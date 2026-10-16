"""Formatting cannot make an empty import ready; missing CSV records stay invalid."""
import pytest
from tests.unit.test_import_parser import workbook
from tests.integration.test_import_staging import imp, env, analyzed, approved, previewed


@pytest.mark.parametrize('format', ['xlsx','csv'])
def test_empty_source_keeps_preview_blocked(imp,format):
    keys = ['sales.sales_date','sales.product_id','sales.quantity','sales.unit','sales.business_report_key']
    if format=='xlsx':
        header=''.join(f'<c r="{chr(65+n)}1" t="inlineStr"><is><t>{k}</t></is></c>' for n,k in enumerate(keys))
        content=workbook('<row r="1">'+header+'</row><row r="2"><c r="A2" s="1"/></row>')
        from tests.integration.test_import_commit import analyzed_files
        ident=analyzed_files(imp,[('format-only.xlsx',content)])
    else:
        ident=analyzed(imp,(','.join(keys)+'\n,,,,\n').encode())
    approved(imp,ident)
    read=previewed(imp,ident)['preview']
    assert read['summary']['validation_status']=='blocked' and not read['summary']['can_commit']
    if format=='xlsx':
        assert read['rows']==[]
        assert any(b['code']=='NO_DATA_ROWS' for b in read['summary']['blockers'])
        assert any(w['code']=='XLSX_FORMAT_ONLY_ROW_SKIPPED' for w in read['summary']['warnings'])
    else:
        assert read['rows'][0]['classification']=='INVALID'
        assert not any(w['code']=='XLSX_FORMAT_ONLY_ROW_SKIPPED' for w in read['summary']['warnings'])
