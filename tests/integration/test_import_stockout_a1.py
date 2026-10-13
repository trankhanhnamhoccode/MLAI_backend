"""A1 public import and retained forecast acceptance; requires allocated PostgreSQL slot."""
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_execution import ForecastExecutionInput
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.forecast_execution import ForecastExecutionUseCases
from app.models import SalesDaily
from app.models.import_staging import ImportAudit, ImportJob
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, csv_source, post, analyzed
from tests.integration.test_import_commit import ready, commit, finished, analyzed_files
from tests.integration.test_import_staging import approved, previewed
from tests.integration.test_import_classification import confirm


def source(imp, quantity, flag, key='report-A'):
    return dict(product_id=imp[4], sales_date='2026-10-09', quantity=str(quantity), unit='cup',
                business_report_key=key, is_stockout=flag)


def resolution(row):
    merge = row['proposed_action'] == 'MERGE_DISJOINT_SALES'
    return dict(row_id=row['row_id'], action='confirm_disjoint_merge' if merge else 'replace_daily_total',
        report_business_key=row['after']['business_report_key'], evidence_reference='Synthetic explicitly independent contributions' if merge else 'Synthetic corrected report',
        reason='Owner-reviewed complete frozen contribution list', disjoint_assertion=merge)


def approve_sales_files(imp, ident):
    approved(imp, ident, context={'sales_semantics': 'disjoint_contribution'})
    summary = imp[0][5].get('/api/v1/imports/' + ident + '/mapping-summary').json()['data']
    for proposal in summary['profile_proposals']:
        if proposal['active_version'] is not None:
            continue
        response = post(imp, '/stores/' + str(imp[1].store_id) + '/mapping-profiles/'
            + proposal['profile_id'] + '/decisions', dict(decision='approve_activate',
            proposal_revision=proposal['proposal_revision'], expected_active_version=proposal['active_version'],
            reason='Synthetic complete sheet spec approval'), match=proposal['lifecycle_revision'])
        assert response.status_code == 200, response.text


@pytest.mark.parametrize('flag', [True, False, None])
def test_stockout_roundtrip_correction_lineage_and_quantity_only(imp, flag):
    ident, read, rev = ready(imp, csv_source('sales', [source(imp, 100, flag)]))
    receipt = finished(imp, ident, commit(imp, ident, read, rev))
    with Session(imp[0][1]) as fresh:
        sale = fresh.scalar(select(SalesDaily))
        assert sale.quantity == 100 and sale.is_stockout is flag
        audit = fresh.scalar(select(ImportAudit).where(ImportAudit.kind == 'IMPORT_CANONICAL_COMMITTED'))
        assert audit.record_json['sales_sources'][0]['source_stockout'] is flag
    second, read2, rev2 = ready(imp, csv_source('sales', [source(imp, 105, None)]),
        context={'missing_stockout': 'quantity_only'})
    row = read2['preview']['rows'][0]
    assert row['after']['quantity'] == '105' and row['after']['is_stockout'] is flag
    done = finished(imp, second, commit(imp, second, read2, rev2, resolutions=[resolution(row)]))
    assert done['canonical_references'][0]['sales_contributions'][0]['stockout_update'] == 'quantity_only'
    with Session(imp[0][1]) as fresh:
        sale = fresh.scalar(select(SalesDaily))
        assert sale.quantity == 105 and sale.is_stockout is flag
        audits = fresh.scalars(select(ImportAudit).where(ImportAudit.kind == 'IMPORT_CANONICAL_COMMITTED')).all()
        assert sorted(a.record_json['sales_sources'][0]['source_revision'] for a in audits) == [1, 2]


def test_multifile_contributions_205_correction_210_reupload_noop(imp):
    files = [('alpha.csv', csv_source('sales', [source(imp, 100, False, 'A')])),
             ('beta.csv', csv_source('sales', [source(imp, 105, None, 'B')]))]
    ident = analyzed_files(imp, list(reversed(files)))
    # Each structurally distinct sheet needs its own approved reusable spec.
    approve_sales_files(imp, ident)
    read = previewed(imp, ident)
    row, = read['preview']['rows']
    assert row['after']['quantity'] == '205' and row['after']['is_stockout'] is None
    assert len(row['sales_contributions']) == 2
    review = confirm(imp, ident, read)
    assert review.status_code == 200, review.text
    finished(imp, ident, commit(imp, ident, read, review.json()['data']['import_revision'], resolutions=[resolution(row)]))
    second, read2, rev2 = ready(imp, csv_source('sales', [source(imp, 110, None, 'B')]),
        context={'sales_semantics': 'disjoint_contribution'})
    row2, = read2['preview']['rows']
    assert row2['after']['quantity'] == '210'
    finished(imp, second, commit(imp, second, read2, rev2, resolutions=[resolution(row2)]))
    third, read3, rev3 = ready(imp, csv_source('sales', [source(imp, 110, None, 'B')]),
        context={'sales_semantics': 'disjoint_contribution'})
    assert read3['preview']['rows'][0]['proposed_action'] == 'NO_OP'
    finished(imp, third, commit(imp, third, read3, rev3))
    with Session(imp[0][1]) as fresh:
        rows = fresh.scalars(select(SalesDaily)).all()
        assert len(rows) == 1 and rows[0].quantity == 210 and rows[0].is_stockout is None


def test_captured_forecast_digest_correction_retained_replay(imp):
    first, read, rev = ready(imp, csv_source('sales', [source(imp, 100, False)]))
    finished(imp, first, commit(imp, first, read, rev))
    execution = ForecastExecutionUseCases(imp[0][1])
    request = ForecastExecutionInput(store_id=imp[1].store_id, product_ids=(imp[4],),
        history_start_date=date(2026, 10, 9), cutoff_date=date(2026, 10, 9))
    before = execution.capture(request)
    run = execution.execute(request)
    reference = RunReferenceInput(store_id=request.store_id, run_id=run.id)
    original = execution.replay(reference)
    second, read2, rev2 = ready(imp, csv_source('sales', [source(imp, 100, True)]))
    row, = read2['preview']['rows']
    assert row['proposed_action'] == 'REPLACE_DAILY_TOTAL'
    finished(imp, second, commit(imp, second, read2, rev2, resolutions=[resolution(row)]))
    assert serialize_prepared(execution.capture(request)).digest != serialize_prepared(before).digest
    assert execution.load_retained(reference) == before
    assert execution.replay(reference) == original
    with Session(imp[0][1]) as fresh:
        sale = fresh.scalar(select(SalesDaily))
        assert sale.quantity == 100 and sale.is_stockout is True


def test_missing_stockout_requires_explicit_unknown_and_absent_dates_stay(imp):
    earlier = source(imp, 100, False)
    earlier['sales_date'] = '2026-10-08'
    first, read, revision = ready(imp, csv_source('sales', [earlier, source(imp, 0, False)]))
    finished(imp, first, commit(imp, first, read, revision))
    incoming = source(imp, 9, None)
    del incoming['is_stockout']
    second = analyzed(imp, csv_source('sales', [incoming]))
    approved(imp, second)
    blocked = previewed(imp, second)
    assert any(b['code'] == 'STOCKOUT_UPDATE_DECLARATION_REQUIRED'
        for b in blocked['preview']['summary']['blockers'])
    assert confirm(imp, second, blocked).status_code == 409
    approved(imp, second, context={'missing_stockout': 'not_provided'})
    reviewed = previewed(imp, second)
    row, = reviewed['preview']['rows']
    assert row['after']['quantity'] == '9' and row['after']['is_stockout'] is None
    accepted = confirm(imp, second, reviewed)
    assert accepted.status_code == 200, accepted.text
    finished(imp, second, commit(imp, second, reviewed,
        accepted.json()['data']['import_revision'], resolutions=[resolution(row)]))
    with Session(imp[0][1]) as fresh:
        rows = fresh.scalars(select(SalesDaily).order_by(SalesDaily.sales_date)).all()
        assert [(r.quantity, r.is_stockout) for r in rows] == [(100, False), (9, None)]


def test_concurrent_corrections_keep_one_atomic_quantity_and_observation(imp):
    ident, read, revision = ready(imp, csv_source('sales', [source(imp, 100, False)]))
    finished(imp, ident, commit(imp, ident, read, revision))
    pending = []
    plans = []
    for quantity, flag in ((105, True), (110, False)):
        ident, read, revision = ready(imp, csv_source('sales', [source(imp, quantity, flag)]))
        plans.append((ident, read, revision))
    # Finish analysis/preview jobs before queueing either commit. A helper must
    # not inadvertently consume a prior queued correction while analyzing B.
    for ident, read, revision in plans:
        response = commit(imp, ident, read, revision, resolutions=[resolution(read['preview']['rows'][0])])
        assert response.status_code == 202, response.text
        pending.append(UUID(response.json()['data']['job_id']))
    from app.application.use_cases.import_staging import ImportStaging
    other_worker = ImportStaging(imp[0][2], imp[2].settings)
    with ThreadPoolExecutor(max_workers=2) as workers:
        claimed = list(workers.map(lambda worker: worker.run_one(), (imp[2], other_worker)))
    assert set(claimed) == set(pending)
    with Session(imp[0][1]) as fresh:
        jobs = [fresh.get(ImportJob, job) for job in pending]
        assert sorted(j.status for j in jobs) == ['completed', 'failed']
        failed = next(j for j in jobs if j.status == 'failed')
        assert failed.error_json['code'] == 'PREVIEW_STALE'
        row = fresh.scalar(select(SalesDaily))
        assert (row.quantity, row.is_stockout) in ((105, True), (110, False))
        audits = fresh.scalars(select(ImportAudit).where(ImportAudit.kind == 'IMPORT_CANONICAL_COMMITTED')).all()
        assert len(audits) == 2  # Initial insert + one correction, no losing audit.


def test_stockout_and_quantity_roll_back_together_after_writer_flush(imp, monkeypatch):
    from app.application.use_cases.sales import SalesUseCases
    from app.application.contracts.auth import AuthError
    earlier = source(imp, 100, True)
    earlier['sales_date'] = '2026-10-08'
    ident, read, revision = ready(imp, csv_source('sales', [earlier, source(imp, 0, False)]))
    original = SalesUseCases.record_in_transaction
    writes = []
    def reject_second(self, value):
        result = original(self, value)
        writes.append(result)
        if len(writes) == 2:
            raise AuthError('PREVIEW_BLOCKED', 409)
        return result
    monkeypatch.setattr(SalesUseCases, 'record_in_transaction', reject_second)
    response = commit(imp, ident, read, revision)
    assert response.status_code == 202, response.text
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        assert len(writes) == 2 and {r.is_stockout for r in writes} == {True, False}
        assert fresh.scalars(select(SalesDaily)).all() == []
        assert fresh.scalars(select(ImportAudit).where(ImportAudit.kind == 'IMPORT_CANONICAL_COMMITTED')).all() == []
        assert fresh.get(ImportJob, UUID(response.json()['data']['job_id'])).status == 'failed'


@pytest.mark.parametrize('revoke_after_acceptance', [False, True])
def test_masked_contribution_observation_correction_needs_resolution_and_current_rights(imp, revoke_after_acceptance):
    files = [('alpha.csv', csv_source('sales', [source(imp, 100, False, 'A')])),
        ('beta.csv', csv_source('sales', [source(imp, 105, True, 'B')]))]
    ident = analyzed_files(imp, files)
    approve_sales_files(imp, ident)
    read = previewed(imp, ident)
    reviewed = confirm(imp, ident, read)
    assert reviewed.status_code == 200, reviewed.text
    finished(imp, ident, commit(imp, ident, read,
        reviewed.json()['data']['import_revision'], resolutions=[resolution(read['preview']['rows'][0])]))
    second, preview, revision = ready(imp, csv_source('sales', [source(imp, 100, None, 'A')]),
        context={'sales_semantics': 'disjoint_contribution'})
    row, = preview['preview']['rows']
    assert row['after']['quantity'] == '205' and row['after']['is_stockout'] is True
    assert row['proposed_action'] == 'REPLACE_DAILY_TOTAL' and row['confirmation_required']
    rejected = commit(imp, second, preview, revision)
    assert rejected.status_code in (409, 422), rejected.text
    response = commit(imp, second, preview, revision, resolutions=[resolution(row)])
    assert response.status_code == 202, response.text
    if revoke_after_acceptance:
        from app.models import StoreMembership
        from app.models.auth import MembershipGrant
        from app.domain.permissions import PERMISSIONS
        with Session(imp[0][1]) as writer, writer.begin():
            member = writer.scalar(select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id))
            member.role = 'STAFF'
            writer.add_all([MembershipGrant(membership_id=member.id, permission=key)
                for key in sorted(PERMISSIONS - {'sales.correct'})])
        imp[2].run_one()
    else:
        finished(imp, second, response)
    with Session(imp[0][1]) as fresh:
        sale = fresh.scalar(select(SalesDaily))
        assert sale.quantity == 205 and sale.is_stockout is True
        audits = fresh.scalars(select(ImportAudit).where(ImportAudit.kind == 'IMPORT_CANONICAL_COMMITTED')).all()
        assert len(audits) == (1 if revoke_after_acceptance else 2)
        job = fresh.get(ImportJob, UUID(response.json()['data']['job_id']))
        if revoke_after_acceptance:
            assert job.status == 'failed' and job.error_json['code'] == 'PERMISSION_DENIED'
        else:
            corrected = next(a.record_json['sales_sources'][0] for a in audits
                if len(a.record_json['sales_sources']) == 1)
            assert corrected['business_report_key'] == 'A' and corrected['source_revision'] == 2
            assert corrected['source_stockout'] is None and corrected['canonical_stockout'] is True
