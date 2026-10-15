"""Read-only wrapper over the existing bounded XLSX reader; no formula evaluation."""
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.application.contracts.import_source import ParsedFile
from app.infrastructure.import_parser import parse_source, MAIN, DOC_REL

ROLE_SHEETS = {
    'pos': ('POS_T7_2026',),
    'usage': ('NL_thực_dùng',),
    'stock_vendor': ('KiemKe_27-07', 'PNK tháng 7', 'Vendor rules'),
    'recipes_rules': ('Định lượng món', 'Điều kiện vận hành'),
    'calendar': ('Calendar + Weather',),
    'menu': ('06_Menu',),
}


@dataclass(frozen=True)
class DemoWorkbook:
    role: str
    path: Path
    sha256: str
    parsed: ParsedFile
    metadata: dict


def read_workbook(path: Path) -> DemoWorkbook:
    content=path.read_bytes()
    digest=hashlib.sha256(content).hexdigest()
    parsed=parse_source(content,'xlsx')
    names={s.name for s in parsed.sheets}
    roles=[r for r,expected in ROLE_SHEETS.items() if set(expected)<=names]
    if len(roles)!=1: raise ValueError('WORKBOOK_ROLE_SIGNATURE_AMBIGUOUS_OR_UNKNOWN')
    metadata=dict(role=roles[0],path=str(path.resolve()),sha256=digest,bytes=len(content),excel_date_system=parsed.excel_date_system,
                  formulas_evaluated=False,sheets=[],aliases=[])
    # parse_source has already enforced archive/XML bounds, path and external-link guards.
    with ZipFile(io.BytesIO(content)) as archive:
        wb=ET.fromstring(archive.read('xl/workbook.xml'))
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        metadata['package_members']=len(archive.infolist())
        metadata['document_properties_present']=[n for n in ('docProps/core.xml','docProps/app.xml') if n in archive.namelist()]
        for item,sheet in zip(wb.find(MAIN+'sheets'),parsed.sheets,strict=True):
            target=rels[item.attrib[DOC_REL+'id']]
            member=target[1:] if target.startswith('/') else posixpath.normpath(posixpath.join('xl',target))
            root=ET.fromstring(archive.read(member))
            formulas=[dict(cell=c.attrib['r'],text=f.text,cached=None if c.find(MAIN+'v') is None else c.find(MAIN+'v').text,
                           attributes=dict(f.attrib)) for c in root.iter(MAIN+'c') if (f:=c.find(MAIN+'f')) is not None]
            dimension=root.find(MAIN+'dimension')
            metadata['sheets'].append(dict(name=sheet.name,index=sheet.index,state=item.attrib.get('state','visible'),
                declared_dimension=None if dimension is None else dimension.attrib.get('ref'),
                physical_rows=len(sheet.rows),first_row=min((r.row_number for r in sheet.rows),default=None),
                last_row=max((r.row_number for r in sheet.rows),default=None),
                physical_columns=max((c.column_index+1 for r in sheet.rows for c in r.cells),default=0),
                populated_cells=sum(c.raw is not None for r in sheet.rows for c in r.cells),
                formula_count=len(formulas),formulas=formulas))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise ValueError('RAW_CHANGED_DURING_READ')
    return DemoWorkbook(roles[0],path.resolve(),digest,parsed,metadata)


def discover_workbooks(directory: Path) -> tuple[DemoWorkbook,...]:
    found={role:{} for role in ROLE_SHEETS}
    for path in sorted(directory.glob('*.xlsx'),key=lambda p:p.name.casefold()):
        book=read_workbook(path)
        found[book.role].setdefault(book.sha256,[]).append(book)
    result=[]
    for role,variants in found.items():
        if not variants: raise ValueError('MISSING_WORKBOOK_ROLE:'+role)
        if len(variants)!=1: raise ValueError('DISTINCT_WORKBOOK_VARIANTS_REQUIRE_EXPLICIT_SELECTION:'+role)
        copies=next(iter(variants.values()))
        book=copies[0]
        book.metadata['aliases']=[str(c.path) for c in copies[1:]]
        result.append(book)
    return tuple(result)
