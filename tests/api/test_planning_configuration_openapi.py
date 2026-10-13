"""Accepted S4.8 API inventory and FE-critical header/error contract."""
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings


def test_s48_accepted_operations_and_conditional_responses():
    schema=create_app(Settings(_env_file=None)).openapi()
    base='/api/v1/stores/{store_id}'
    operations=[('/planning-requirements','post','N1','201'),
        ('/planning-requirements/{saved_requirement_id}','get','N2','200'),
        ('/planning-requirements/{saved_requirement_id}','put','N3','200'),
        ('/planning-budget','put','N4','200'),('/readiness','get','R01','200'),('/planning-context','get','C01','200')]
    for suffix,method,identity,status in operations:
        operation=schema['paths'][base+suffix][method]
        assert operation['operationId']==identity
        assert operation['security']==[{'APIKeyCookie':[]}]
        assert {status,'401','403','404','422','503'}<=set(operation['responses'])
    budget=schema['paths'][base+'/planning-budget']['put']
    assert {'If-Match','If-None-Match','Idempotency-Key'}<={p['name'] for p in budget['parameters']}
    assert {'ETag','Location'}<=set(budget['responses']['201']['headers'])
    assert budget['responses']['201']['content']['application/json']['schema']==budget['responses']['200']['content']['application/json']['schema']
    assert 'model_config' in schema['components']['schemas']['SourceVersions']['properties']
    readiness_dates=schema['components']['schemas']['Readiness']['properties']
    assert readiness_dates['cutoff_date']['type']=='string'


def test_fe_can_send_create_only_header_and_read_location():
    app=create_app(Settings(_env_file=None,auth_allowed_origins=['https://fe.example.test']))
    with TestClient(app) as client:
        response=client.options('/api/v1/stores/x/planning-budget',headers={
            'Origin':'https://fe.example.test','Access-Control-Request-Method':'PUT',
            'Access-Control-Request-Headers':'If-None-Match,Idempotency-Key,X-CSRF-Token'})
        assert response.status_code==200
        assert 'if-none-match' in response.headers['access-control-allow-headers'].lower()
