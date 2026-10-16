"""Validate typed XLSX, independent stock conservation, exact BOM and external cutoff; no DB/model fit."""
import sys,json,hashlib
from pathlib import Path
from decimal import Decimal
from datetime import date,datetime,timedelta
from uuid import uuid4,uuid5,NAMESPACE_URL
sys.path.insert(0,str(Path.cwd()));sys.stdout.reconfigure(encoding='utf-8')
from app.infrastructure.import_parser import parse_source
from app.application.import_analysis import discover,build_spec
from app.application.import_preview import normalize
from app.application.contracts import import_mapping as dto
from app.domain.demand.bom import DemandPoint,DatedRecipe,RecipeLine,expand_dated_bom
root=Path('tests/fixtures/synthetic_cafe_v1'); data=json.loads((root/'dataset.json').read_text(encoding='utf-8'));checks={}; hashes={}
for filename,expected in data['workbooks'].items():
 raw=(root/filename).read_bytes();hashes[filename]=hashlib.sha256(raw).hexdigest()
 parsed=parse_source(raw,'xlsx'); tables={s.name:s for s in parsed.sheets if s.name!='SYNTHETIC_README'}
 assert set(tables)==set(expected)
 for name,rows in expected.items():
  assert len(tables[name].rows)==len(rows)+1,(filename,name,len(tables[name].rows),len(rows))
 if 'reconciliation' in filename:continue
 sheets,issues,sources=discover(uuid4(),parsed)
 identity=[]
 for entity,key in [('product','products'),('ingredient','ingredients'),('supplier','suppliers')]:
  for r in data['workbooks']['01_main_at_cutoff.xlsx'][key]:identity.append(dto.IdentityRule(entity=entity,source_token=r['name'],canonical_id=uuid5(NAMESPACE_URL,entity+r['name'])))
 for row in expected.get('opening_stock',[]):identity.append(dto.IdentityRule(entity='lot',source_token=row['lot_code'],canonical_id=uuid5(NAMESPACE_URL,row['lot_code'])))
 for sh in sheets:
  if sh.name=='SYNTHETIC_README':continue
  ctx=dto.ResolveRequest(resolution=dto.SourceContext(kind='source_context',source_system_key='SYNTHETIC_CAFE_V1',report_type='CAFE_INPUT_V1',sales_semantics='daily_total',date_format='EXCEL_SERIAL',evidence_reference='Explicit synthetic facts'))
  own=[i.model_copy(update=dict(status='resolved',resolution=ctx if i.issue_type=='source_context' else None)) for i in issues if i.sheet_id==sh.sheet_id]
  spec,missing=build_spec(sh,own,uuid4(),identities=tuple(identity));assert not missing,(sh.name,missing)
  src=next(s for s in sources if s['sheet_id']==str(sh.sheet_id))
  normalized=[]
  for r in src['rows']:
   try:normalized.append(normalize({**r,'excel_date_system':src.get('excel_date_system')},spec)[0])
   except Exception:
    print('NORMALIZATION FAILED',filename,sh.name,r['row_number'],r['cells']);raise
  assert len(normalized)==len(expected[sh.name]);checks[filename+':'+sh.name]=len(normalized)
main=data['workbooks']['01_main_at_cutoff.xlsx']; led=data['workbooks']['04_inventory_reconciliation.xlsx']
for scenario,prefix in [('01_main_at_cutoff.xlsx','main'),('02_sufficient_at_cutoff.xlsx','sufficient')]:
 w=data['workbooks'][scenario]; usage={(r['usage_date'],r['ingredient_id']):r['quantity'] for r in w['usage_history']}
 rates={p['name']:{} for p in main['products']}
 for r in w['recipes']:rates[r['product_id']][r['ingredient_id']]=r['quantity']
 expected={}
 for s in w['sales']:
  for ing,rate in rates[s['product_id']].items():
   k=(s['sales_date'],ing);expected[k]=expected.get(k,0)+s['quantity']*rate
 assert expected==usage
 for day in led[prefix+'_daily']:
  assert day['opening']+day['received']-day['consumed']-day['expired']==day['closing']
  assert day['consumed']==usage[day['day'],day['ingredient']]
 for lot in led[prefix+'_lots']:assert lot['quantity']==lot['consumed']+lot['expired']+lot['remaining']
 for ing in main['ingredients']:
  name=ing['name'];receipts=sum(r['quantity'] for r in w['purchase_history'] if r['ingredient_id']==name)
  consumed=sum(r['quantity'] for r in w['usage_history'] if r['ingredient_id']==name)
  expired=sum(r['expired'] for r in led[prefix+'_lots'] if r['name']==name)
  balance=sum(r['quantity'] for r in w['opening_stock'] if r['ingredient_id']==name)
  assert receipts-consumed-expired==balance
 assert len({r['source_record_key'] for r in w['purchase_history']})==len(w['purchase_history'])
 terms={r['ingredient_id']:r for r in w['supplier_terms']}
 for purchase in w['purchase_history']:
  term=terms[purchase['ingredient_id']]
  assert purchase['quantity']%term['pack_size_base_quantity']==0
  assert purchase['quantity']//term['pack_size_base_quantity']>=term['minimum_order_quantity']
  assert purchase['price_basis']=='PER_QUANTITY' and purchase['price_quantity']==1
  assert purchase['price_unit']==purchase['unit']==term['unit']
  assert purchase['price']*term['pack_size_base_quantity']==term['pack_cost']
 assert all(r['sales_date']<='2026-10-17' for r in w['sales'])
 assert all(r['received_date']<='2026-10-17' and r['report_date']<='2026-10-17' for r in w['purchase_history'])
# Real pure BOM must reproduce independently summed per-day recorded use.
pids={p['name']:uuid5(NAMESPACE_URL,'product'+p['name']) for p in main['products']};iids={i['name']:uuid5(NAMESPACE_URL,'ingredient'+i['name']) for i in main['ingredients']}
recipes=tuple(DatedRecipe(uuid4(),pid,date(2026,4,19),None,Decimal(1),Decimal(0),tuple(RecipeLine(iids[r['ingredient_id']],r['unit'],Decimal(r['quantity'])) for r in main['recipes'] if r['product_id']==name)) for name,pid in pids.items())
bom=expand_dated_bom(tuple(DemandPoint('BASE',pids[s['product_id']],date.fromisoformat(s['sales_date']),Decimal(s['quantity'])) for s in main['sales']),recipes)
assert not bom.gaps
observed={(date.fromisoformat(r['usage_date']),iids[r['ingredient_id']]):Decimal(r['quantity']) for r in main['usage_history']}
assert {(r.day,r.ingredient_id):r.quantity for r in bom.totals}==observed
external=data['workbooks']['03_external_week_locked.xlsx']['sales'];assert len(external)==28 and min(r['sales_date'] for r in external)=='2026-10-18' and max(r['sales_date'] for r in external)=='2026-10-24'
assert json.loads((root/'hashes.json').read_text(encoding='utf-8'))==hashes, 'Workbook digest drift'
print(json.dumps(dict(outcome='PASS',typed_normalized_rows=checks,real_bom_daily_totals=len(bom.totals),external_rows=28,workbook_sha256=hashes),indent=2))
