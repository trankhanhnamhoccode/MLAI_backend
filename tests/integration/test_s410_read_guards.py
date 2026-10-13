"""Actual retained HTTP: no computation/writes, foreign Store and body guards."""
from uuid import uuid4
from sqlalchemy import event
from sqlalchemy.orm import Session
from tests.integration.test_planning_exports import exports, export
from tests.integration.test_planning_public import flow, config, env, submit, demand_and_offer
from app.models import PlanningExport


def test_read_hooks_foreign_store_and_export_transport(exports, monkeypatch):
    flow, service = exports
    c, ingredient, _, worker = flow
    client, engine = c[0][5], c[0][1]
    # All boundary services share the fixture's real auth use case/controlled clock.
    from app.application.use_cases.import_history import ImportHistoryReads
    from app.application.use_cases.import_staging import ImportStaging
    client.app.state.import_staging = ImportStaging(c[0][2], c[0][0])
    client.app.state.import_history = ImportHistoryReads(client.app.state.import_staging)
    demand_and_offer(flow)
    accepted = submit(c)
    location = accepted.headers['Location']
    run = worker.run_one()
    assert run.status == 'completed'
    receipt = export(c, location).json()['data']
    assert service.run_one().status == 'completed'
    store_path = f'/api/v1/stores/{c[1].store_id}'
    reads = [location, location+'/ingredients', location+'/ingredients/'+str(ingredient),
        location+'/explanation', store_path+'/procurement-plans',
        store_path+'/imports/calendar?month=2026-10', store_path+'/imports?import_date=2026-10-10',
        '/api/v1/jobs/'+receipt['job_id'], location+'/exports/'+receipt['export_id']]

    def forbidden(*args, **kwargs):
        raise AssertionError('GET attempted computation/provider/recapture')

    forecast = client.app.state.forecast_serving
    for name in ('prepare', 'serve', 'prepare_serve_capture', 'capture_operational_preparation'):
        monkeypatch.setattr(forecast, name, forbidden)
    monkeypatch.setattr(worker, 'execute', forbidden)
    monkeypatch.setattr(service.renderer, 'render', forbidden)
    from app.infrastructure.procurement_milp_v2 import NativeProductSearch
    monkeypatch.setattr(NativeProductSearch, '__init__', forbidden)
    from app.application.use_cases import import_staging
    monkeypatch.setattr(import_staging.ImportStaging, 'run_one', forbidden)

    statements = []
    def sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split(None, 1)[0].upper())
    event.listen(engine, 'before_cursor_execute', sql)
    try:
        for path in reads:
            response = client.get(path)
            assert response.status_code == 200, (path, response.text[:500])
        assert not set(statements) & {'INSERT', 'UPDATE', 'DELETE'}, statements
    finally:
        event.remove(engine, 'before_cursor_execute', sql)

    for path, expected in [(location+'/ingredients?limit=101', 'INVALID_FILTER'),
        (store_path+'/procurement-plans?status=invalid', 'INVALID_FILTER'),
        (store_path+'/imports/calendar?month=bad', 'INVALID_MONTH'),
        (store_path+'/imports?import_date=bad', 'INVALID_DATE')]:
        response = client.get(path)
        assert response.status_code == 422 and response.json()['error']['code'] == expected, response.text
    before = None
    with Session(engine) as fresh:
        before = fresh.query(PlanningExport).count()
    response = client.post(location+'/exports', headers={**c[3], 'Idempotency-Key':str(uuid4()),
        'Content-Type':'application/json'}, content=b' '*(64*1024+1))
    assert response.status_code == 413 and response.json()['error']['code'] == 'RESOURCE_LIMIT_EXCEEDED', response.text
    with Session(engine) as fresh:
        assert fresh.query(PlanningExport).count() == before

    from tests.integration.test_auth_public import setup, login
    setup(c[0], 'other-store@example.test')
    signed = login(c[0], 'other-store@example.test').json()['data']
    for path in reads:
        response = client.get(path)
        assert response.status_code == 404, (path, response.text[:500])
    response = client.post(location+'/exports', headers={**c[3],
        'X-CSRF-Token':signed['session']['csrf_token'], 'Idempotency-Key':str(uuid4())},
        json={'format':'pdf', 'option_id':None, 'locale':'vi'})
    assert response.status_code == 404, response.text
