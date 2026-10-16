"""Original Menu guards and separate synthetic catalog capability, never substitute facts."""
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, Recipe, SalesDaily
from app.models.import_staging import ImportBatch, ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store, review_batch, complete
from tests.integration.test_import_i51_pos_declared import upload_declared_pos
from tests.integration.test_import_classification import listing, mapping, confirm
from tests.integration.test_import_rule_review import summary
from tests.integration.test_import_staging import post, csv_source, previewed
from tests.integration.test_import_commit import analyzed_files, commit, finished
from tests.integration.import_i5_evidence import CASES, SOURCE_DIRECTORY, cells_by_sheet, save, i5_trace

MENU_DECLARATIONS=json.loads((Path(__file__).parents[1]/'fixtures/import_menu_declarations.json').read_text(encoding='utf-8'))


def prepare_original_menu(fresh_store, monkeypatch, source_system_key="MENU_INSPECTION_ONLY"):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('provider forbidden'))
    path = SOURCE_DIRECTORY / CASES[5]['file']
    assert path.is_file(), 'Original Menu is required for this acceptance case'
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == CASES[5]['sha256']
    assert digest == MENU_DECLARATIONS['menu_sha256']
    cells = cells_by_sheet(path)['06_Menu']
    rows = [dict(row=n, source_key=cells[f'A{n}'], name=cells[f'C{n}'],
                 unit=cells[f'E{n}'], price=cells[f'H{n}'], raw_status=cells[f'J{n}'],
                 # Explicit earlier user decisions, not inference from Product history.
                 declared_active=MENU_DECLARATIONS['products_by_full_name'][cells[f'C{n}']]['active'],
                 declared_sku=MENU_DECLARATIONS['products_by_full_name'][cells[f'C{n}']]['sku'])
            for n in range(4, 14)]
    assert len({r['source_key'] for r in rows}) == 10
    assert len({r['name'] for r in rows}) == 10
    assert {r['name'] for r in rows} == set(MENU_DECLARATIONS['products_by_full_name'])
    assert all(r['raw_status'] == 'Đang bán' for r in rows)
    assert 'tạm dừng' in cells['A2']
    context = fresh_store  # Previous POS fixture cleaned up; no business seed or old UUIDs.
    ident = upload_declared_pos(context, path)
    sheet, = summary(context, ident)['sheets']
    assert sheet['header_row'] == 3 and sheet['row_count'] == 10

    def issue(kind):
        return next(i for i in listing(context, ident) if i['issue_type'] == kind)

    def change(item, body):
        response = mapping(context, ident, item, body)
        assert response.status_code == 200, response.text

    change(issue('classification'), {'resolution':dict(kind='sheet_type', sheet_type='products',
        reason='User-approved catalog-only scope; recipes/discounts remain raw')})
    change(issue('source_context'), {'resolution':dict(kind='source_context',
        source_system_key=source_system_key, report_type='PRODUCT_CATALOG',
        evidence_reference=('Isolated inspection namespace, not an approved canonical source identity'
            if source_system_key == 'MENU_INSPECTION_ONLY' else
            'User-created synthetic Menu baseline 08/07/2026; stable catalog source namespace chosen for isolated acceptance, retained on reexport'))})
    targets = {0:'products.source_business_key', 2:'products.name', 4:'products.selling_unit',
               7:'products.price', 9:'products.active'}
    for column in range(10):
        item = next(i for i in listing(context, ident) if i['issue_type'] == 'column'
                    and i['source_location']['source_column_index'] == column)
        change(item, {'target_field':targets[column]} if column in targets else
               {'resolution':dict(kind='ignored_optional_field',
                 evidence_reference='User-approved Product scope; B/D/F/G/I retained raw, no BOM/discount facts')})
    for item in [i for i in listing(context,ident) if i['issue_type'] == 'identity']:
        record, = [r for r in rows if r['source_key'] == item['source_header']]
        change(item, {'resolution':dict(kind='new_entity_proposal',entity='product',
            source_business_key=record['source_key'], metadata=dict(name=record['name'],
            selling_unit=record['unit'], price=record['price'], active=record['declared_active'],
            sku=record['declared_sku']), evidence_reference=(
                f"Original hash {digest}, row {record['row']}: C/E/H; prior user decisions: "
                'five POS SKUs unknown/null, combo SKUs t6..t10, combo A2 paused authority. '
                'Inspection-only reservation; no canonical Product or N5 approval'))})
    return context, ident, rows, digest, path, cells, sheet


def test_original_menu_keeps_all_rows_and_blocks_unreviewed_status(fresh_store, monkeypatch, i5_trace):
    context, ident, rows, digest, path, cells, sheet = prepare_original_menu(fresh_store, monkeypatch)

    def issue(kind):
        return next(i for i in listing(context, ident) if i['issue_type'] == kind)

    # M1 supports explicit batch-only null for a homogeneous sheet. The approved
    # unknown scope here is five keys; never extend it to the five known combo SKUs.
    # PROFILE_CONSTANT remains forbidden even after M1.
    rejected = mapping(context, ident, issue('source_context'), {'resolution':dict(
        kind='shared_value', target_field='products.sku', scope='PROFILE_CONSTANT', value=None,
        evidence_reference='Capability probe only; NOT approval to apply null to all ten rows')})
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'VALIDATION_ERROR'
    current = summary(context, ident)
    proposal, = current['profile_proposals']
    assert not proposal['missing_fields'] and proposal['spec'] is not None
    assert not current['can_preview'] and not current['binding_refs']
    options = context[0][5].get(f'/api/v1/imports/{ident}/sheets/{sheet["sheet_id"]}/field-options')
    assert options.status_code == 200, options.text
    sku = next(o for o in options.json()['data']['options'] if o['key'] == 'products.sku')
    assert sku['allowed_shared_scopes'] == ['IMPORT_VALUE'] and sku['nullable']
    assert not current['sheets'][0]['import_values']  # No unauthorized all-ten null.
    approval = post(context, f'/stores/{context[1].store_id}/mapping-profiles/{proposal["profile_id"]}/decisions',
        dict(decision='approve_activate', proposal_revision=proposal['proposal_revision'],
             expected_active_version=proposal['active_version'], reason='Review complete spec under approved missing-SKU policy; source status remains invalid'),
        match=proposal['lifecycle_revision'])
    assert approval.status_code == 200, approval.text
    # Re-read revisions after Owner activation; invalid source status still blocks.
    from tests.integration.test_import_staging import previewed
    read = previewed(context, ident)
    assert not read['preview']['summary']['can_commit']
    assert any(b['code'] == 'INVALID_BOOLEAN' for r in read['preview']['rows'] for b in r['blockers'])
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        raw, = fresh.get(ImportBatch, UUID(ident)).analysis_json['sources']
        assert [r['row_number'] for r in raw['rows']] == list(range(4,14))
        for r in raw['rows']:
            assert {c['column_index']:c['raw'] for c in r['cells']} == {
                i:cells[f'{letter}{r["row_number"]}'] for i,letter in enumerate('ABCDEFGHIJ')}
        assert not fresh.get(ImportBatch, UUID(ident)).analysis_json.get('completion')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    save('original-menu-inspection', dict(outcome='BLOCKED_MISSING_EXPLICIT_DECLARATIONS_NOT_END_TO_END_PASS',
        sha256=digest, import_id=ident, rows=rows, source_namespace='INSPECTION_ONLY_NOT_CANONICAL_BINDING',
        scope='All ten populated rows, catalog only; B/D/F/G/I raw, no recipe/discount',
        retained_decisions='Five POS SKUs explicitly null; prior Menu SKU t6..t10 decision applies only to combo rows; prior A2 authority makes combos paused',
        missing_fields=proposal['missing_fields'], guidance=current['completion_guidance'],
        m1_scope_limit='IMPORT_VALUE null is available only sheet-wide; five unknown keys plus five known SKUs cannot share one value',
        shared_sku_error=rejected.json()['error'], approval_error=approval.json()['error'],
        preview_blockers=read['preview']['summary']['blockers'], canonical_products=0,
        additional_limit='Raw Vietnamese status has no Product bool alias; sheet-wide constant cannot express mixed reviewed status',
        limits='Owner reviewed; typed preview blocked by invalid source status. No canonical Products, confirmation/commit or original reexport NO_OP'))


def test_synthetic_catalog_mixed_status_nullable_sku_commit_and_renamed_reexport(fresh_store, monkeypatch, i5_trace):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('provider forbidden'))
    context = fresh_store
    records = [dict(source_business_key='CAT-A', name='Synthetic available item', selling_unit='cup',
                    sku=None, price='12000', active=True),
               dict(source_business_key='CAT-B', name='Synthetic paused item', selling_unit='box',
                    sku='SYN-B', price='45000', active=False)]
    content = csv_source('products', records)
    source = dict(source_system_key='SYNTHETIC_CATALOG_ACCEPTANCE', report_type='PRODUCT_CATALOG')
    ident = analyzed_files(context, [('catalog.csv',content)])
    review_batch(context,ident,creations={r['source_business_key']:('product',
        {k:v for k,v in r.items() if k != 'source_business_key'}) for r in records}, source_context=source)
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0
    read = previewed(context,ident)
    confirmation = confirm(context,ident,read)
    assert confirmation.status_code == 200, confirmation.text
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0
    done = finished(context,ident,commit(context,ident,read,confirmation.json()['data']['import_revision']))
    with Session(context[0][1]) as fresh:
        products = {p.name:p for p in fresh.scalars(select(Product))}
        assert len(products) == 2
        ids = {name:str(p.id) for name,p in products.items()}
        for r in records:
            p=products[r['name']]
            assert p.store_id == context[1].store_id and p.active is r['active']
            assert p.sku == r['sku'] and p.selling_unit == r['selling_unit'] and p.price == int(r['price'])
        versions = fresh.scalar(select(func.count()).select_from(ImportProfileVersion))
        retained = fresh.get(ImportBatch,UUID(ident)).analysis_json['completion']
        assert {r['canonical_id'] for r in retained['canonical_references']} == set(ids.values())
        assert retained['mapping_bindings'] == done['mapping_bindings']
        paused, = [r for r in retained['canonical_references'] if r['canonical_id'] == ids[records[1]['name']]]
        assert paused['provenance']['active']['source_value'] == 'false'
    renamed = analyzed_files(context, [('renamed-catalog.csv',content)])
    review_batch(context,renamed,source_context=source)
    second, again = complete(context,renamed)
    assert all(r['classification'] == 'UNCHANGED' and r['proposed_action'] == 'NO_OP'
               for r in second['preview']['rows'])
    with Session(context[0][1]) as fresh:
        assert {p.name:str(p.id) for p in fresh.scalars(select(Product))} == ids
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == versions
        retained = fresh.get(ImportBatch,UUID(renamed)).analysis_json['completion']
        assert {r['canonical_id'] for r in retained['canonical_references']} == set(ids.values())
        assert [b['version'] for b in retained['mapping_bindings']] == [b['version'] for b in done['mapping_bindings']]
        assert fresh.scalar(select(Product).where(Product.name == records[1]['name'])).active is False
    save('synthetic-menu-capability',dict(outcome='SYNTHETIC_ONLY_NOT_ORIGINAL_MENU_COMPLETION',
        records=records, canonical_ids=ids, first=done, renamed_reexport=again,
        limits='Explicit separate synthetic facts; cannot replace missing original sources or status declarations'))


def test_original_menu_product_values_owner_commit_exact_facts_and_renamed_reexport(fresh_store,monkeypatch,i5_trace):
    from tests.integration.test_import_product_values import values
    from tests.integration.test_import_field_value_bindings import activate
    from tests.integration.test_import_rule_review import declare_context
    c,ident,records,digest,path,cells,sheet=prepare_original_menu(fresh_store,monkeypatch,
        source_system_key='USER_SYNTHETIC_MENU')
    scope,=summary(c,ident)['product_value_scopes']
    assert not scope['unresolved_tokens'] and len(scope['products'])==10
    ids={p['source_token']:p['product_id'] for p in scope['products']}
    assert all(p['reference_state']=='reserved' for p in scope['products'])
    for target in ('sku','active'):
        entries=[dict(product_id=ids[r['source_key']],value=r['declared_'+target]) for r in records]
        extra=dict(replace_source_column_index=9,acknowledgment=True) if target=='active' else {}
        response=values(c,ident,target,entries,**extra)
        assert response.status_code==200 and response.json()['data']['approval_required'],response.text
    proposal,=summary(c,ident)['profile_proposals']
    assert not proposal['missing_fields'] and len(proposal['spec']['entity_proposals'])==10
    activate(c,ident)
    read=previewed(c,ident)
    assert len(read['preview']['rows'])==10 and not read['preview']['summary']['blockers'],read
    for preview in read['preview']['rows']:
        expected,=[r for r in records if r['source_key']==preview['after']['source_business_key']]
        assert preview['after']['active'] is expected['declared_active']
        assert preview['after']['sku']==expected['declared_sku']
        assert preview['provenance']['active']['value_source']=='IMPORT_VALUE'
        assert preview['provenance']['sku']['declaration_id']
    confirmation=confirm(c,ident,read)
    assert confirmation.status_code==200,confirmation.text
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product))==0
    first=finished(c,ident,commit(c,ident,read,confirmation.json()['data']['import_revision']))
    def exact(fresh):
        assert fresh.scalar(select(func.count()).select_from(Product))==10
        assert fresh.scalar(select(func.count()).select_from(Recipe))==0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily))==0
        for r in records:
            product=fresh.get(Product,UUID(ids[r['source_key']]))
            assert product.store_id==c[1].store_id and product.name==r['name']
            assert product.selling_unit==r['unit'] and product.price==int(r['price'])
            assert product.sku==r['declared_sku'] and product.active is r['declared_active']
    with Session(c[0][1]) as fresh:
        exact(fresh)
        batch=fresh.get(ImportBatch,UUID(ident))
        assert {r['canonical_id'] for r in batch.analysis_json['completion']['canonical_references']}==set(ids.values())
        assert [r['row_number'] for r in batch.analysis_json['sources'][0]['rows']]==list(range(4,14))
        for row in batch.analysis_json['sources'][0]['rows']:
            assert {cell['column_index']:cell['raw'] for cell in row['cells']}=={
                n:cells[f'{letter}{row["row_number"]}'] for n,letter in enumerate('ABCDEFGHIJ')}
    second=upload_declared_pos(c,path,filename='menu-reexport-renamed.xlsx')
    declare_context(c,second,dict(source_system_key='USER_SYNTHETIC_MENU',report_type='PRODUCT_CATALOG',
        sales_semantics=None,
        evidence_reference='Same user-created synthetic Menu baseline 08/07/2026; same source/report regardless of upload name'))
    m=summary(c,second)
    assert m['binding_refs'] and not m['can_preview'] and not m['sheets'][0]['import_values']
    assert {d['target_field'] for d in m['completion_guidance']['declarations']}=={'products.sku','products.active'}
    for target in ('sku','active'):
        entries=[dict(product_id=ids[r['source_key']],value=r['declared_'+target]) for r in records]
        response=values(c,second,target,entries)
        assert response.status_code==200 and not response.json()['data']['approval_required'],response.text
    _,again=complete(c,second)
    assert again['outcome']=='no_changes'
    with Session(c[0][1]) as fresh:
        exact(fresh)
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    save('original-menu-m2-committed',dict(outcome='SOURCE_FAITHFUL_USER_SYNTHETIC_MENU_CATALOG_COMMITTED',
        original_sha256=digest,scope='All ten original Menu rows, catalog only; no recipes/discount facts; fresh isolated Store',
        source_system_key='USER_SYNTHETIC_MENU',report_type='PRODUCT_CATALOG',ids=ids,
        decisions=records,first=first,renamed_reexport=again,
        limits='Canonical assertions before supported test cleanup; no real Store/provider/FE acceptance'))
