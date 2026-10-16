"""Synthetic retained projection, not a real Run or a forecast accuracy oracle."""
import json
from copy import deepcopy
from datetime import date
from fractions import Fraction
from pathlib import Path
from uuid import UUID
from app.application.contracts.planning_pdf import PlanningPDFDocument
from app.application.planning_public_projection import quantity

ROOT = Path(__file__).resolve().parents[2] / 'docs/features/examples'


def owner_document() -> PlanningPDFDocument:
    view = json.loads((ROOT / 'planning_public/c03_completed_response.json').read_text(encoding='utf-8'))['data']
    detail = json.loads((ROOT / 's410/c05_response.json').read_text(encoding='utf-8'))['data']
    explanation = json.loads((ROOT / 's410/c08_response.json').read_text(encoding='utf-8'))['data']
    q = lambda n: quantity(Fraction(n)).model_dump(mode='json')
    pid = view['scope']['menu_products'][0]['product_id']
    view['scope']['menu_products'][0]['name'] = 'Cà phê sữa đá đặc biệt'
    option = deepcopy(view['result']['options'][0])
    oid = option['option_id']
    costs = [Fraction(420000), Fraction(360000), Fraction(575000)]
    names = ['Cà phê rang xay nguyên chất', 'Sữa tươi không đường', 'Đường mía vàng']
    units = ['g', 'ml', 'g']
    purchases, details = [], []
    for index, (cost, name, unit) in enumerate(zip(costs, names, units), 1):
        iid, sid, tid = (str(UUID(int=100 * index + n)) for n in (1, 2, 3))
        purchase = dict(supplier_term_id=tid, supplier_id=sid, ingredient_id=iid, unit=unit,
                        packs=2, quantity=q(2000), arrival_date='2026-10-10', expiry_date=None,
                        purchase_outlay=q(cost), payable_fee_components=[])
        purchases.append(purchase)
        item = deepcopy(detail)
        item.update(run_id=view['run_id'], result_digest=explanation['result_digest'], ingredient_id=iid,
                    selected_option_id=oid, display_name=name, unit=unit, purchases=[purchase], related_products=[], issues=[])
        item['captured_stock']['provenance'] = 'synthetic_fixture/1'
        item['daily_balances'] = []
        # Exact explicit fixture balance: 2000 incoming on day1, consume 5/day.
        for path in ('LOW', 'BASE', 'HIGH'):
            for day in range(7):
                item['daily_balances'].append(dict(path=path, day=date(2026, 10, 10 + day).isoformat(), unit=unit,
                    requested=q(5), available=q(2000 - 5 * day), shortage=q(0), consumed=q(5), expired=q(0),
                    other_waste=q(0), ending=q(1995 - 5 * day), incoming_quantity=q(2000 if day == 0 else 0)))
        details.append(item)
    option['purchases'] = purchases
    option['costs'] = dict(currency='VND', purchase=q(sum(costs)), payable_fees=q(25000), delivery_fees=None,
        fee_classification='PAYABLE_FEE_TYPE_NOT_CAPTURED', total=q(sum(costs) + 25000),
        fee_components=[dict(basis='SUPPLIER_ORDER', entity_id=purchases[0]['supplier_id'], amount=q(25000))])
    option['product_services'] = [dict(product_id=pid, unit='cup', path=path, requested=q(35), fulfilled=q(35), lost_sales=q(0),
        service=dict(numerator='1', denominator='1', percent_view='100')) for path in ('LOW', 'BASE', 'HIGH')]
    option['ingredient_balances'] = [dict(ingredient_id=p['ingredient_id'], unit=p['unit'], path=path,
        consumed=q(35), expired=q(0), ending_usable=q(1965)) for p in purchases for path in ('LOW', 'BASE', 'HIGH')]
    option['issues'] = []
    view['result']['options'] = [option]
    view['result']['winner_option_id'] = oid
    view['configuration']['budget'].update(limit='2000000', ceiling_at_acceptance='2000000')
    explanation.update(run_id=view['run_id'], winner=dict(option_id=oid, reason_code='WINNER_FOUND'), options=[])
    return PlanningPDFDocument.model_validate(dict(view=view, option=option, ingredients=details,
                                                   explanation=explanation, source_evidence=None))


def representative_document() -> PlanningPDFDocument:
    """Same small report dimensions as the supplied PDF: 5 dishes, 7 inputs,
    6 purchase lines. Explicit synthetic projection, not the user's original Run.
    """
    data = owner_document().model_dump(mode='json')
    q = lambda n: quantity(Fraction(n)).model_dump(mode='json')
    option = data['option']
    names = ['Cà phê rang xay', 'Sữa tươi', 'Sữa đặc', 'Trà ô long', 'Siro đào', 'Siro vải', 'Đường mía']
    costs = [400000, 300000, 315000, 2500000, 360000, 360000]
    units = ['g', 'ml', 'ml', 'g', 'ml', 'ml', 'g']
    purchases, ingredients = [], []
    for i, (name, unit) in enumerate(zip(names, units)):
        iid = str(UUID(int=10001 + i))
        purchase = deepcopy(option['purchases'][0])
        purchase.update(ingredient_id=iid, unit=unit, supplier_id=str(UUID(int=30001)),
                        supplier_term_id=str(UUID(int=20001 + i)), expiry_date='2027-01-14')
        if i < 6:
            purchase['purchase_outlay'] = q(costs[i])
            purchases.append(purchase)
        detail = deepcopy(data['ingredients'][0])
        detail.update(ingredient_id=iid, display_name=name, unit=unit, purchases=[purchase] if i < 6 else [])
        for row in detail['daily_balances']:
            row['unit'] = unit
        if i == 6:
            detail['captured_stock']['scope_declaration'] = 'COMPLETE_CURRENT_LOTS'
            detail['captured_stock']['lots'] = [dict(lot_id=str(UUID(int=50001)),quantity=q(2000),unit=unit,
                received_date='2026-10-09',expiry_date=None,supplier_id=None,unit_cost=None,cost_availability='unknown')]
            for row in detail['daily_balances']:
                row['incoming_quantity'] = q(0)
        ingredients.append(detail)
    option['purchases'] = purchases
    option['costs'].update(purchase=q(sum(costs)), total=q(sum(costs)), payable_fees=q(0),
                          delivery_fees=q(0), fee_classification='NONE', fee_components=[])
    dishes = ['Cà phê sữa đá', 'Bạc xỉu', 'Trà đào cam sả', 'Trà vải', 'Trà sữa ô long']
    products = [dict(product_id=str(UUID(int=40001 + i)),name=name,selling_unit='cup') for i,name in enumerate(dishes)]
    services, assessments = [], []
    for i, product in enumerate(products):
        for path in ('BASE','LOW','HIGH'):
            demand = Fraction(70 * (i + 1))
            ratio = Fraction(99,100) if path == 'BASE' else Fraction(1) if path == 'LOW' else Fraction(9,10)
            fulfilled = demand * ratio
            services.append(dict(product_id=product['product_id'],unit='cup',path=path,requested=q(demand),
                fulfilled=q(fulfilled),lost_sales=q(demand-fulfilled),service=dict(numerator=str(ratio.numerator),
                denominator=str(ratio.denominator),percent_view=quantity(ratio*100).decimal_view)))
        assessments.append(dict(product_id=product['product_id'],path='BASE',target_percent='95',applied_source='common',status='PASS',shortfall=q(0)))
    option.update(product_services=services, requirements_assessment=assessments, ingredient_balances=[])
    data['view']['scope'].update(menu_products=products,computed_product_ids=[p['product_id'] for p in products],menu_count=5,computed_count=5)
    data['view']['configuration']['budget'].update(limit='10000000',ceiling_at_acceptance='10000000')
    data['view']['result']['options'] = [deepcopy(option)]
    data['ingredients'] = ingredients
    return PlanningPDFDocument.model_validate(data)
