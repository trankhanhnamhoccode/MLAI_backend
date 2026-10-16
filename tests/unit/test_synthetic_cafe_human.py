"""Physical source values versus frozen independent authoring truth; no DB/provider."""
import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import pytest
from app.infrastructure.import_parser import parse_source
from app.application.import_analysis import header_index

ROOT=Path(__file__).parents[1]/'fixtures'
HUMAN=ROOT/'synthetic_cafe_human_v1'
MANIFEST=json.loads((HUMAN/'manifest.json').read_text(encoding='utf-8'))
ORACLE=json.loads((ROOT/'synthetic_cafe_v1/dataset.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('filename',MANIFEST['files'])
def test_human_source_preserves_every_oracle_field_and_value(filename):
    raw=(HUMAN/filename).read_bytes()
    hashes=json.loads((HUMAN/'hashes.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(raw).hexdigest()==hashes[filename]
    parsed=parse_source(raw,filename.rsplit('.',1)[1])
    expected_sheets=MANIFEST['files'][filename]['sheets']
    assert len(parsed.sheets)==len(expected_sheets)
    for sheet,spec in zip(parsed.sheets,expected_sheets,strict=True):
        index=header_index(sheet.rows) if filename.endswith('.xlsx') else 0
        assert sheet.rows[index].row_number==spec['header_row']
        expected=ORACLE['workbooks'][spec['oracle_file']][spec['oracle_sheet']]
        assert len(sheet.rows[index+1:])==len(expected)==spec['row_count']
        assert {c['field'] for c in spec['columns']}==set(expected[0])
        assert [c.raw for c in sheet.rows[index].cells]==[c['label'] for c in spec['columns']]
        for physical,truth in zip(sheet.rows[index+1:],expected,strict=True):
            cells={c.column_index:c for c in physical.cells}
            for i,column in enumerate(spec['columns']):
                value=truth[column['field']];cell=cells.get(i);raw=cell.raw if cell else None
                assert not cell or not cell.formula
                if value is None:assert raw in (None,'')
                elif type(value) is bool:assert raw.lower() in (str(value).lower(),str(int(value)))
                elif type(value) in (int,float):assert Decimal(raw)==Decimal(str(value))
                elif isinstance(value,(list,dict)):assert json.loads(raw)==value
                elif len(value)==10 and value[4]=='-' and value[7]=='-':
                    assert (date(1899,12,30)+timedelta(days=int(raw)) if filename.endswith('.xlsx') else date.fromisoformat(raw))==date.fromisoformat(value)
                elif 'T' in value and column['field'].endswith('_at'):
                    assert datetime.fromisoformat(raw.replace('Z','+00:00'))==datetime.fromisoformat(value)
                else:assert raw==value,(filename,spec['sheet'],physical.row_number,column,raw,value)


def test_oracle_bytes_remain_pinned_and_external_inputs_separate():
    assert hashlib.sha256((ROOT/'synthetic_cafe_v1/dataset.json').read_bytes()).hexdigest()==MANIFEST['oracle_sha256']
    for filename,digest in MANIFEST['oracle_workbook_hashes'].items():
        assert hashlib.sha256((ROOT/'synthetic_cafe_v1'/filename).read_bytes()).hexdigest()==digest
    assert MANIFEST['files']['06_tuan_kiem_chung.xlsx']['role']=='external_locked'
    assert MANIFEST['files']['07_doi_soat.xlsx']['role']=='reference_only'
