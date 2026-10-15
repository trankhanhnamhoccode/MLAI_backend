"""Server-owned facts/numbers and bounded language variants; no NLP repair."""
from app.application.contracts.decision_evidence import DecisionEvidence
from app.application.contracts.plan_summary import (
    SummaryRequest, SummaryExpression, SummaryDiagnostics, SummaryClaim, SummaryAnswer,
)
from app.application.planning_public_projection import plain

DEFAULT_EXPRESSION = SummaryExpression(ordering=('outcome','cost','requirements','coverage','proof','limitations'),tone='plain')


def render_summary(evidence: DecisionEvidence, request: SummaryRequest, diagnostics: SummaryDiagnostics,
                   expression: SummaryExpression = DEFAULT_EXPRESSION) -> SummaryAnswer:
    overview, option = evidence.overview, evidence.option
    vi = request.locale == 'vi'
    def ref(pointer):
        return next(r.evidence_id for r in evidence.references if r.pointer == pointer)
    texts = {}
    outcome = overview.outcome
    if overview.recommendation_available:
        texts['outcome'] = ('Run có phương án được khuyến nghị.' if vi else 'This Run has a recommended option.')
        if expression.tone == 'brief':
            texts['outcome'] = ('Run này có khuyến nghị.' if vi else 'A recommendation is available for this Run.')
    elif outcome == 'no_eligible_candidate':
        texts['outcome'] = ('Chưa có phương án đủ điều kiện được chọn trong Run này.' if vi else 'No eligible option was selected in this Run.')
    elif overview.status == 'failed':
        texts['outcome'] = ('Run gặp lỗi thực thi; các phần dữ liệu đã lưu vẫn được giữ riêng.' if vi else 'The Run failed during execution; retained partial facts remain separate.')
    else:
        texts['outcome'] = ('Run chưa tạo được khuyến nghị; cần xem phần dữ liệu thiếu hoặc bị chặn.' if vi else 'The Run did not produce a recommendation; review missing or blocked evidence.')
    budget = overview.configuration.budget
    if option:
        c = option.costs
        texts['cost'] = (f'Phương án đang xem có tổng chi {c.total.decimal_view} {c.currency}, gồm tiền mua {c.purchase.decimal_view} và phí phải trả {c.payable_fees.decimal_view} {c.currency}.' if vi else
            f'The viewed option has total outlay {c.total.decimal_view} {c.currency}: purchase {c.purchase.decimal_view} and payable fees {c.payable_fees.decimal_view} {c.currency}.')
    else:
        texts['cost'] = ('Chưa có chi phí phương án để diễn giải; không thể coi là chi phí bằng không.' if vi else 'Option costs are unavailable; this does not mean zero outlay.')
    texts['cost'] += (f' Giới hạn ngân sách đã lưu là {budget.limit} {budget.currency}.' if vi else f' The retained budget limit is {budget.limit} {budget.currency}.')
    assessments = option.requirements_assessment if option else None
    if assessments is not None:
        counts = {s:sum(a.status == s for a in assessments) for s in ('PASS','FAIL','NOT_EVALUATED')}
        texts['requirements'] = (f'Các đánh giá yêu cầu theo món và đường nhu cầu: {counts["PASS"]} đạt, {counts["FAIL"]} chưa đạt, {counts["NOT_EVALUATED"]} chưa đánh giá.' if vi else
            f'Product/path requirement assessments: {counts["PASS"]} pass, {counts["FAIL"]} fail, {counts["NOT_EVALUATED"]} not evaluated.')
    else:
        texts['requirements'] = ('Chưa có đánh giá đáp ứng yêu cầu của phương án.' if vi else 'Option requirement assessments are unavailable.')
    pair=next(iter(overview.comparisons or ()),None)
    if pair:
        labels={o.option_id:'/'.join(({'lean':'tinh gọn','balanced':'cân bằng','protected':'bảo vệ'}[s] if vi else s) for s in o.source_strategies) for o in overview.options}
        left,right=labels[pair.from_option_id],labels[pair.to_option_id]
        amount=plain(pair.total_outlay_delta.decimal_view)
        texts['cost'] += (f' So sánh đã lưu từ phương án {left} sang {right}: chênh tổng chi {amount} {pair.currency} (sau trừ trước), chỉ áp dụng cho cặp này.' if vi else
            f' Retained comparison from {left} to {right}: outlay change {amount} {pair.currency} (to minus from), for this pair only.')
        change=next((p for p in pair.products if p.fulfilled.numerator!='0'),None)
        if change:
            product=next(p for p in overview.scope.menu_products if p.product_id==change.product_id)
            value=plain(change.fulfilled.decimal_view)
            texts['requirements'] += (f' Trong cùng cặp, lượng phục vụ món “{product.name}” trên đường {change.path} chênh {value} {change.unit} (sau trừ trước); không phải xếp hạng toàn cục.' if vi else
                f' In this pair, fulfilled quantity for “{product.name}” on {change.path} changes by {value} {change.unit} (to minus from); this is not a global ranking.')
    scope = overview.scope
    texts['coverage'] = ((f'Phạm vi đã tính gồm {scope.computed_count}/{scope.menu_count} món; món bị loại không có nghĩa là nhu cầu bằng không.' if vi else
        f'Computed scope covers {scope.computed_count}/{scope.menu_count} Products; exclusions do not imply zero demand.') if scope else
        ('Phạm vi tính chưa được lưu đầy đủ.' if vi else 'Computed scope is unavailable.'))
    texts['proof'] = ('Khuyến nghị chỉ so sánh các phương án đã đánh giá, không chứng minh tối ưu toàn cục.' if vi else
        'Recommendation concerns evaluated options only; it is not proof of global optimality.') if overview.selection_proof else (
        'Chưa có bằng chứng selector để giải thích thứ hạng.' if vi else 'Selector evidence for ranking is unavailable.')
    if overview.selection_proof and overview.recommendation_available:
        texts['proof'] += (' Selector xét phương án đủ điều kiện theo chi phí, sau đó mức đáp ứng từng món và thứ tự kỹ thuật khi hòa.' if vi else
            'The selector compares eligible options by outlay, then per-Product service and a stable technical tie-break.')
    if overview.status=='failed' and overview.explanation.winner.option_id is not None:
        texts['proof'] += (' Kết quả so sánh đã lưu không phải khuyến nghị khả dụng vì lần chạy gặp lỗi.' if vi else
            'The Run failed; the retained selector winner is diagnostic evidence, not an available recommendation.')
    if any(s.proof == 'UNPROVEN' or not s.search_complete for s in overview.strategies):
        texts['proof'] += (' Tìm kiếm chưa có chứng nhận đầy đủ trong miền giới hạn đã lưu.' if vi else 'Search has no complete certificate over the retained finite domain.')
    elif overview.strategies:
        texts['proof'] += (' Chứng nhận duyệt hết chỉ áp dụng cho miền hữu hạn đã lưu.' if vi else 'Enumeration certificates apply only to the retained finite domain.')
    if option and option.option_id != overview.explanation.winner.option_id:
        texts['proof'] += (' Phương án đang xem không phải phương án được khuyến nghị.' if vi else 'The viewed option is not the recommended option.')
    warnings = len(overview.explanation.warnings)
    blockers = len(overview.explanation.blockers)
    texts['limitations'] = (f'Run giữ {warnings} cảnh báo và {blockers} vấn đề chặn. Các đường nhu cầu không phải xác suất; kết quả mô phỏng không phải lượng nhận hoặc tiêu thụ thực tế. Chưa có bằng chứng nhân quả hay so sánh không mua trong summary này. Xem chi tiết trước khi quyết định; sửa dữ liệu thì tạo Run mới. Khuyến nghị không tự tạo đơn mua.' if vi else
        f'The Run retains {warnings} warnings and {blockers} blockers. Demand paths are not probabilities; simulated outcomes are not actual receipts or usage. This summary has no causal or zero-purchase comparison evidence. Review details before acting; changed data requires a new Run. Recommendation does not place an order.')
    if overview.explanation.availability != 'available':
        texts['limitations'] += (' Bằng chứng kết quả còn thiếu hoặc chỉ có một phần.' if vi else 'Result evidence is partial or unavailable.')
    if overview.temporal_basis and overview.temporal_basis.kind=='HYPOTHETICAL_CURRENT_CAPTURE':
        texts['limitations'] += (' Ngày lập kế hoạch khác ngày chụp dữ liệu; tồn hiện tại được dùng theo giả định, không phải tồn kho lịch sử.' if vi else
            'Planning and capture dates differ; current stock is used hypothetically, not as historical inventory.')
    if request.detail_level == 'technical':
        texts['limitations'] += (' Evidence schema decision_evidence/1; source schema ' if vi else ' Evidence schema decision_evidence/1; source schema ') + (evidence.identity.result_schema_version or 'unavailable') + '.'
    sources = {
        'outcome':('/overview/outcome','/overview/explanation'),
        'cost':('/overview/configuration',) + (('/option/costs',) if option else ('/overview/omissions',)),
        'requirements':('/option/requirements_assessment',) if option else ('/overview/explanation',),
        'coverage':('/overview/scope',),
        'proof':('/overview/selection_proof','/overview/strategies','/overview/explanation'),
        'limitations':('/overview/explanation','/overview/omissions','/overview/assumptions','/overview/temporal_basis'),
    }
    if pair:
        sources['cost'] += ('/overview/comparisons',)
        sources['requirements'] += ('/overview/comparisons','/overview/scope')
    claims = tuple(SummaryClaim(family=k,text=texts[k],evidence_ids=tuple(ref(p) for p in sources[k])) for k in expression.ordering)
    used = {i for claim in claims for i in claim.evidence_ids}
    result = SummaryAnswer(identity=evidence.identity,option_id=option.option_id if option else None,locale=request.locale,
        detail_level=request.detail_level,source='model_presentation' if diagnostics.disposition == 'ACCEPTED' else 'deterministic_fallback',presentation=expression,
        answer='\n\n'.join(c.text for c in claims),claims=claims,
        references=tuple(r for r in evidence.references if r.evidence_id in used),diagnostics=diagnostics)
    for claim in result.claims:
        for ident in claim.evidence_ids: evidence.resolve(ident)
    return result
