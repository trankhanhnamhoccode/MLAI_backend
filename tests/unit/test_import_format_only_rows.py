"""Only value-free XLSX formatting is a non-record; incomplete data still validates."""
from copy import deepcopy
from uuid import uuid4
import pytest
from app.application.import_preview import preview_record_sources


@pytest.mark.parametrize('epoch', ['1900', '1904'])
def test_formatting_locations_are_reported_without_mutating_raw_evidence(epoch):
    sheet = dict(file_id=str(uuid4()), sheet_id=str(uuid4()), excel_date_system=epoch,
        rows=[dict(row_number=2,cells=[dict(column_index=0,raw=None,kind='empty',formula=False)]),
              dict(row_number=3,cells=[]),
              dict(row_number=4,cells=[dict(column_index=0,raw='0',kind='numeric',formula=False)])])
    original = deepcopy(sheet)
    scoped, warnings = preview_record_sources([sheet])
    assert sheet == original
    assert [r['row_number'] for r in scoped[0]['rows']] == [4]
    assert [w.source_location.row_number for w in warnings] == [2,3]
    assert all(w.code == 'XLSX_FORMAT_ONLY_ROW_SKIPPED' and w.severity == 'WARNING' for w in warnings)


@pytest.mark.parametrize('epoch,raw,kind,formula', [
    (None,None,'empty',False), (None,'','empty',False),
    ('1900','0','numeric',False), ('1900','0','boolean',False),
    ('1900','','text',False), ('1900',' ','text',False),
    ('1900',None,'empty',True), ('1900',None,'error',False),
    ('1900','unmapped evidence','text',False), ('1900',None,'numeric',False),
])
def test_missing_or_unmapped_values_formula_error_csv_zero_and_false_remain_records(epoch,raw,kind,formula):
    row = dict(row_number=2,cells=[dict(column_index=9,raw=raw,kind=kind,formula=formula)])
    sheet = dict(file_id=str(uuid4()),sheet_id=str(uuid4()),excel_date_system=epoch,rows=[row])
    scoped, warnings = preview_record_sources([sheet])
    assert scoped[0]['rows'] == [row] and not warnings
