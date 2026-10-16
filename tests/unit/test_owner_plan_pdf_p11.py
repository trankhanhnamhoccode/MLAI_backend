"""P1.1 owner language, retained temporal scope and immutable /2 compatibility."""
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
from pypdf import PdfReader
import pytest
from app.application.contracts.planning_pdf import PlanningPDFDocument
from app.application.planning_public_projection import quantity
from app.infrastructure.planning_pdf_renderer import PlanningPDFRenderer
from app.infrastructure.planning_pdf_wording import base_assessment, temporal_note, unmet_note, proof_notes, proof_trace
from tests.fixtures.owner_plan_pdf import owner_document, representative_document


def changed(doc, edit):
    data = doc.model_dump(mode='json')
    edit(data)
    return PlanningPDFDocument.model_validate(data)


def text(doc):
    reader = PdfReader(BytesIO(PlanningPDFRenderer().render(doc)))
    return [' '.join(page.extract_text().split()) for page in reader.pages]


def test_front_page_decision_costs_budget_dates_and_base_scope():
    first = text(representative_document())[0]
    for value in ('10/10/2026 đến 16/10/2026', 'Tổng chi dự kiến', '4.235.000 ₫',
                  'Ngân sách hiệu lực / trần cửa hàng đã lưu', '10.000.000 ₫',
                  'Đang xuất phương án được khuyến nghị', '5/5 món', 'Kịch bản cơ sở (BASE)', 'DỮ LIỆU SYNTHETIC'):
        assert value in first, value
    assert 'Chiến lược tạo phương án' not in first
    assert first.count('10.000.000 ₫') == 1


def test_budget_limits_are_separate_when_different_and_viewed_option_is_reference():
    def edit(d):
        d['view']['configuration']['budget']['ceiling_at_acceptance'] = '3000000'
        d['option']['option_id'] = 'viewed-other'
    first = text(changed(owner_document(), edit))[0]
    assert 'Đang xem phương án tham khảo' in first
    assert 'Ngân sách hiệu lực đã lưu' in first and '2.000.000 ₫' in first
    assert 'Trần cửa hàng lúc nhận yêu cầu' in first and '3.000.000 ₫' in first


@pytest.mark.parametrize('kind,marked', [('CURRENT_CAPTURE', False), ('CURRENT_CAPTURE', True),
                                       ('HYPOTHETICAL_CURRENT_CAPTURE', False), ('HYPOTHETICAL_CURRENT_CAPTURE', True),
                                       (None, False)])
def test_temporal_kind_and_synthetic_never_certify_real_inventory(kind, marked):
    def edit(d):
        if kind is None:
            d['view']['operational_basis'] = None
        else:
            basis = d['view']['operational_basis']
            basis['kind'] = kind
            if kind == 'HYPOTHETICAL_CURRENT_CAPTURE':
                basis['planning_start_date'] = '2026-10-12'
                d['view']['request']['forecast_start_date'] = '2026-10-12'
        if not marked:
            for item in d['ingredients']:
                item['captured_stock']['provenance'] = 'unclassified saved evidence'
    note = temporal_note(changed(owner_document(), edit))
    assert 'tồn kho đầu vào đã lưu' in note.lower()
    if kind == 'HYPOTHETICAL_CURRENT_CAPTURE':
        assert 'giả định ngày 12/10/2026' in note and 'chụp ngày 10/10/2026' in note
        assert 'không coi đây là tồn kho lịch sử' in note
    elif kind == 'CURRENT_CAPTURE':
        assert 'các biến động và tiêu thụ sau đó là mô phỏng' in note
    else:
        assert 'chưa có thông tin đầy đủ' in note
    assert ('giả lập' in note) == marked


def test_same_proof_coalesces_but_incomplete_error_and_finite_scope_remain():
    doc = owner_document()
    strategies = doc.view.result.strategies
    assert len(proof_notes(strategies, True)) == 1
    assert 'vẫn có thể còn lựa chọn khác' in proof_notes(strategies, True)[0]
    changed_items = [s.model_dump() for s in strategies]
    changed_items[1]['execution'] = 'ERROR'
    changed_items[2]['execution'] = 'INCOMPLETE'
    from app.application.contracts.planning_public import StrategyResult
    notes = proof_notes(tuple(StrategyResult.model_validate(s) for s in changed_items), False)
    assert len(notes) == 3
    assert 'Cân bằng: Việc tìm phương án gặp lỗi thực thi' in notes[1]
    assert 'Bảo vệ: Việc tìm phương án chưa hoàn tất' in notes[2]
    finite = tuple(s.model_copy(update={'proof': 'COMPLETE_EXACT_ENUMERATION', 'search_complete': True}) for s in strategies)
    assert 'phạm vi giới hạn của dữ liệu đã lưu' in proof_notes(finite, False)[0]
    assert 'không áp dụng' in proof_notes(finite, False)[0]


def test_shortage_summary_names_actual_paths_without_counting_product_twice():
    doc = representative_document()
    note = unmet_note(doc)
    assert 'kịch bản cơ sở và cao' in note and 'mô phỏng' in note
    assert '10' not in note and 'thấp' not in note
    def edit(d):
        for row in d['option']['product_services']:
            row['lost_sales'] = quantity(Fraction(1, 10**9) if row['path'] == 'LOW' else Fraction()).model_dump(mode='json')
    assert 'kịch bản thấp.' in unmet_note(changed(doc, edit))
    def ingredient_only(d):
        for row in d['option']['product_services']:
            row['lost_sales'] = quantity(Fraction()).model_dump(mode='json')
        d['ingredients'][0]['daily_balances'][0]['shortage'] = quantity(Fraction(1)).model_dump(mode='json')
    assert 'chưa ghi nhận' in unmet_note(changed(doc, ingredient_only)).lower()


def test_header_does_not_average_or_claim_coverage_for_missing_assessments():
    doc = representative_document()
    assert '5/5 món' in base_assessment(doc)
    def edit(d):
        d['option']['requirements_assessment'] = d['option']['requirements_assessment'][:1]
    assert 'Chưa đủ đánh giá' in base_assessment(changed(doc, edit))


def test_store_local_time_not_utc_date_or_machine_clock():
    def edit(d):
        d['view']['operational_basis']['captured_at'] = '2026-10-09T18:30:00Z'
    first = text(changed(owner_document(), edit))[0]
    assert '10/10/2026 01:30 (Asia/Ho_Chi_Minh)' in first
    assert '09/10/2026 18:30' not in first


def test_mixed_finite_and_unproven_or_feasibility_never_coalesce():
    strategies = list(owner_document().view.result.strategies)
    strategies[1] = strategies[1].model_copy(update={'proof': 'COMPLETE_EXACT_ENUMERATION', 'search_complete': True})
    strategies[2] = strategies[2].model_copy(update={'customer_feasibility': 'UNKNOWN'})
    notes = proof_notes(tuple(strategies), True)
    assert len(notes) == len(proof_trace(tuple(strategies))) == 3
    assert 'Cân bằng: Đã kiểm tra đầy đủ' in notes[1]
    assert 'ngoài phạm vi đó' in notes[1]
    assert 'vẫn có thể còn lựa chọn khác' in notes[0]
    assert 'customer_feasibility=UNKNOWN' in proof_trace(tuple(strategies))[2]


def test_primary_prose_is_vietnamese_and_preserves_canonical_unit():
    pages = text(representative_document())
    combined = ' '.join(pages)
    main = combined.split('4. Cách đọc và truy vết')[0]
    for technical in ('snapshot', 'provenance', 'dump', 'KPI', 'miền hữu hạn', 'tối ưu toàn cục'):
        assert technical not in main
    assert 'cup' in combined and 'ly' not in combined.split('Đơn vị được giữ nguyên')[0]
    assert 'chưa có nhãn tiếng Việt được xác nhận' in combined
    assert '2026-10-' not in main and '14/01/2027' in combined


def test_missing_scope_and_service_stay_unknown_without_unrelated_unit_example():
    def edit(d):
        d['view']['scope'] = None
        d['option']['product_services'] = []
    pages = text(changed(owner_document(), edit))
    assert 'Chưa đủ đánh giá' in pages[0]
    assert 'chưa có nhãn tiếng Việt' not in ' '.join(pages)


def test_frozen_v2_reproduces_exact_p1_primary_bytes():
    renderer = PlanningPDFRenderer()
    assert sha256(renderer.render_v2(representative_document())).hexdigest() == '942cca925ebade2bfb5ad885b253059042dd89c39038176392a51ac947c7fee1'
