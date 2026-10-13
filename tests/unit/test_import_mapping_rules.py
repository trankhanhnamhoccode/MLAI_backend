"""Conservative proposals preserve physical evidence and require explicit approval."""

from uuid import uuid4

from app.application.import_analysis import discover
from app.application.import_descriptors import rule_classification
from app.infrastructure.import_parser import parse_source


def test_title_preamble_headers_and_extra_unlabelled_data_are_preserved():
    content = (
        'POS report\nOwner supplied notes\n'
        'Ngày GD,Tên món / SKU,Số lượng bán,ĐVT,Mã báo cáo nghiệp vụ\n'
        '2026-10-09,Coffee,0,cup,R-1,extra business data\n'
    ).encode()
    sheets, issues, raw = discover(uuid4(), parse_source(content, 'csv'))
    sheet = sheets[0]
    assert sheet.header_row == 3 and sheet.preamble_rows == (1, 2)
    assert sheet.preamble_samples == ('POS report', 'Owner supplied notes')
    assert sheet.row_count == 1 and len(sheet.headers) == 6
    assert sheet.selected_type == 'sales'
    assert [r['row_number'] for r in raw[0]['preamble']] == [1, 2]
    assert raw[0]['rows'][0]['row_number'] == 4
    assert raw[0]['rows'][0]['cells'][2]['raw'] == '0'
    columns = [i for i in issues if i.issue_type == 'column']
    assert columns[0].target_field == 'sales.sales_date'
    assert columns[0].suggestion_reason and columns[0].status == 'needs_confirmation'
    assert columns[-1].target_field is None and columns[-1].status == 'unmatched'


def test_do_not_skip_multicell_rows_in_search_for_familiar_header():
    sheets, _, raw = discover(uuid4(), parse_source(
        b'unknown,business row\nsales.product_id,sales.sales_date,sales.quantity\nP,2026-10-09,1\n', 'csv'))
    assert sheets[0].header_row == 1 and len(raw[0]['rows']) == 2


def test_controlled_normalization_duplicates_and_no_identity_inference():
    kind, targets, _, _ = rule_classification(
        ('  NGAY_GD ', 'Tên món / SKU', 'Số lượng bán', 'ĐVT'), 'arbitrary filename')
    assert kind == 'sales' and targets == (
        'sales.sales_date', 'sales.product_id', 'sales.quantity', 'sales.unit')
    _, issues, _ = discover(uuid4(), parse_source(
        'sales.sales_date,Số lượng bán,quantity sold\n2026-10-09,1,2\n'.encode(), 'csv'))
    duplicate = [i for i in issues if i.source_header in ('Số lượng bán', 'quantity sold')]
    assert all(i.status == 'ambiguous' and i.target_field is None for i in duplicate)
    assert all(i.candidate_targets == ('sales.quantity',) for i in duplicate)


def test_unsupported_sheets_and_ambiguous_business_meanings_are_not_forced():
    for headers in (
        ('NCT', 'Tên hàng', 'SLN', 'ĐVT', 'Giá nhập', 'Thành tiền'),
        ('Date', 'Weekend', 'Holiday', 'Store closed', 'Promo'),
        ('Loại điều kiện', 'Áp dụng cho NL', 'Giá trị', 'Unit', 'Currency'),
    ):
        assert rule_classification(headers, 'sales')[0] is None
    usage = rule_classification(('Ngày sử dụng', 'Lượng thực dùng'), 'sales')
    assert usage[0] == 'usage_history' and usage[3]  # Missing identity/unit/evidence still requires review.
    kind, targets, _, _ = rule_classification(
        ('Vendor', 'Material', 'MOQ', 'Order UOM', 'Pack Size', 'Base UOM', 'Lead time (days)', 'Giá mua'), '')
    assert kind == 'supplier_terms'
    assert targets[2] is None and targets[-1] is None
    assert rule_classification(('Ngày GD', 'Tên món / SKU', 'SLX'), '')[1][-1] is None


def test_numeric_excel_dates_are_proposed_with_explicit_convention_review():
    from tests.unit.test_import_parser import workbook
    content = workbook(
        '<row r="1"><c r="A1" t="inlineStr"><is><t>sales.sales_date</t></is></c></row>'
        '<row r="2"><c r="A2"><v>46253</v></c></row>')
    _, issues, raw = discover(uuid4(), parse_source(content, 'xlsx'))
    date = next(i for i in issues if i.issue_type == 'column')
    assert date.target_field == 'sales.sales_date'
    assert 'DATE_CONVENTION_REVIEW' in date.suggestion_reason
    assert raw[0]['rows'][0]['cells'][0]['raw'] == '46253'


def test_configured_key_without_opt_in_never_opens_transport(monkeypatch):
    from pydantic import SecretStr
    from app.config import Settings
    from app.infrastructure import import_suggestions as gateway
    monkeypatch.setattr(gateway, 'build_opener',
                        lambda *a: (_ for _ in ()).throw(AssertionError('network forbidden')))
    sheets, _, raw = discover(uuid4(), parse_source(b'sales.quantity\n1\n', 'csv'))
    assert gateway.suggest_sheet(Settings(_env_file=None, openrouter_api_key=SecretStr('SYNTHETIC')),
                                 sheets[0], raw[0], 'x', {}) == (None, 'LLM_UNAVAILABLE')


def test_xlsx_preamble_and_styled_blanks_preserve_cached_formula_location():
    from tests.unit.test_import_parser import workbook
    content = workbook(
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Title</t></is></c><c r="F1" s="1"/></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Notes</t></is></c></row>'
        '<row r="3"><c r="A3" t="inlineStr"><is><t>sales.sales_date</t></is></c>'
        '<c r="B3" t="inlineStr"><is><t>sales.quantity</t></is></c>'
        '<c r="C3" t="inlineStr"><is><t>sales.unit</t></is></c><c r="F3" s="1"/></row>'
        '<row r="4"><c r="A4" t="inlineStr"><is><t>2026-10-09</t></is></c>'
        '<c r="B4"><f>1+1</f><v>9</v></c><c r="C4" t="inlineStr"><is><t>cup</t></is></c></row>')
    sheets, _, raw = discover(uuid4(), parse_source(content, 'xlsx'))
    assert sheets[0].header_row == 3 and len(sheets[0].headers) == 3
    cell = raw[0]['rows'][0]['cells'][1]
    assert cell['formula'] and cell['raw'] == '9'
    assert raw[0]['rows'][0]['row_number'] == 4
