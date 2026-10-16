"""Original July baseline inspection; absent declarations must never become facts."""
import hashlib
import re
import json
from pathlib import Path
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contracts.import_scalars import Quantity
from app.models import Ingredient, Product, Recipe, RecipeLine, InventoryLot
from app.models.import_staging import ImportBatch, ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store, complete
from tests.integration.test_import_menu_acceptance import prepare_original_menu
from tests.integration.test_import_product_values import values
from tests.integration.test_import_field_value_bindings import activate
from tests.integration.test_import_i51_pos_declared import upload_declared_pos
from tests.integration.test_import_classification import listing, mapping
from tests.integration.test_import_rule_review import summary
from tests.integration.test_import_staging import post
from tests.integration.test_import_staging import previewed
from tests.integration.test_import_rule_review import declare_context
from tests.integration.test_import_classification import confirm
from tests.integration.test_import_commit import commit, finished
from app.domain.demand.bom import DemandPoint, DatedRecipe, RecipeLine as BOMLine, expand_dated_bom
from app.application.readiness_evaluation import recipe_dependencies
from tests.integration.import_i5_evidence import CASES, SOURCE_DIRECTORY, cells_by_sheet, save, i5_trace


def original_recipe():
    case = next(c for c in CASES if c['file'] == '04_RECIPES_BUSINESS_RULES.xlsx')
    path = SOURCE_DIRECTORY / case['file']
    assert path.is_file(), 'Exact original recipe workbook required; do not substitute another baseline'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']
    return path, case, cells_by_sheet(path)


def test_original_recipe_owner_atomic_commit_exact_bom_and_renamed_reexport(fresh_store, monkeypatch, i5_trace):
    c, ident, menu_id, path, case, sheets, recipe_sheet, _, bound_products = prepare_original_recipes(fresh_store, monkeypatch)
    approved=json.loads((Path(__file__).parents[1]/'fixtures/import_recipe_declarations.json').read_text(encoding='utf-8'))
    assert approved['recipe_sha256']==case['sha256']
    cells=sheets[case['sheets'][0]]
    ingredient_units={cells[f'B{r}']:cells[f'D{r}'] for r in range(4,23)}
    assert set(ingredient_units)==set(approved['ingredients_by_full_name'])
    for item in listing(c,ident):
        if item['sheet_id']==recipe_sheet['sheet_id'] and item['issue_type']=='identity' and item['source_location']['source_column_index']==1:
            name=item['source_header']
            response=mapping(c,ident,item,{'resolution':dict(kind='new_entity_proposal',entity='ingredient',
                source_business_key=name,metadata=dict(name=name,base_unit=ingredient_units[name],
                    **approved['ingredients_by_full_name'][name]),evidence_reference=approved['evidence'])})
            assert response.status_code==200,response.text
    source_context=dict(source_system_key=approved['source_system_key'],report_type=approved['report_type'],
        sales_semantics=None,date_format='EXCEL_SERIAL',recipe_quantity_format='OOXML_FINITE_DECIMAL',
        evidence_reference='User-created synthetic July08 baseline; source A2/C3 per serving, E/F yield, G version, H date; reviewed exact OOXML quantity policy')
    declare_context(c,ident,source_context)
    proposal,=summary(c,ident)['profile_proposals']
    assert proposal['spec']['source_provenance']['declared_by']==str(c[1].user_id)
    reservations=proposal['spec']['entity_proposals']
    assert len(reservations)==10 and all(r['entity']=='ingredient' for r in reservations)
    assert all(r['evidence_reference']==approved['evidence'] for r in reservations)
    assert not proposal['missing_fields'] and not summary(c,ident)['can_preview']
    assert not any(r['target_field'] in {'recipes.process_loss_rate','recipes.effective_to'}
        for r in proposal['spec']['shared_field_bindings'])
    activate(c,ident)
    read=previewed(c,ident)
    assert read['preview']['summary']['policy_version']=='import_mapping_policy/2'
    assert not read['preview']['summary']['blockers'],read
    recipe_rows=[r for r in read['preview']['rows'] if r['after']['domain']=='recipes']
    assert len(recipe_rows)==5 and sum(len(r['line_provenance']) for r in recipe_rows)==19
    assert len(read['preview']['rows'])==15
    for row in read['preview']['rows']:
        if row['after']['domain']=='ingredients':
            metadata=approved['ingredients_by_full_name'][row['after']['name']]
            for field in ('sku','active','expiry_tracking'):
                p=row['provenance'][field]
                assert p['origin']=='SOURCE_EXPLICIT' and p['value_source']=='IDENTITY_BINDING'
                assert p['source_value']==metadata[field] and not p['source_missing']
                assert p['applied_rule_ids'] and p['applied_rule_ids'][0].startswith('entity_proposal:')
    for row in recipe_rows:
        assert row['after']['process_loss_rate']=='0' and row['after']['effective_to'] is None
        assert {w['code'] for w in row['warnings']}=={'RECIPE_PROCESS_LOSS_DEFAULTED_ZERO'}
        for line in row['line_provenance']:
            loss=line['provenance']['process_loss_rate']
            assert loss['origin']=='SYSTEM_DEFAULT' and loss['source_missing'] and loss['source_value'] is None
            assert loss['declaration_id'] is None and loss['value_source']=='SYSTEM_DEFAULT'
    confirmation=confirm(c,ident,read);assert confirmation.status_code==200,confirmation.text
    with Session(c[0][1]) as fresh:
        for model in (Ingredient,Recipe,RecipeLine):
            assert fresh.scalar(select(func.count()).select_from(model))==0
    from uuid import uuid4
    key=str(uuid4())
    accepted=commit(c,ident,read,confirmation.json()['data']['import_revision'],key=key)
    first=finished(c,ident,accepted)
    replay=commit(c,ident,read,confirmation.json()['data']['import_revision'],key=key)
    assert replay.status_code==202 and replay.json()['data']==accepted.json()['data']
    expected_by_product={}
    for row in range(4,23):
        expected_by_product.setdefault(cells[f'A{row}'],{})[cells[f'B{row}']]=Decimal(cells[f'C{row}'])
    def exact(fresh):
        assert fresh.scalar(select(func.count()).select_from(Product))==10
        assert fresh.scalar(select(func.count()).select_from(Ingredient))==10
        assert fresh.scalar(select(func.count()).select_from(Recipe))==5
        assert fresh.scalar(select(func.count()).select_from(RecipeLine))==19
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==0
        ingredients={i.name:i for i in fresh.scalars(select(Ingredient))}
        for name,i in ingredients.items():
            assert i.store_id==c[1].store_id and i.base_unit==ingredient_units[name]
            assert i.sku is None and i.active and i.expiry_tracking is approved['ingredients_by_full_name'][name]['expiry_tracking']
        saved=[]
        for name,product_id in bound_products.items():
            recipe=fresh.scalar(select(Recipe).where(Recipe.product_id==UUID(product_id)))
            assert recipe.version==1 and recipe.effective_from==date(2026,6,1) and recipe.effective_to is None
            assert recipe.yield_quantity==1 and recipe.process_loss_rate==0
            lines=fresh.scalars(select(RecipeLine).where(RecipeLine.recipe_id==recipe.id)).all()
            expected=expected_by_product[name]
            assert {line.ingredient_id:line.quantity for line in lines}=={ingredients[n].id:q for n,q in expected.items()}
            assert all(line.unit==fresh.get(Ingredient,line.ingredient_id).base_unit for line in lines)
            saved.append(DatedRecipe(recipe.id,recipe.product_id,recipe.effective_from,recipe.effective_to,
                recipe.yield_quantity,recipe.process_loss_rate,tuple(BOMLine(l.ingredient_id,l.unit,l.quantity) for l in lines)))
        # Independent expected demand from raw source values, not preview/normalizer output.
        demand=tuple(DemandPoint('BASE',UUID(pid),date(2026,7,8),Decimal(40)) for pid in bound_products.values())
        bom=expand_dated_bom(demand,tuple(saved));assert not bom.gaps
        expected_totals={}
        for recipe in expected_by_product.values():
            for name,quantity in recipe.items():
                expected_totals[name]=expected_totals.get(name,Fraction())+40*Fraction(quantity)
        actual={next(name for name,i in ingredients.items() if i.id==t.ingredient_id):Fraction(t.quantity) for t in bom.totals}
        assert actual==expected_totals
        snapshot=dict(ingredients=[dict(id=str(i.id),base_unit=i.base_unit) for i in ingredients.values()],
            recipes=[dict(id=str(r.recipe_id),product_id=str(r.product_id),assigned=True,effective_from=str(r.effective_from),
                effective_to=None,yield_quantity=str(r.yield_quantity),process_loss_rate=str(r.loss)) for r in saved],
            recipe_lines=[dict(recipe_id=str(r.recipe_id),ingredient_id=str(l.ingredient_id),quantity=str(l.quantity),unit=l.unit)
                for r in saved for l in r.lines])
        for pid in bound_products.values():
            assert not recipe_dependencies(snapshot,dict(id=pid),(date(2026,7,8),))[1]
        return {name:str(q) for name,q in actual.items()}
    with Session(c[0][1]) as fresh:
        bom_totals=exact(fresh)
        version=fresh.scalar(select(ImportProfileVersion).where(ImportProfileVersion.source_system_key==approved['source_system_key']))
        assert version.approved_by==c[1].user_id and version.spec_json['source_provenance']['owner_reviewed']
        batch=fresh.get(ImportBatch,UUID(ident))
        original=next(s for s in batch.analysis_json['sources'] if s['sheet_id']==recipe_sheet['sheet_id'])
        assert len(original['rows'])==19
        for row in original['rows']:
            assert {cell['column_index']:cell['raw'] for cell in row['cells']}=={
                n:cells[f'{letter}{row["row_number"]}'] for n,letter in enumerate('ABCDEFGH')}
        refs=batch.analysis_json['completion']['canonical_references']
        for ref in refs:
            if ref['canonical_domain']=='ingredients':
                ingredient=fresh.get(Ingredient,UUID(ref['canonical_id']))
                for field in ('sku','active','expiry_tracking'):
                    assert ref['provenance'][field]['source_value']==approved['ingredients_by_full_name'][ingredient.name][field]
        assert all(line['provenance']['process_loss_rate']['origin']=='SYSTEM_DEFAULT'
            for ref in refs if ref['canonical_domain']=='recipes' for line in ref['line_provenance'])
    second=upload_declared_pos(c,path,filename='same-recipe-renamed.xlsx')
    state=summary(c,second)
    rules=next(s for s in state['sheets'] if s['name']==case['sheets'][1])
    item=next(i for i in listing(c,second) if i['sheet_id']==rules['sheet_id'] and i['issue_type']=='classification')
    assert mapping(c,second,item,{'resolution':dict(kind='sheet_type',sheet_type=None,ignored=True,acknowledgment=True,
        reason='Same explicit recipe-only scope; operational rules remain raw')}).status_code==200
    declare_context(c,second,source_context)
    state=summary(c,second)
    assert state['binding_refs'] and not state['can_preview']
    sheet=next(s for s in state['sheets'] if s['name']==case['sheets'][0])
    item=next(i for i in listing(c,second) if i['sheet_id']==sheet['sheet_id'] and i['issue_type']=='source_context')
    assert mapping(c,second,item,{'resolution':dict(kind='shared_value',scope='IMPORT_VALUE',target_field='recipes.quantity_basis',
        value='PER_SERVING',evidence_reference='Re-read current source A2/C3; no reused batch declarations')}).status_code==200
    _,again=complete(c,second)
    assert again['outcome']=='no_changes'
    with Session(c[0][1]) as fresh:exact(fresh)
    save('original-recipes-committed',dict(outcome='SOURCE_FAITHFUL_SYNTHETIC_JULY08_RECIPES_COMMITTED',
        original_sha256=case['sha256'],ingredients=10,recipes=5,recipe_lines=19,first=first,reexport=again,
        bom_40_each_product_exact_rational_totals=bom_totals,
        limits='All19 recipe rows; separate operational sheet26 raw rows excluded. No combo recipes/stock/supplier/Planning acceptance; isolated DB cleanup follows.'))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==case['sha256']


def test_original_recipe_numeric_cells_reveal_unsupported_lexical_form():
    """No rounding or transformed workbook; identify the actual boundary gap."""
    path, case, sheets = original_recipe()
    cells = sheets[case['sheets'][0]]
    adapter = TypeAdapter(Quantity)
    unsupported = {}
    accepted = {}
    for address, value in cells.items():
        if re.fullmatch(r'C[0-9]+', address) and int(address[1:]) > 3:
            try:
                accepted[address] = adapter.validate_python(value)
            except ValidationError:
                unsupported[address] = value
    assert accepted['C4'] == '0.12'
    assert set(unsupported) == {'C10', 'C13', 'C19', 'C21'}
    assert all('E-' in value for value in unsupported.values())
    save('original-recipe-numeric-boundary', dict(original_sha256=case['sha256'],
        supported=accepted, unsupported=unsupported,
        outcome='BLOCKED_LEXICAL_NORMALIZATION_POLICY',
        limits='Scalar contract check only, not preview or canonical recipe acceptance'))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']


def prepare_original_recipes(fresh_store, monkeypatch):
    c, menu_id, records, _, _, _, _ = prepare_original_menu(
        fresh_store, monkeypatch, source_system_key='USER_SYNTHETIC_MENU')
    scope, = summary(c, menu_id)['product_value_scopes']
    ids = {p['source_token']: p['product_id'] for p in scope['products']}
    for target in ('sku', 'active'):
        extra = dict(replace_source_column_index=9, acknowledgment=True) if target == 'active' else {}
        response = values(c, menu_id, target,
            [dict(product_id=ids[r['source_key']], value=r['declared_' + target]) for r in records], **extra)
        assert response.status_code == 200, response.text
    activate(c, menu_id)
    complete(c, menu_id)
    names = {r['name']: ids[r['source_key']] for r in records}

    path, case, sheets = original_recipe()
    ident = upload_declared_pos(c, path)
    current = summary(c, ident)
    recipe = next(s for s in current['sheets'] if s['name'] == case['sheets'][0])
    rules = next(s for s in current['sheets'] if s['name'] == case['sheets'][1])

    def own(kind, sheet=recipe):
        return [i for i in listing(c, ident) if i['sheet_id'] == sheet['sheet_id'] and i['issue_type'] == kind]

    def change(item, body):
        response = mapping(c, ident, item, body)
        assert response.status_code == 200, response.text

    change(own('classification', rules)[0], {'resolution': dict(kind='sheet_type',
        sheet_type=None, ignored=True, acknowledgment=True,
        reason='Recipe-only acceptance scope; business rules remain separate raw evidence, no inventory/supplier/planning writes')})
    change(own('classification')[0], {'resolution': dict(kind='sheet_type', sheet_type='recipes',
        reason='Original one-ingredient-per-row recipe table; all populated rows retained')})
    change(own('source_context')[0], {'resolution': dict(kind='source_context',
        source_system_key='USER_SYNTHETIC_RECIPES', report_type='PRODUCT_RECIPES',
        date_format='EXCEL_SERIAL', evidence_reference=
        'User-created July baseline; proposed stable recipe namespace, not N5 approval; original OOXML date system')})
    targets = ('product_id', 'ingredient_id', 'quantity', 'unit', 'yield_quantity', 'yield_unit', 'version', 'effective_from')
    for column, target in enumerate(targets):
        item = next(i for i in own('column') if i['source_location']['source_column_index'] == column)
        change(item, {'target_field': 'recipes.' + target})
    product_column = 0
    bound_products = {}
    for item in own('identity'):
        if item['source_location']['source_column_index'] == product_column:
            token = item['source_header']
            assert token in names  # Exact full-name lookup, never fuzzy/code/SKU inference.
            change(item, {'resolution': dict(kind='identity_binding', canonical_id=names[token])})
            bound_products[token] = names[token]
    assert len(bound_products) == 5
    change(own('source_context')[0], {'resolution': dict(kind='shared_value', scope='IMPORT_VALUE',
        target_field='recipes.quantity_basis', value='PER_SERVING',
        evidence_reference='Original A2 and C3 explicitly describe ingredient quantity for one Product; no batch assumption')})
    return c, ident, menu_id, path, case, sheets, recipe, rules, bound_products


def test_original_recipe_manual_product_bindings_preserve_rows_and_block_missing_facts(fresh_store, monkeypatch, i5_trace):
    c, ident, menu_id, path, case, sheets, recipe, rules, bound_products = prepare_original_recipes(fresh_store, monkeypatch)

    current = summary(c, ident)
    assert not current['can_preview']
    proposal, = current['profile_proposals']
    assert not {'recipes.process_loss_rate', 'recipes.effective_to'} & set(proposal['missing_fields'])
    ingredient_issues = [i for i in listing(c, ident) if i['sheet_id'] == recipe['sheet_id']
        and i['issue_type'] == 'identity' and i['source_location']['source_column_index'] == 1]
    assert len({i['source_header'] for i in ingredient_issues}) == 10
    batch_read = c[0][5].get('/api/v1/imports/' + ident).json()['data']
    preview = post(c, '/imports/' + ident + '/process',
        dict(phase='preview', mapping_revision=current['mapping_revision']), match=batch_read['import_revision'])
    assert preview.status_code == 409, preview.text
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 10
        for model in (Ingredient, Recipe, RecipeLine):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
        batch = fresh.get(ImportBatch, UUID(ident))
        source = next(s for s in batch.analysis_json['sources'] if s['sheet_id'] == recipe['sheet_id'])
        assert len(source['rows']) == 19
        for row in source['rows']:
            assert {cell['column_index']: cell['raw'] for cell in row['cells']} == {
                index: sheets[case['sheets'][0]][f'{letter}{row["row_number"]}']
                for index, letter in enumerate('ABCDEFGH')}
        rules_source = next(s for s in batch.analysis_json['sources'] if s['sheet_id'] == rules['sheet_id'])
        assert len(rules_source['rows']) == 26
    save('original-recipe-manual-inspection', dict(outcome='BLOCKED_MISSING_BUSINESS_DECLARATIONS',
        original_sha256=case['sha256'], menu_import_id=menu_id, recipe_import_id=ident,
        product_bindings=bound_products, missing_fields=proposal['missing_fields'],
        unresolved_ingredients=sorted({i['source_header'] for i in ingredient_issues}),
        raw_recipe_rows=19, raw_business_rule_rows=26, canonical_ingredients=0, canonical_recipes=0,
        preview_response=preview.json(), limits='No N5/confirm/commit for recipe; no invented metadata/loss/end-date'))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']
