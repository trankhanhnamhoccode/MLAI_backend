"""Generated tiny OOXML fixtures, never copied DEMO rows; no model/DB/provider execution."""
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
import hashlib
import io
from xml.sax.saxutils import escape
from zipfile import ZipFile,ZIP_DEFLATED

import pytest

from app.application.contracts.demo_workbooks import AdmissionDeclarations
from app.application.demo_workbook_normalization import normalize_demo,boolean,quantity,day,Table,POS_HEADERS,MENU_HEADERS,CALENDAR_HEADERS
from app.application.demo_workbook_admission import OP_TABLES,assess,proposed_windows
from app.application.use_cases.forecast_benchmark import load_protocol
from app.application.forecast_benchmark_admission import admit_plan
from app.infrastructure.demo_workbook_reader import discover_workbooks,read_workbook
from app.application.contracts.import_source import SourceParseError
from scripts.prepare_demo_benchmark import prepare

ROOT=Path(__file__).resolve().parents[2]


def serial(day_value): return str((day_value-date(1899,12,30)).days)


def xlsx(sheets,*,epoch='0',formula=None):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    relationship='http://schemas.openxmlformats.org/package/2006/relationships'
    files={};sheet_tags=[];rels=[]
    for i,(name,rows) in enumerate(sheets.items(),1):
        sheet_tags.append(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="s{i}"/>')
        rels.append(f'<Relationship Id="s{i}" Target="worksheets/s{i}.xml"/>')
        xml_rows=[]
        for number,values in sorted(rows.items()):
            cells=[]
            for column,value in values.items():
                address=column+str(number)
                if value is None: continue
                if formula and (name,address)==formula[:2]:
                    cells.append(f'<c r="{address}"><f>{escape(formula[2])}</f><v>{value}</v></c>')
                else: cells.append(f'<c r="{address}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
            xml_rows.append(f'<row r="{number}">'+''.join(cells)+'</row>')
        files[f'xl/worksheets/s{i}.xml']=f'<worksheet xmlns="{ns}"><sheetData>'+''.join(xml_rows)+'</sheetData></worksheet>'
    files['xl/workbook.xml']=f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><workbookPr date1904="{epoch}"/><sheets>'+''.join(sheet_tags)+'</sheets></workbook>'
    files['xl/_rels/workbook.xml.rels']=f'<Relationships xmlns="{relationship}">'+''.join(rels)+'</Relationships>'
    output=io.BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for path,value in files.items(): archive.writestr(path,value)
    return output.getvalue()


def headers(values): return {chr(65+i):v for i,v in enumerate(values)}


def bundle(tmp_path,*,duplicate=False,missing=False,unit='cup',days=70):
    first=date(2026,1,1)
    menu={1:{'A':'Fixture menu'},2:{'A':'Single items and paused combos'},3:headers(MENU_HEADERS)}
    for i in range(5):
        menu[i+4]={'A':f'p{i+1}','B':'Món lẻ','C':f'Drink{i+1}','E':unit,'J':'active'}
    pos={1:{'A':'Fixture POS'},2:{'A':'synthetic demo fixture'},3:headers(POS_HEADERS)}
    for n in range(days):
        for i in range(5):
            row=4+n*5+i
            if missing and n==1 and i==0: continue
            pos[row]={'A':serial(first+timedelta(days=n)),'B':f'Drink{i+1}','C':'0' if n==0 else '2','F':None if n==0 else 'Không'}
    if duplicate: pos[max(pos)+1]=dict(pos[4])
    calendar={1:{'A':'Fixture calendar'},3:headers(CALENDAR_HEADERS)}
    for n in range(days+7):calendar[n+4]={'A':serial(first+timedelta(days=n)),'C':'FALSE','D':'FALSE'}
    ops={}
    for kind,(role,sheet,cols) in OP_TABLES.items():
        rows={1:{'A':'Fixture '+kind},2:{'A':'synthetic POS recipe fixture'},3:headers(cols)}
        if kind=='inventory':rows[4]={'A':serial(first+timedelta(days=days-1)),'B':'Material','C':'10','D':'g','F':'lot-fixture'}
        if kind=='usage':rows[4]={'A':serial(first),'B':'Material','C':'1','D':'g','E':'0','F':'derived fixture'}
        if kind=='vendor_terms':rows[4]={'A':'Vendor','B':'Material','C':'1','D':'pack','E':'2','F':'g','G':'1','H':'7','I':'Monday'}
        if kind=='recipes':rows[4]={'A':'Drink1','B':'Material','C':'1','D':'g','E':'2','F':unit,'G':'version-x','H':serial(first)}
        if kind=='constraints':rows[4]={'A':'safety_stock','B':'Material','C':'1','D':'g','F':serial(first)}
        ops.setdefault(role,{})[sheet]=rows
    workbooks={'pos':{'POS_T7_2026':pos},'menu':{'06_Menu':menu},'calendar':{'Calendar + Weather':calendar},**ops}
    for role,sheets in workbooks.items():(tmp_path/(role+'.xlsx')).write_bytes(xlsx(sheets))
    return discover_workbooks(tmp_path)


def test_reader_source_locations_tri_state_missing_and_zero(tmp_path):
    books=bundle(tmp_path,missing=True)
    assert next(b for b in books if b.role=='pos').metadata['role']=='pos'
    assert next(b for b in books if b.role=='pos').metadata['sheets'][0]['physical_columns']==7
    data,issues=normalize_demo(books)
    assert not issues and len(data.sales)==349
    assert sum(r.quantity==0 for r in data.sales)==5
    assert sum(r.is_stockout is None for r in data.sales)==5
    p=next(p for p in data.products if p.source_key=='p1')
    assert not any(r.product_id==p.product_id and r.sales_date==date(2026,1,2) for r in data.sales)
    row=next(r for r in data.sales if r.product_id==p.product_id and r.sales_date==date(2026,1,1))
    assert row.sources[0].cell=='A4' and row.sources[2].cell=='C4' and row.sources[3].raw is None
    assert row.sources[0].file_sha256==next(b.sha256 for b in books if b.role=='pos')


@pytest.mark.parametrize('value,expected',[('Có',True),('Không',False),('TRUE',True),('0',False),(None,None),('',None)])
def test_explicit_tri_state_tokens(value,expected): assert boolean(value) is expected


@pytest.mark.parametrize('value',['maybe','2','n/a'])
def test_unknown_stockout_token_never_becomes_false(value):
    with pytest.raises(ValueError): boolean(value)


@pytest.mark.parametrize('value',['-1','NaN','Infinity',True,'1_000','1,000'])
def test_invalid_quantities_are_not_zero(value):
    with pytest.raises(ValueError): quantity(value)


def test_duplicate_keys_are_blocked_and_both_source_rows_retained(tmp_path):
    data,issues=normalize_demo(bundle(tmp_path,duplicate=True))
    issue=next(i for i in issues if i.code=='DUPLICATE_POS_KEY')
    assert issue.classification=='BLOCKER' and len(data.sales)==351
    assert {v.cell for v in issue.sources if v.cell.startswith('A')}=={'A4','A354'}


def test_units_are_sourced_unchanged_and_blank_unit_blocks(tmp_path):
    data,_=normalize_demo(bundle(tmp_path,unit='unit-X'))
    assert {p.selling_unit for p in data.products}=={'unit-X'}
    with pytest.raises(ValueError,match='IDENTITY_UNIT_MISSING'):
        normalize_demo(bundle(tmp_path,unit=''))


def test_deduplicate_equal_bytes_not_filename_suffix_and_reject_distinct_variants(tmp_path):
    books=bundle(tmp_path)
    source=next(b for b in books if b.role=='pos')
    (tmp_path/'a-pos-copy (99).xlsx').write_bytes(source.path.read_bytes())
    same=discover_workbooks(tmp_path)
    assert len(same)==6 and len(next(b for b in same if b.role=='pos').metadata['aliases'])==1
    raw=source.path.read_bytes()
    # Same logical role but a distinct archive, even if it has an innocent suffix.
    with ZipFile(io.BytesIO(raw)) as archive: parts={n:archive.read(n) for n in archive.namelist()}
    parts['extra-metadata.xml']=b'<extra/>'
    out=io.BytesIO()
    with ZipFile(out,'w') as archive:
        for name,value in parts.items():archive.writestr(name,value)
    (tmp_path/'pos (1).xlsx').write_bytes(out.getvalue())
    with pytest.raises(ValueError,match='DISTINCT_WORKBOOK_VARIANTS'): discover_workbooks(tmp_path)


def test_formulas_are_metadata_only_never_canonical_values(tmp_path):
    rows={3:headers(POS_HEADERS),4:{'A':'46023','B':'Drink1','C':'9','F':'FALSE'}}
    path=tmp_path/'formula.xlsx'
    path.write_bytes(xlsx({'POS_T7_2026':rows},formula=('POS_T7_2026','C4','1+1')))
    book=read_workbook(path)
    assert book.metadata['sheets'][0]['formulas'][0]['cached']=='9'
    table=Table(book,'POS_T7_2026',POS_HEADERS)
    with pytest.raises(ValueError,match='FORMULA_NOT_CANONICAL_SOURCE'):
        table.literal(table.rows()[0],2)


def test_epoch_dates_and_protocol_windows():
    assert day('46023','1900')==date(2026,1,1)
    assert day('0','1904')==date(1904,1,1)
    with pytest.raises(ValueError):day('60','1900')
    with pytest.raises(ValueError):day('46023.5','1900')
    tasks=proposed_windows(date(2026,8,19),load_protocol(ROOT))
    assert [t.origin for t in tasks]==[date(2026,7,22),date(2026,7,29),date(2026,8,5),date(2026,8,12)]
    assert tasks[0].train_end==date(2026,5,27) and tasks[-1].calibration_start==date(2026,7,16)
    assert [t.partition for t in tasks]==['validation','validation','holdout','holdout']


def test_preparation_no_training_raw_hashes_and_unapproved_projection_blocked(tmp_path,monkeypatch):
    uploads=tmp_path/'uploads';uploads.mkdir();bundle(uploads)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in uploads.glob('*.xlsx')}
    def forbidden(*a,**k):pytest.fail('Admission cannot train or run Planning')
    monkeypatch.setattr('app.infrastructure.forecast_benchmark_training.fit_arm',forbidden)
    monkeypatch.setattr('app.application.use_cases.forecast_benchmark.fit_arm',forbidden)
    monkeypatch.setattr('app.application.use_cases.procurement_v2.execute_procurement_v2',forbidden)
    # Source code is rooted in the repository; outputs redirected to a test-only storage root.
    import scripts.prepare_demo_benchmark as command
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    monkeypatch.setattr(command,'BenchmarkStorage',lambda root:BenchmarkStorage(tmp_path/'owned-runtime'))
    manifest,directory=prepare(uploads,ROOT,AdmissionDeclarations())
    assert manifest['normalization']=='READY' and manifest['forecast_AB']=='PARTIAL_DECLARATIONS_REQUIRED'
    assert not (directory/'dataset.json').exists() and manifest['planned_workload']['executed_fits']==0
    assert manifest['E4']=='BLOCKED' and manifest['forecast_C']=='BLOCKED'
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in uploads.glob('*.xlsx')}


def test_explicit_demo_declarations_allow_only_limited_harness_projection(tmp_path):
    books=bundle(tmp_path)
    config=AdmissionDeclarations(timezone='UTC',accept_five_single_item_scope=True,
        observation_availability='RETROSPECTIVE_NEXT_RUN_ASSUMPTION')
    data,issues=normalize_demo(books,config.timezone)
    manifest,tables,projection,plan=assess(data,books,config,issues,load_protocol(ROOT))
    assert projection is not None and projection.classification=='SYNTHETIC' and projection.calendar==()
    assert manifest['forecast_AB']=='READY_DEMO_EXPLORATORY_INPUT' and manifest['paired_ABC']=='BLOCKED'
    assert any('not real/unseen' in limitation for limitation in projection.limitations)
    assert manifest['findings'] and any(f.code=='SAFETY_STOCK_UNSUPPORTED' for f in manifest['findings'])
    admit_plan(projection,plan)


def test_calendar_duplicate_and_unknown_flags_are_not_default_open(tmp_path):
    bundle(tmp_path)
    rows={3:headers(CALENDAR_HEADERS),4:{'A':'46023','C':None,'D':None},5:{'A':'46023','C':'FALSE','D':'FALSE'}}
    (tmp_path/'calendar.xlsx').write_bytes(xlsx({'Calendar + Weather':rows}))
    data,issues=normalize_demo(discover_workbooks(tmp_path))
    assert data.calendar[0].closed is None and data.calendar[0].holiday is None
    issue=next(i for i in issues if i.code=='DUPLICATE_CALENDAR_DATE')
    assert {c.cell for c in issue.sources if c.cell.startswith('A')}=={'A4','A5'}


def test_reader_epoch_metadata_is_used_without_date_guessing(tmp_path):
    rows={3:headers(POS_HEADERS),4:{'A':'0','B':'Drink1','C':'0','F':'FALSE'}}
    p=tmp_path/'epoch.xlsx';p.write_bytes(xlsx({'POS_T7_2026':rows},epoch='1'))
    book=read_workbook(p)
    assert book.parsed.excel_date_system=='1904'
    assert day('0',book.parsed.excel_date_system)==date(1904,1,1)


def test_postprocess_purge_and_holdout_quarantine_preserve_frozen_policy(tmp_path):
    from app.application.demo_workbook_admission import postprocess_population
    data,_=normalize_demo(bundle(tmp_path))
    observed={(r.product_id,r.sales_date):r for r in data.sales}
    start=date(2026,1,2);end=start+timedelta(days=27)
    holdout={end-timedelta(days=i) for i in range(7)}
    pop=postprocess_population(observed,data.products,start,end,start-timedelta(days=1),holdout)
    assert pop['purged_tasks']==105 and pop['holdout_quarantined_tasks']==245
    assert sum(pop['eligible_known_false_tasks_by_horizon_upper_bound'].values())==630


def test_duration_constraint_is_not_an_ingredient_quantity_unit_alias(tmp_path):
    bundle(tmp_path)
    recipe_headers=OP_TABLES['recipes'][2];rule_headers=OP_TABLES['constraints'][2]
    recipe={3:headers(recipe_headers),4:{'A':'Drink1','B':'Material','C':'1','D':'g','E':'2','F':'cup','G':'v1','H':'46023'}}
    rules={3:headers(rule_headers),4:{'A':'safety_stock','B':'Material','C':'1','D':'g','F':'46023'},
           5:{'A':'shelf_life_target','B':'Material','C':'5','D':'day','F':'46023'},
           6:{'A':'maximum_stock','B':'Material','C':'10','D':'kilogram','F':'46023'}}
    (tmp_path/'recipes_rules.xlsx').write_bytes(xlsx({'Định lượng món':recipe,'Điều kiện vận hành':rules}))
    books=discover_workbooks(tmp_path);data,issues=normalize_demo(books)
    manifest,_,_,_=assess(data,books,AdmissionDeclarations(),issues,load_protocol(ROOT))
    assert {v.raw for v in manifest['operational_unit_conflicts']['Material']}=={'g','kilogram'}
