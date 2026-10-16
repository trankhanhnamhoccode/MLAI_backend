"""Deterministic fictional cafe inputs. Does not read original workbooks or any DB."""
from datetime import date, timedelta
from pathlib import Path
from hashlib import sha256
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests/fixtures/synthetic_cafe_v1'
D = date(2026, 10, 17)
START = D-timedelta(days=181)
SYSTEM = 'SYNTHETIC_CAFE_V1'
STAMP = '2026-10-17T23:59:59+07:00'
EVIDENCE = 'SYNTHETIC_CAFE_V1: entirely fictional; not extracted from July08 original workbooks'
PRODUCTS = [
    ('Sinh tố dâu size S', 35000, 18, {'Dâu nghiền':100,'Sữa tươi':100,'Đường':10,'Ly giấy':1}),
    ('Sinh tố dâu size L', 45000, 12, {'Dâu nghiền':150,'Sữa tươi':150,'Đường':15,'Ly giấy':1}),
    ('Cà phê sữa nóng', 30000, 20, {'Cà phê rang':18,'Sữa tươi':50,'Đường':8,'Ly giấy':1}),
    ('Cà phê sữa lạnh', 35000, 16, {'Cà phê rang':20,'Sữa tươi':80,'Đường':10,'Ly giấy':1}),
]
# All assumptions below are fictional and fixed before the external week's draw.
INGREDIENTS = [
    ('Dâu nghiền','ml',6000,1000,60000,200000,100000),
    ('Sữa tươi','ml',6000,1000,30000,200000,150000),
    ('Cà phê rang','g',1000,1000,200000,30000,15000),
    ('Đường','g',1000,1000,20000,50000,20000),
    ('Ly giấy','piece',100,100,90000,5000,2000),
]
SUPPLIER = 'Nhà cung cấp giả Cafe V1'


def demand(day, name, base):
    # No fitted statistics, holdout reads, stock or model outputs in this generator.
    noise=int.from_bytes(sha256(f'cafe-v1-sales|{day}|{name}'.encode()).digest()[:2],'big')%7-3
    weekday=(0,1,0,2,3,6,5)[day.weekday()]
    trend=(day-START).days//42
    return max(1,base+weekday+trend+noise)


def dataset(sufficient=False):
    products=[dict(source_business_key=name,name=name,selling_unit='cup',sku=f'SYN-SKU-P{i+1:02}',price=price,active=True)
              for i,(name,price,_,_) in enumerate(PRODUCTS)]
    ingredients=[dict(source_business_key=name,name=name,base_unit=unit,sku=f'SYN-SKU-I{i+1:02}',expiry_tracking=unit!='piece',active=True)
                 for i,(name,unit,*_) in enumerate(INGREDIENTS)]
    suppliers=[dict(source_supplier_key=SUPPLIER,name=SUPPLIER,active=True)]
    recipes=[dict(product_id=name,ingredient_id=ing,version=1,effective_from=str(START),effective_to=None,
                  quantity_basis='PER_SERVING',yield_quantity=1,yield_unit='cup',process_loss_rate=0,quantity=q,
                  unit=next(i[1] for i in INGREDIENTS if i[0]==ing))
             for name,_,_,lines in PRODUCTS for ing,q in lines.items()]
    sales=[];usage=[];purchases=[];lots=[];daily=[]
    for offset in range(182):
        day=START+timedelta(days=offset)
        consumed={name:0 for name,*_ in INGREDIENTS}
        for name,_,base,lines in PRODUCTS:
            q=demand(day,name,base)
            sales.append(dict(product_id=name,sales_date=str(day),quantity=q,unit='cup',business_report_key='CAFE_V1_DAILY_TOTAL',is_stockout=False))
            for ing,rate in lines.items():consumed[ing]+=q*rate
        for ix,(name,unit,nominal,pack,cost,capacity,extra) in enumerate(INGREDIENTS):
            before=sum(l['remaining'] for l in lots if l['name']==name)
            # Order at yesterday's close, using only the then-known balance.
            # Every historical delivery also respects the declared pack and MOQ.
            shortage=max(0,3*nominal-before)
            received=pack*max(2,(shortage+pack-1)//pack) if shortage else 0
            deliveries=[(f'SYN-LOT-{ix+1:02}-{day:%Y%m%d}',received)] if received else []
            if sufficient and day==D:deliveries.append((f'SYN-TOPUP-{ix+1:02}-{day:%Y%m%d}',extra))
            for key,qty in deliveries:
                expiry=day+timedelta(days=14) if unit!='piece' else None
                lots.append(dict(key=key,name=name,unit=unit,received=str(day),expiry=str(expiry) if expiry else None,
                                 quantity=qty,remaining=qty,consumed=0,expired=0,unit_cost=cost//pack))
                purchases.append(dict(source_record_key=key,evidence_reference=EVIDENCE+'; physical lot='+key,
                    ingredient_id=name,supplier_id=SUPPLIER,quantity=qty,unit=unit,order_date=str(day-timedelta(days=1)),
                    received_date=str(day),report_date=str(day),price=cost//pack,price_basis='PER_QUANTITY',
                    price_quantity=1,price_unit=unit,currency='VND'))
            expired=0
            for lot in lots:
                if lot['name']==name and lot['expiry'] and lot['expiry']<str(day):
                    expired+=lot['remaining'];lot['expired']+=lot['remaining'];lot['remaining']=0
            remaining=consumed[name]
            for lot in sorted((l for l in lots if l['name']==name),key=lambda l:(l['expiry'] or '9999',l['received'],l['key'])):
                used=min(remaining,lot['remaining']);lot['remaining']-=used;lot['consumed']+=used;remaining-=used
            assert remaining==0,(day,name,'stockout')
            closing=sum(l['remaining'] for l in lots if l['name']==name)
            assert before+sum(q for _,q in deliveries)-expired-consumed[name]==closing
            assert before+sum(q for _,q in deliveries)<=capacity
            daily.append(dict(day=str(day),ingredient=name,unit=unit,opening=before,received=sum(q for _,q in deliveries),
                              consumed=consumed[name],expired=expired,closing=closing))
            usage.append(dict(source_record_key=f'USE-{ix+1:02}-{day:%Y%m%d}',evidence_reference=EVIDENCE,
                              ingredient_id=name,usage_date=str(day),observed_at=str(day)+'T22:00:00+07:00',quantity=consumed[name],unit=unit))
    opening=[dict(source_record_id=l['key'],ingredient_id=l['name'],supplier_id=SUPPLIER,lot_code=l['key'],
                  quantity=l['remaining'],unit=l['unit'],received_date=l['received'],expiry_date=l['expiry'],unit_cost=l['unit_cost'],
                  currency='VND',observed_at=STAMP,reason=EVIDENCE+'; physical opening baseline at cutoff, not a new receipt')
             for l in lots if l['remaining']>0]
    terms=[dict(source_term_key=f'SYN-TERM-{ix+1:02}',supplier_id=SUPPLIER,ingredient_id=name,effective_from=str(START),effective_to=None,
        unit=unit,pack_size_base_quantity=pack,pack_cost=cost,currency='VND',price_basis='PER_PACK',price_quantity=None,price_unit=None,
        moq_basis='PACKS',minimum_order_quantity=2,moq_unit=None,lead_time_days=1,shelf_life_days=14 if unit!='piece' else None,
        active=True,maximum_order_base_quantity=capacity)
        for ix,(name,unit,nominal,pack,cost,capacity,extra) in enumerate(INGREDIENTS)]
    fees=[dict(source_fee_key='SYN-NO-FEES',scope='STORE_PROCUREMENT',effective_from=str(START),effective_to=None,
        mode='NONE',coverage='COMPLETE',currency='VND',components=[],covered_source_term_keys=[t['source_term_key'] for t in terms],
        covered_source_supplier_keys=[SUPPLIER],evidence_reference=EVIDENCE,reason='Fictional supplier includes all delivery fees in pack price')]
    declarations=[dict(source_declaration_key=f'SYN-STOCK-{ix+1:02}',declaration=dict(kind='INVENTORY',ingredient_id=name,
        state='COMPLETE_CURRENT_LOTS',observed_at=STAMP,covered_lot_ids=[l['lot_code'] for l in opening if l['ingredient_id']==name],
        evidence_reference=EVIDENCE)) for ix,(name,*_) in enumerate(INGREDIENTS)]
    declarations.append(dict(source_declaration_key='SYN-SALES-COVERAGE',declaration=dict(kind='SALES_COVERAGE',
        product_ids=[p['name'] for p in products],from_date=str(START),to_date=str(D),state='COMPLETE',evidence_reference=EVIDENCE)))
    declarations.append(dict(source_declaration_key='SYN-PROCUREMENT',declaration=dict(kind='PROCUREMENT_CONTEXT',
        effective_from=str(D+timedelta(days=1)),effective_to=None,committed_inbound_state='CONFIRMED_NONE',
        no_additional_orders_state='CONFIRMED_NONE',capacity_state='DECLARED',capacities=[dict(ingredient_id=name,unit=unit,
            maximum_quantity=str(capacity),checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION')
            for name,unit,nominal,pack,cost,capacity,extra in INGREDIENTS],
        supplier_limit_state='DECLARED',supplier_limits=[dict(supplier_id=SUPPLIER,ingredient_id=name,unit=unit,
            maximum_quantity=str(capacity),scope='ONE_ORDER_SUPPLIER_INGREDIENT') for name,unit,nominal,pack,cost,capacity,extra in INGREDIENTS],
        evidence_reference=EVIDENCE)))
    sheets=dict(products=products,ingredients=ingredients,suppliers=suppliers,recipes=recipes,sales=sales,
                usage_history=usage,purchase_history=purchases,opening_stock=opening,supplier_terms=terms,payable_fees=fees,scope_declarations=declarations)
    for l in lots:assert l['quantity']==l['consumed']+l['expired']+l['remaining']
    return sheets,daily,lots


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    main_sheets,daily,lots=dataset();full_sheets,full_daily,full_lots=dataset(True)
    actuals=[dict(product_id=name,sales_date=str(D+timedelta(days=h)),quantity=demand(D+timedelta(days=h),name,base),
                  unit='cup',business_report_key='CAFE_V1_EXTERNAL_LOCKED',is_stockout=False)
             for h in range(1,8) for name,_,base,_ in PRODUCTS]
    origins=[START+timedelta(days=n) for n in range(41,182-7,7)]
    manifest=dict(dataset_label='SYNTHETIC',version=1,source_system_key=SYSTEM,history_start=str(START),cutoff=str(D),
        cutoff_timestamp=STAMP,forecast_start=str(D+timedelta(days=1)),external_end=str(D+timedelta(days=7)),
        history_days=182,external_days=7,validation_origins=list(map(str,origins[:len(origins)//2])),
        internal_holdout_origins=list(map(str,origins[len(origins)//2:])),
        policy='Freeze model/family/configuration using only input history; external actuals may be opened only after predictions are frozen.',
        scenarios=dict(main=dict(file='01_main_at_cutoff.xlsx',budget='5000000',expected='purchase_required_winner'),
            sufficient=dict(file='02_sufficient_at_cutoff.xlsx',budget='5000000',expected='no_purchase_winner'),
            insufficient_budget=dict(file='01_main_at_cutoff.xlsx',budget='1',expected='no_winner')),
        origin='All fields, SKU, IDs, names, metadata, prices, receipt dates and stock are newly fabricated. Original workbooks untouched.',
        import_policy='Import data sheets excluding Scope first; then import Scope only and bind exact current Store lot IDs. History is record-only. Never import receipt history as stock alongside opening snapshot.',
        missing_policy='Explicit recipe loss0, yield1 and version1 are fictional source facts. Null recipe end date and packaging expiry intentional.',
        procurement='MOQ2 packs, lead1 day, shelf14 days for foods, explicit capacity and per-supplier limits, known zero delivery fees. Future actual receipts/orders are not inputs.',
        timeline_adjustment='Initial July08 prototype blocked by current stock freshness against DB write timestamps. Fixed new fictional cutoff Oct17, with declarations after actual DB creation on that Store day; no guard changes.',
        historical_order_policy='Order at prior close to restore three nominal days of stock; round up to whole packs, MOQ2. No future sales in ordering. Initial prototype used base-unit bulk deliveries; revised to make every historical delivery obey the same pack/MOQ. No external-week scores informed this change.',
        baseline_policy='Current supported operator configuration is BASELINE; trained candidate evaluation is a separate trusted internal path, not silently activated.')
    payload=dict(manifest=manifest,workbooks={'01_main_at_cutoff.xlsx':main_sheets,'02_sufficient_at_cutoff.xlsx':full_sheets,
        '03_external_week_locked.xlsx':{'sales':actuals},'04_inventory_reconciliation.xlsx':{
            'main_daily':daily,'main_lots':lots,'sufficient_daily':full_daily,'sufficient_lots':full_lots}})
    (OUT/'dataset.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(history_days=182,external_days=7,main_rows={k:len(v) for k,v in main_sheets.items()},
        origins=len(origins)),indent=2))


if __name__=='__main__':main()
