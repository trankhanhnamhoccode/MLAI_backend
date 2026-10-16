"""Deterministic /3 presentation sentences, without new business calculations."""
from collections import OrderedDict
from datetime import date
from app.application.contracts.planning_pdf import PlanningPDFDocument
from app.application.contracts.planning_public import StrategyResult
from app.infrastructure.planning_pdf_display import fraction, SYNTHETIC_PROVENANCE, STRATEGIES

PATH_NAMES = {'BASE': 'cơ sở', 'LOW': 'thấp', 'HIGH': 'cao'}


def day(value: date | None) -> str:
    return value.strftime('%d/%m/%Y') if value is not None else 'Chưa biết'


def synthetic(document: PlanningPDFDocument) -> bool:
    return any(i.captured_stock.provenance in SYNTHETIC_PROVENANCE for i in document.ingredients)


def temporal_note(document: PlanningPDFDocument) -> str:
    basis = document.view.operational_basis
    if basis is None:
        result = 'Mô phỏng dùng tồn kho đầu vào đã lưu; chưa có thông tin đầy đủ về thời điểm chụp và ngày áp dụng.'
    elif basis.kind == 'CURRENT_CAPTURE':
        result = 'Tồn kho đầu vào đã lưu là dữ liệu tại thời điểm chụp; các biến động và tiêu thụ sau đó là mô phỏng.'
    else:
        result = ('Kế hoạch giả định ngày ' + day(basis.planning_start_date)
                  + ' dùng tồn kho đầu vào đã lưu tại thời điểm chụp ngày ' + day(basis.local_capture_date)
                  + '; không coi đây là tồn kho lịch sử tại ngày kế hoạch. Các biến động và tiêu thụ sau đó là mô phỏng.')
    if synthetic(document):
        result += ' Nguồn đã đánh dấu giả lập; tồn đầu vào chưa được chứng nhận là tồn thực đã kiểm chứng.'
    return result


def base_assessment(document: PlanningPDFDocument) -> str:
    """Count distinct assessed Products on BASE only; no average service ratio."""
    scope = document.view.scope
    if scope is None or not scope.computed_product_ids:
        return 'Chưa đủ đánh giá đã lưu để kết luận mức đáp ứng trong kịch bản cơ sở (BASE).'
    products = set(scope.computed_product_ids)
    assessments = {a.product_id: a.status for a in document.option.requirements_assessment
                   if a.path == 'BASE' and a.product_id in products}
    evaluated = {r.product_id for r in document.option.product_services if r.path == 'BASE'}
    if not products <= evaluated or any(assessments.get(p) not in ('PASS', 'FAIL') for p in products):
        return 'Chưa đủ đánh giá đã lưu để kết luận mức đáp ứng trong kịch bản cơ sở (BASE).'
    passed = sum(assessments[p] == 'PASS' for p in products)
    result = f'Kịch bản cơ sở (BASE): {passed}/{len(products)} món trong phạm vi tính toán đạt yêu cầu đã lưu.'
    if scope.coverage_status != 'full':
        result += ' Kết luận chỉ áp dụng cho phạm vi đã đánh giá, không bao gồm món bị loại.'
    return result


def unmet_note(document: PlanningPDFDocument) -> str:
    paths = {row.path for row in document.option.product_services if fraction(row.lost_sales) > 0}
    if not paths:
        return 'Chưa ghi nhận nhu cầu chưa đáp ứng dương trong các kết quả mô phỏng đã lưu; chưa kết luận cho món chưa đánh giá.'
    ordered = [PATH_NAMES[p] for p in ('BASE', 'LOW', 'HIGH') if p in paths]
    joined = ' và '.join(ordered) if len(ordered) <= 2 else ', '.join(ordered[:-1]) + ' và ' + ordered[-1]
    return ('Một số món chưa được đáp ứng đủ trong kịch bản ' + joined
            + '. Đây là kết quả mô phỏng. Xem cột “Chưa đáp ứng” tại phần khả năng đáp ứng.')


def _proof_groups(strategies: tuple[StrategyResult, ...]) -> tuple[tuple[StrategyResult, ...], ...]:
    """Keep execution, search/proof/scope and both feasibility states separate."""
    groups: OrderedDict[tuple, list[StrategyResult]] = OrderedDict()
    for item in strategies:
        key = (item.execution, item.proof, item.proof_scope, item.search_complete,
               item.customer_feasibility, item.construction_feasibility)
        groups.setdefault(key, []).append(item)
    return tuple(tuple(items) for items in groups.values())


def proof_notes(strategies: tuple[StrategyResult, ...], recommended: bool) -> tuple[str, ...]:
    if not strategies:
        return ('Chưa có kết quả tìm phương án để kết luận tính khả thi.',)
    groups = _proof_groups(strategies)
    notes = []
    for items in groups:
        item = items[0]
        label = ', '.join(STRATEGIES[s.strategy] for s in items) + ': ' if len(groups) > 1 else ''
        execution = {'FINISHED': '', 'INCOMPLETE': 'Việc tìm phương án chưa hoàn tất. ',
                     'ERROR': 'Việc tìm phương án gặp lỗi thực thi. ', 'BLOCKED': 'Việc tìm phương án bị chặn. ',
                     'NUMERIC_UNSUPPORTED': 'Có giá trị số chưa được hỗ trợ khi tìm phương án. '}[item.execution]
        if item.proof == 'COMPLETE_EXACT_ENUMERATION' and item.search_complete:
            proof = ('Đã kiểm tra đầy đủ các lựa chọn trong phạm vi giới hạn của dữ liệu đã lưu; '
                     'kết luận không áp dụng cho nguồn cung hoặc lựa chọn ngoài phạm vi đó.')
        else:
            proof = (('Đề xuất' if recommended else 'Kết quả so sánh')
                     + ' dựa trên các phương án đã kiểm tra; vẫn có thể còn lựa chọn khác chưa được tìm thấy.')
        if item.customer_feasibility == 'NO_PASS_CERTIFIED':
            proof += ' Không có phương án đạt yêu cầu trong phạm vi đã được kiểm tra và xác nhận.'
        notes.append(label + execution + proof)
    return tuple(notes)


def proof_trace(strategies: tuple[StrategyResult, ...]) -> tuple[str, ...]:
    """Codes remain reachable without repeating identical proof metadata."""
    rows = []
    for items in _proof_groups(strategies):
        item = items[0]
        names = ', '.join(STRATEGIES[s.strategy] for s in items)
        rows.append(f'{names}: execution={item.execution}; proof={item.proof}; scope={item.proof_scope}; '
                    f'search_complete={item.search_complete}; customer_feasibility={item.customer_feasibility}; '
                    f'construction_feasibility={item.construction_feasibility}')
    return tuple(rows)
