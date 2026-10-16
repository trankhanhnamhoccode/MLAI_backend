"""Explicit sheet/header mapping; no LLM, defaults, inferred prices or operational writes."""
from datetime import date
from decimal import Decimal, InvalidOperation
import unicodedata
import re
from uuid import UUID, uuid5

from app.application.contracts.demo_workbooks import CellEvidence, DemoProduct, DemoSale, DemoCalendar, DemoDataset, AdmissionFinding
from app.application.import_excel_dates import excel_date
from app.application.forecast_challenger_serialization import challenger_digest

NAMESPACE=UUID('2c812493-913d-497b-b993-3aac434121c8')


def text(value):
    return None if value is None else unicodedata.normalize('NFC',value).strip()


def boolean(value):
    value=text(value)
    if value in (None,''): return None
    mapping={'có':True,'không':False,'true':True,'false':False,'1':True,'0':False}
    if value.casefold() not in mapping: raise ValueError('INVALID_TRI_STATE_BOOLEAN')
    return mapping[value.casefold()]


def quantity(value):
    if value in (None,''): return None
    if not isinstance(value,str): raise ValueError('INVALID_QUANTITY')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?',value): raise ValueError('INVALID_QUANTITY')
    try: number=Decimal(value)
    except (InvalidOperation,TypeError): raise ValueError('INVALID_QUANTITY') from None
    if not number.is_finite() or number<0: raise ValueError('INVALID_QUANTITY')
    return number


def day(value,system):
    if value is None: raise ValueError('MISSING_DATE')
    try: return date.fromisoformat(value)
    except ValueError: return date.fromisoformat(excel_date(value,system))


def col_name(index):
    value=index+1;out=''
    while value:
        value,remainder=divmod(value-1,26);out=chr(65+remainder)+out
    return out


def evidence_at(book,sheet_name,address):
    letters=address.rstrip('0123456789');number=int(address[len(letters):])
    column=0
    for char in letters: column=column*26+ord(char)-64
    sheet=next(s for s in book.parsed.sheets if s.name==sheet_name)
    row=next((r for r in sheet.rows if r.row_number==number),None)
    cell=None if row is None else next((c for c in row.cells if c.column_index==column-1),None)
    return CellEvidence(file_sha256=book.sha256,sheet=sheet_name,cell=address,
                        raw=None if cell is None else cell.raw,formula=False if cell is None else cell.formula)


class Table:
    def __init__(self,book,sheet_name,headers):
        self.book=book
        self.sheet=next(s for s in book.parsed.sheets if s.name==sheet_name)
        header=next((r for r in self.sheet.rows if r.row_number==3),None)
        self.header={} if header is None else {c.column_index:self.literal(header,c.column_index) for c in header.cells}
        if tuple(self.header.get(i) for i in range(len(headers)))!=tuple(headers):
            raise ValueError('EXPLICIT_HEADER_MAPPING_MISMATCH:'+sheet_name)

    def evidence(self,row,column):
        cell=next((c for c in row.cells if c.column_index==column),None)
        return CellEvidence(file_sha256=self.book.sha256,sheet=self.sheet.name,cell=col_name(column)+str(row.row_number),
            raw=None if cell is None else cell.raw,formula=False if cell is None else cell.formula)

    def literal(self,row,column):
        evidence=self.evidence(row,column)
        if evidence.formula: raise ValueError('FORMULA_NOT_CANONICAL_SOURCE:'+evidence.cell)
        return text(evidence.raw)

    def rows(self):
        return tuple(r for r in self.sheet.rows if r.row_number>3 and any(c.raw not in (None,'') for c in r.cells))


POS_HEADERS=('Ngày GD','Tên món / SKU','SLX','Đơn giá bán','Doanh thu','Hết món?','CTKM')
MENU_HEADERS=('Mã món','Loại','Tên món / Combo','Thành phần combo','ĐVT','Tổng giá lẻ','Mức giảm','Giá bán','Tiết kiệm','Trạng thái')
CALENDAR_HEADERS=('Date','Weekend','Holiday','Store closed','Promo','Campaign','Temp C','Rain mm')


def normalize_demo(books,timezone=None):
    by_role={b.role:b for b in books}
    menu=Table(by_role['menu'],'06_Menu',MENU_HEADERS)
    products=[];issues=[];names={};keys=set()
    for row in menu.rows():
        if menu.literal(row,1)!='Món lẻ': continue
        sku,name,unit,state=(menu.literal(row,c) for c in (0,2,4,9))
        if not all((sku,name,unit,state)): raise ValueError('MENU_IDENTITY_UNIT_MISSING')
        if sku in keys or name in names: raise ValueError('MENU_IDENTITY_AMBIGUOUS')
        product=DemoProduct(product_id=uuid5(NAMESPACE,'product/'+sku),source_key=sku,name=name,selling_unit=unit,
                            menu_status=state,sources=tuple(menu.evidence(row,c) for c in (0,1,2,4,9)))
        products.append(product);names[name]=product;keys.add(sku)
    pos=Table(by_role['pos'],'POS_T7_2026',POS_HEADERS)
    sales=[];seen={}
    for row in pos.rows():
        sources=tuple(pos.evidence(row,c) for c in (0,1,2,5))
        try:
            name=pos.literal(row,1)
            if name not in names: raise ValueError('POS_PRODUCT_NOT_IN_PROPOSED_SINGLE_ITEM_SCOPE')
            record=DemoSale(product_id=names[name].product_id,sales_date=day(pos.literal(row,0),pos.book.parsed.excel_date_system),
                quantity=quantity(pos.literal(row,2)),is_stockout=boolean(pos.literal(row,5)),sources=sources)
            key=record.product_id,record.sales_date
            if key in seen:
                issues.append(AdmissionFinding(code='DUPLICATE_POS_KEY',classification='BLOCKER',area='DATA',
                    detail='Duplicate Product/date rows retained; no aggregation or first-row selection.',sources=seen[key]+sources))
            seen[key]=sources;sales.append(record)
        except ValueError as error:
            issues.append(AdmissionFinding(code='INVALID_POS_ROW',classification='BLOCKER',area='DATA',detail=str(error),sources=sources))
    dates=[];seen_days={}
    calendar=Table(by_role['calendar'],'Calendar + Weather',CALENDAR_HEADERS) if 'calendar' in by_role else None
    for row in calendar.rows() if calendar else ():
        sources=tuple(calendar.evidence(row,c) for c in (0,2,3))
        try:
            record=DemoCalendar(day=day(calendar.literal(row,0),calendar.book.parsed.excel_date_system),
                closed=boolean(calendar.literal(row,3)),holiday=boolean(calendar.literal(row,2)),sources=sources)
            if record.day in seen_days:
                issues.append(AdmissionFinding(code='DUPLICATE_CALENDAR_DATE',classification='BLOCKER',area='FORECAST_C',
                    detail='Calendar dates cannot be merged silently.',sources=seen_days[record.day]+sources))
            seen_days[record.day]=sources;dates.append(record)
        except ValueError as error:
            issues.append(AdmissionFinding(code='INVALID_CALENDAR_ROW',classification='BLOCKER',area='FORECAST_C',detail=str(error),sources=sources))
    revision=challenger_digest('demo-raw-bundle',{b.role:b.sha256 for b in books})
    dataset=DemoDataset(source_revision=revision,store_id=uuid5(NAMESPACE,'benchmark-only-demo-store'),timezone=timezone,
        products=tuple(sorted(products,key=lambda p:p.source_key)),sales=tuple(sorted(sales,key=lambda r:(r.sales_date,r.product_id))),
        calendar=tuple(sorted(dates,key=lambda r:r.day)))
    return dataset,tuple(issues)
