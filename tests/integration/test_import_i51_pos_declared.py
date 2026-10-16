"""User-established original POS facts progress through full-spec N5 and real preview."""
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, SalesDaily
from app.models.import_staging import ImportAudit, ImportBatch, ImportPreview, ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store
from tests.integration.test_import_commit import commit, finished
from tests.integration.test_import_classification import listing, mapping, confirm
from tests.integration.test_import_rule_review import summary
from tests.integration.test_import_staging import post, previewed
from tests.integration.import_i5_evidence import CASES, SOURCE_DIRECTORY, cells_by_sheet, save, i5_trace

DECLARATIONS = json.loads((Path(__file__).parents[1] / 'fixtures/import_i51_pos_declarations.json').read_text(encoding='utf-8'))


def upload_declared_pos(context, path, filename=None):
    """Public upload with the user's explicit baseline data_date, not fixture date."""
    draft = post(context, f'/stores/{context[1].store_id}/imports', {'data_date':DECLARATIONS['data_date']})
    assert draft.status_code == 201, draft.text
    ident = draft.json()['data']['import_id']
    uploaded = context[0][5].post(f'/api/v1/imports/{ident}/files',
        headers={**context[3],'Idempotency-Key':str(uuid4())},
        files=[('files[]',(filename or path.name,path.read_bytes(),'application/octet-stream'))],
        data={'client_file_ids[]':[str(uuid4())]})
    assert uploaded.status_code == 200, uploaded.text
    data = uploaded.json()['data']
    analyzed = post(context,f'/imports/{ident}/analyze',dict(file_set_version=data['file_set_version'],
        accepted_file_ids=[r['file_id'] for r in data['items']],acknowledged_rejected_client_file_ids=[]),
        match=data['import_revision'])
    assert analyzed.status_code == 202, analyzed.text
    assert context[2].run_one() == UUID(analyzed.json()['data']['job_id'])
    return ident


def test_original_pos_user_declarations_owner_review_commit_and_same_report_reexport(fresh_store, monkeypatch, i5_trace):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('provider forbidden'))
    paths = [SOURCE_DIRECTORY / CASES[n]['file'] for n in (0, 5)]
    if not all(p.is_file() for p in paths):
        pytest.skip('Original source absent; original completion remains BLOCKED')
    for path, case in zip(paths, (CASES[0], CASES[5])):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']
    assert CASES[0]['sha256'] == DECLARATIONS['pos_sha256']
    assert CASES[5]['sha256'] == DECLARATIONS['menu_sha256']
    pos = cells_by_sheet(paths[0])[CASES[0]['sheets'][1]]
    menu = cells_by_sheet(paths[1])[CASES[5]['sheets'][0]]
    expected = {}
    for key in pos:
        if key.startswith('A') and key[1:].isdigit() and int(key[1:]) >= 4:
            n = key[1:]
            expected[int(n)] = (pos['B'+n], (date(1899,12,30)+timedelta(days=int(pos[key]))).isoformat(), pos['C'+n], pos['F'+n])
    assert len(expected) == 945
    context = fresh_store  # Auth/empty Store only; Product creation must use Import.
    ident = upload_declared_pos(context, paths[0])
    current = summary(context, ident)
    pos_sheet = next(s for s in current['sheets'] if s['name'] == CASES[0]['sheets'][1])
    readme = next(s for s in current['sheets'] if s['name'] == 'README')
    def change(issue, body):
        response = mapping(context, ident, issue, body)
        assert response.status_code == 200, response.text
    def own(kind):
        return [i for i in listing(context, ident) if i['sheet_id'] == pos_sheet['sheet_id'] and i['issue_type'] == kind]
    change(next(i for i in listing(context, ident) if i['sheet_id'] == readme['sheet_id'] and i['issue_type'] == 'classification'),
           {'resolution': dict(kind='sheet_type', sheet_type=None, ignored=True, acknowledgment=True, reason=DECLARATIONS['scope'])})
    change(own('classification')[0], {'resolution': dict(kind='sheet_type', sheet_type='sales', reason=DECLARATIONS['evidence_reference'])})
    change(own('source_context')[0], {'resolution': dict(kind='source_context',
        source_system_key=DECLARATIONS['source_system_key'], report_type=DECLARATIONS['report_type'],
        sales_semantics=DECLARATIONS['sales_semantics'], date_format='EXCEL_SERIAL',
        stockout_aliases=[dict(token=pos['F4'], value=True), dict(token=pos['F5'], value=False)],
        evidence_reference=DECLARATIONS['evidence_reference'] + '; source XLSX epoch1900 and F header/values')})
    targets = {0:'sales.sales_date', 1:'sales.product_id', 2:'sales.quantity', 5:'sales.is_stockout'}
    for column in range(7):
        issue = next(i for i in own('column') if i['source_location']['source_column_index'] == column)
        change(issue, {'target_field':targets[column]} if column in targets else
               {'resolution':dict(kind='ignored_optional_field', evidence_reference=DECLARATIONS['scope'])})
    units = {menu[f'E{n}'] for n in range(4,9)}
    assert len(units) == 1
    for target, scope, value, evidence in (
        ('sales.unit','PROFILE_CONSTANT',next(iter(units)), 'Menu E4:E8, exact-name matches; no guessed unit'),
        ('sales.business_report_key','IMPORT_VALUE',DECLARATIONS['business_report_key'],DECLARATIONS['identity_lifecycle'])):
        change(own('source_context')[0], {'resolution':dict(kind='shared_value', target_field=target,
            scope=scope, value=value, evidence_reference=DECLARATIONS['evidence_reference']+'; '+evidence)})
    metadata = {}
    for issue in own('identity'):
        token = issue['source_header']
        matches = [n for n in range(4,9) if menu[f'C{n}'] == token]
        assert len(matches) == 1
        n = matches[0]
        # Establish each status from its source cell, never a default for all Products.
        assert menu[f'J{n}'] in ('Đang bán', 'Tạm dừng')
        facts = dict(name=menu[f'C{n}'], selling_unit=menu[f'E{n}'], price=menu[f'H{n}'],
                     active=menu[f'J{n}']=='Đang bán', sku=DECLARATIONS['sku'])
        metadata[token] = facts
        change(issue, {'resolution':dict(kind='new_entity_proposal', entity='product', source_business_key=token,
            metadata=facts, evidence_reference=DECLARATIONS['sku_evidence']+'; Menu SHA256 '+CASES[5]['sha256']+f' row{n}: C/E/H/J; A is source code only')})
    assert len(metadata) == 5
    proposal, = summary(context, ident)['profile_proposals']
    assert not proposal['missing_fields'] and proposal['spec'] is not None
    assert proposal['spec']['sales_semantics'] == 'daily_total'
    assert len(proposal['spec']['entity_proposals']) == 5
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    approved = post(context, f'/stores/{context[1].store_id}/mapping-profiles/{proposal["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=proposal['proposal_revision'], expected_active_version=proposal['active_version'],
             reason=DECLARATIONS['evidence_reference']+'; Owner reviewed exact names, per-row Menu metadata and explicitly unknown SKU'),
        match=proposal['lifecycle_revision'])
    assert approved.status_code == 200, approved.text
    assert summary(context, ident)['can_preview']
    read = previewed(context, ident)
    with Session(context[0][1]) as fresh:
        preview = fresh.get(ImportPreview, UUID(read['preview']['summary']['preview_id']))
        rows = preview.content_json['rows']
        valid_sales = [r for r in rows if r['after'] and r['after']['domain'] == 'sales']
        invalid = [r for r in rows if r['classification'] == 'INVALID']
        creations = [r for r in rows if r['proposed_action'] == 'CREATE_PRODUCT']
        assert len(valid_sales) == 945 and len(creations) == 5
        ids = {r['after']['source_business_key']:r['entity_refs']['product_id'] for r in creations}
        for r in valid_sales:
            token, day, quantity, flag = expected[r['source_location']['row_number']]
            assert r['after']['product_id'] == ids[token] and r['after']['sales_date'] == day
            assert Decimal(r['after']['quantity']) == Decimal(quantity) and r['after']['unit'] in units
            assert r['after']['is_stockout'] == (flag == pos['F4'])
        counts = {m.__tablename__:fresh.scalar(select(func.count()).select_from(m)) for m in (Product,SalesDaily)}
        assert counts == {'products':0,'sales_daily':0}
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        batch = fresh.get(ImportBatch,UUID(ident))
        assert not batch.analysis_json.get('completion')
        raw = next(s for s in batch.analysis_json['sources'] if s['sheet_id'] == pos_sheet['sheet_id'])
        assert len(raw['rows']) == 1155  # Physical formatting remains in immutable evidence.
    assert not invalid and not read['preview']['summary']['blockers']
    excluded = [w['source_location']['row_number'] for w in read['preview']['summary']['warnings']
                if w['code'] == 'XLSX_FORMAT_ONLY_ROW_SKIPPED']
    assert excluded == list(range(949,1159))
    reviewed = confirm(context,ident,read)
    assert reviewed.status_code == 200, reviewed.text
    done = finished(context,ident,commit(context,ident,read,reviewed.json()['data']['import_revision']))
    with Session(context[0][1]) as fresh:
        products = {str(p.id):p for p in fresh.scalars(select(Product))}
        assert len(products) == 5 and set(products) == set(ids.values())
        for token,pid in ids.items():
            p = products[pid]
            assert p.store_id == context[1].store_id and p.sku is None
            assert p.name == metadata[token]['name'] and p.selling_unit == metadata[token]['selling_unit']
            assert p.price == Decimal(metadata[token]['price']) and p.active == metadata[token]['active']
        saved = {(str(s.product_id),s.sales_date.isoformat()):s for s in fresh.scalars(select(SalesDaily))}
        assert len(saved) == 945
        for token,day,quantity,flag in expected.values():
            s = saved[ids[token],day]
            assert s.store_id == context[1].store_id and s.quantity == Decimal(quantity)
            assert s.is_stockout == (flag == pos['F4'])
        audits = fresh.scalars(select(ImportAudit).where(ImportAudit.kind=='IMPORT_CANONICAL_COMMITTED')).all()
        contributions = [v for a in audits for v in a.record_json['sales_sources']]
        assert len(contributions) == 945
        assert all(v['source_revision']==1 and v['source_system_key']==DECLARATIONS['source_system_key']
                   and v['report_type']==DECLARATIONS['report_type'] and v['business_report_key']==DECLARATIONS['business_report_key'] for v in contributions)
    # Same original bytes/source/report: approved binding and explicit same report value,
    # no model/new identity/N5 and no extra contribution or Product rows.
    second = upload_declared_pos(context,paths[0],filename='reexport-of-baseline-2026-07-08.xlsx')
    sheets = summary(context,second)['sheets']
    other = next(s for s in sheets if s['name']=='README')
    issue = next(i for i in listing(context,second) if i['sheet_id']==other['sheet_id'] and i['issue_type']=='classification')
    response = mapping(context,second,issue,{'resolution':dict(kind='sheet_type',sheet_type=None,ignored=True,
        acknowledgment=True,reason=DECLARATIONS['scope'])})
    assert response.status_code==200,response.text
    issue = next(i for i in listing(context,second) if i['issue_type']=='source_context' and i['sheet_id']!=other['sheet_id'])
    response = mapping(context,second,issue,{'resolution':dict(kind='source_context',source_system_key=DECLARATIONS['source_system_key'],
        report_type=DECLARATIONS['report_type'],sales_semantics='daily_total',date_format='EXCEL_SERIAL',
        stockout_aliases=[dict(token=pos['F4'],value=True),dict(token=pos['F5'],value=False)],evidence_reference=DECLARATIONS['evidence_reference'])})
    assert response.status_code==200,response.text
    current = summary(context,second)
    assert current['binding_refs'] and not current['profile_proposals']
    issue = next(i for i in listing(context,second) if i['sheet_id']!=other['sheet_id'])
    response = mapping(context,second,issue,{'resolution':dict(kind='shared_value',target_field='sales.business_report_key',
        scope='IMPORT_VALUE',value=DECLARATIONS['business_report_key'],evidence_reference=DECLARATIONS['identity_lifecycle'])})
    assert response.status_code==200,response.text
    replay_preview = previewed(context,second)
    assert replay_preview['preview']['summary']['counts']['NEW']==0 and not replay_preview['preview']['summary']['blockers']
    reviewed = confirm(context,second,replay_preview)
    assert reviewed.status_code==200,reviewed.text
    replay = finished(context,second,commit(context,second,replay_preview,reviewed.json()['data']['import_revision']))
    assert replay['outcome']=='no_changes'
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product))==5
        assert fresh.scalar(select(func.count()).select_from(SalesDaily))==945
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1
        final_sales = {(str(s.product_id),s.sales_date.isoformat()):s for s in fresh.scalars(select(SalesDaily))}
        for token,day,quantity,flag in expected.values():
            s = final_sales[ids[token],day]
            assert s.store_id == context[1].store_id and s.quantity == Decimal(quantity)
            assert s.is_stockout == (flag == pos['F4'])
        audits = fresh.scalars(select(ImportAudit).where(ImportAudit.kind=='IMPORT_CANONICAL_COMMITTED')).all()
        final_contributions = [v for a in audits for v in a.record_json['sales_sources']]
        assert len(final_contributions)==945 and all(v['source_revision']==1 for v in final_contributions)
    save('original-pos-declared-preview',dict(import_id=ident,declarations=DECLARATIONS,approved=approved.json()['data'],
        preview_summary=read['preview']['summary'],preview_rows=rows,canonical_counts=counts,
        populated_sales_rows=len(valid_sales),product_proposals=metadata,format_only_row_warnings=excluded,
        completion=done,reexport_completion=replay,canonical_counts_after_commit={'products':5,'sales_daily':945},
        fresh_after_reexport_values_verified=945,source_contributions_after_reexport=945,
        database_lifecycle='Supported fixture resets owned test DB after case; committed-state assertions run before cleanup',
        outcome='SOURCE_FAITHFUL_SYNTHETIC_ORIGINAL_POS_SCOPE_COMMITTED_NOT_WHOLE_WORKBOOK'))
    for path, case in zip(paths,(CASES[0],CASES[5])):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']
