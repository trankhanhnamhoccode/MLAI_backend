"""Owner PDF facts, scope and display precision; no network/database/provider."""
from datetime import date
from fractions import Fraction
from io import BytesIO
from uuid import UUID
import pytest
from pypdf import PdfReader
from app.infrastructure.planning_pdf_renderer import PlanningPDFRenderer
from app.infrastructure.planning_pdf_display import number, money, RetainedLabels, grouped_notices
from app.application.contracts.planning_pdf import PlanningPDFDocument
from app.application.contracts.planning_public import PlanningNotification, PlanningNotificationDetails
from app.application.planning_public_projection import quantity
from tests.fixtures.owner_plan_pdf import owner_document, representative_document


def pdf_text(document):
    reader = PdfReader(BytesIO(PlanningPDFRenderer().render(document)))
    return '\n'.join(p.extract_text() for p in reader.pages), reader


@pytest.mark.parametrize('amount,places,expected', [
    (Fraction(1, 3), 3, '~ 0,333'), (Fraction(1, 100000), 3, '< 0,001'),
    (Fraction(4235000), 0, '4.235.000'), (Fraction(1, 2), 0, '< 1'),
    (Fraction(0), 3, '0'), (None, 3, 'Chưa biết / chưa đánh giá'),
    (Fraction(19999, 2000), 3, '~ 10'),
])
def test_display_exact_small_null_and_rounding(amount, places, expected):
    assert number(amount, places) == expected


def test_money_currency_is_never_converted():
    assert money('4235000', 'VND') == '4.235.000 ₫'
    assert money('12.345', 'USD') == '~ 12,35 USD'
    assert money('0.0001', 'EUR') == '< 0,01 EUR'
    assert money('1.2345', 'XXX') == '~ 1,235 XXX'


def test_owner_report_snapshot_oracle_and_no_dump():
    doc = owner_document()
    before = doc.model_dump_json()
    text, reader = pdf_text(doc)
    assert 3 <= len(reader.pages) <= 5
    for value in ('1.380.000 ₫', '1.355.000 ₫', '25.000 ₫', '2.000.000 ₫', '420.000 ₫',
                  'Cà phê sữa đá đặc biệt', 'Cà phê rang xay nguyên chất', '2 gói', '2.000 g',
                  'Nhu cầu cơ sở (BASE)', 'Nhu cầu thấp (LOW)', 'Nhu cầu cao (HIGH)',
                  'DỮ LIỆU SYNTHETIC', '10/10/2026 09:00', 'vẫn có thể còn lựa chọn khác', 'CAPTURED_FINITE_DOMAIN_ONLY'):
        assert value in ' '.join(text.split()), value
    assert str(doc.view.run_id) not in reader.pages[0].extract_text()
    assert str(doc.view.run_id) in text and doc.explanation.result_digest in text
    assert 'exact ' not in text and 'Phụ lục đầy đủ' not in text and 'daily_balances[' not in text
    assert doc.model_dump_json() == before
    assert PlanningPDFRenderer().render(doc) == PlanningPDFRenderer().render(doc)


def test_notices_group_dates_without_merging_entities_or_scope():
    def notice(day, entity=UUID(int=1), field='recipe'):
        return PlanningNotification(code='RECIPE_MISSING', message='Thiếu công thức',
            details=PlanningNotificationDetails(entity='product', entity_id=entity, field=field, affected_dates=(date(2026, 10, day),)))
    groups = grouped_notices(tuple(notice(d) for d in range(10, 17)) + (notice(10, UUID(int=2)), notice(10, field='other')))
    assert len(groups) == 3
    assert groups[0][1] == tuple(f'2026-10-{d}' for d in range(10, 17))


def test_missing_names_codes_are_distinct_even_with_colliding_suffixes():
    doc = owner_document()
    # Same final four hex characters, different entity IDs.
    data = doc.model_dump(mode='json')
    for i, row in enumerate(data['option']['purchases']):
        row['supplier_id'] = str(UUID(int=(i + 1) * 65536 + 1))
    doc = PlanningPDFDocument.model_validate(data)
    labels = RetainedLabels(doc)
    names = [labels.name('Nhà cung cấp', p.supplier_id) for p in doc.option.purchases]
    assert len(set(names)) == 3
    assert all('chưa lưu tên' in name for name in names)


def test_reference_zero_purchase_and_missing_evidence():
    data = owner_document().model_dump(mode='json')
    option = data['option']
    option['option_id'] = 'explicit-reference'
    option['eligible'] = False
    option['purchases'] = []
    option['product_services'] = []
    for field in ('purchase', 'payable_fees', 'total'):
        option['costs'][field] = quantity(Fraction()).model_dump(mode='json')
    option['costs']['fee_components'] = []
    option['costs']['fee_classification'] = 'NONE'
    for detail in data['ingredients']:
        detail['display_name'] = None
        detail['name_availability'] = 'not_captured'
        detail['daily_balances'] = None
    text, _ = pdf_text(PlanningPDFDocument.model_validate(data))
    assert 'KHÔNG PHẢI KHUYẾN NGHỊ' in text
    assert 'không phát sinh dòng mua' in text and '0 ₫' in text
    assert 'Chưa đánh giá' in text and 'chưa có đánh giá mô phỏng' in text


def test_long_unicode_names_many_lines_are_not_truncated():
    data = owner_document().model_dump(mode='json')
    data['ingredients'][0]['display_name'] = 'Cà phê Việt Nam <đậm & thơm> ' * 6
    original = data['option']['purchases'][0]
    data['option']['purchases'] = [{**original, 'arrival_date': f'2026-10-{10 + i % 7}'}
                                   for i in range(50)]
    text, reader = pdf_text(PlanningPDFDocument.model_validate(data))
    assert len(reader.pages) > 5
    assert '50.' in text and '<đậm & thơm>' in text
    assert all('Trang ' + str(i) in page.extract_text() for i, page in enumerate(reader.pages, 1))


def test_partial_scope_risks_fractional_service_and_unknown_ratio():
    data = owner_document().model_dump(mode='json')
    pid = str(UUID(int=999))
    data['view']['scope']['menu_products'].append(dict(product_id=pid, name='Món bị loại chưa có công thức', selling_unit='cup'))
    data['view']['scope'].update(menu_count=2, coverage_status='partial')
    data['explanation']['exclusions'] = [dict(product_id=pid, reason_codes=['RECIPE_MISSING'], affected_dates=['2026-10-10'])]
    data['explanation']['availability'] = 'partial'
    service = data['option']['product_services'][1]
    q = lambda n: quantity(Fraction(n)).model_dump(mode='json')
    service.update(fulfilled=q(Fraction(104, 3)), lost_sales=q(Fraction(1, 3)),
                   service=dict(numerator='104', denominator='105', percent_view=quantity(Fraction(10400, 105)).decimal_view))
    day = data['ingredients'][0]['daily_balances'][7]
    day['shortage'] = q(Fraction(1, 100000))
    day['expired'] = q(Fraction(1, 3))
    text, _ = pdf_text(PlanningPDFDocument.model_validate(data))
    normalized = ' '.join(text.split())
    for phrase in ('1/2 món', 'Món bị loại chưa có công thức', 'loại khỏi phạm vi, chưa đánh giá',
                   '~ 34,667 cup', '~ 0,333 cup', '~ 99 %', '< 0,001 g', 'Thiếu nguyên liệu mô phỏng', 'Hết hạn mô phỏng'):
        assert phrase in normalized, phrase
    service['service'] = None
    text, _ = pdf_text(PlanningPDFDocument.model_validate(data))
    assert 'Chưa biết / chưa đánh giá' in text


def test_eligible_option_different_from_winner_is_reference():
    data = owner_document().model_dump(mode='json')
    data['option']['option_id'] = 'another-evaluated-option'
    text, _ = pdf_text(PlanningPDFDocument.model_validate(data))
    first = ' '.join(text.split())
    assert 'Đang xem phương án tham khảo' in first
    assert 'Đang xuất phương án được khuyến nghị' not in first


def test_zero_demand_is_not_a_claim_of_full_service():
    data = owner_document().model_dump(mode='json')
    for row in data['option']['product_services']:
        for field in ('requested', 'fulfilled', 'lost_sales'):
            row[field] = quantity(Fraction()).model_dump(mode='json')
        row['service'] = None
    text, _ = pdf_text(PlanningPDFDocument.model_validate(data))
    assert 'Không xác định' in text
    assert 'nhu cầu bằng 0' in text


def test_absence_of_marker_does_not_infer_synthetic_from_names():
    data = owner_document().model_dump(mode='json')
    for detail in data['ingredients']:
        detail['captured_stock']['provenance'] = 'unclassified source'
    text, _ = pdf_text(PlanningPDFDocument.model_validate(data))
    assert 'DỮ LIỆU SYNTHETIC' not in text
    data['ingredients'][0]['captured_stock']['provenance'] = 'User-requested SYNTHETIC local demo; no real inventory/sales/order evidence'
    text, _ = pdf_text(PlanningPDFDocument.model_validate(data))
    assert 'DỮ LIỆU SYNTHETIC' in text


def test_representative_five_dishes_seven_inputs_six_lines():
    doc = representative_document()
    text, reader = pdf_text(doc)
    assert len(doc.ingredients) == 7 and len(doc.option.purchases) == 6
    assert doc.view.scope.menu_count == 5
    assert 3 <= len(reader.pages) <= 5
    assert '4.235.000 ₫' in text
    assert '6.' in text and 'Trà sữa ô long' in text
    assert sum(Fraction(int(p.purchase_outlay.numerator), int(p.purchase_outlay.denominator))
               for p in doc.option.purchases) == 4235000
