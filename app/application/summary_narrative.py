"""BE communication selection and closed clause reconciliation, without a model judge.

Each permitted full clause denotes exactly one selected typed fact. Matching a
whole clause, its family and issued references is deliberately conservative;
arbitrary prose with matching numbers/citations cannot pass this summary guard.
No user labels/source text enter the provider vocabulary. No NLP string repair.
"""
from dataclasses import dataclass
from app.application.contracts.decision_evidence import DecisionEvidence
from app.application.contracts.plan_summary import BlockKey, SummaryAnswer, SummaryClaim, SummaryDiagnostics, SummaryRequest, SummaryProfile
from app.application.contracts.summary_narrative import NarrativeClause, NarrativeSection, SummaryNarrative
from app.application.contracts.summary_narrative import CompactNarrative
from app.application.plan_summary_rendering import DEFAULT_EXPRESSION

VERSIONS = dict(renderer='plan_summary_renderer/2', prompt='plan_summary_prompt/2',
                schema='summary_narrative/2', validator='summary_narrative_guard/2')
OLD_VERSIONS = dict(renderer='plan_summary_renderer/1', prompt='plan_summary_prompt/1',
                    schema='plan_summary/1', validator='summary_presentation_guard/1')


def versions(profile: SummaryProfile) -> dict[str, str]:
    if profile.version == 'summary_profile/4':
        return {**VERSIONS,'prompt':'plan_summary_prompt/3','schema':'summary_narrative/3'}
    return VERSIONS if profile.version in {'summary_profile/2','summary_profile/3'} else OLD_VERSIONS


def diagnostics_v2(diagnostics: SummaryDiagnostics) -> SummaryDiagnostics:
    prompt=diagnostics.prompt_version if diagnostics.prompt_version=='plan_summary_prompt/3' else VERSIONS['prompt']
    return diagnostics.model_copy(update={'prompt_version': prompt, 'validator_version': VERSIONS['validator']})


def expand_compact(plan: tuple['CommunicationFact',...], compact: CompactNarrative) -> SummaryNarrative:
    expected={f.fact_id:f for f in plan}
    if any(c.fact_id not in expected for c in compact.clauses):raise ValueError('Unknown compact fact binding')
    def section(family):
        return NarrativeSection(family=family,clauses=tuple(NarrativeClause(fact_id=c.fact_id,text=c.text,
            evidence_ids=expected[c.fact_id].evidence_ids) for c in compact.clauses if expected[c.fact_id].family==family))
    return SummaryNarrative(schema_version='summary_narrative/2',headline=section('outcome'),summary=section('cost'),
        key_points=tuple(section(k) for k in ('requirements','coverage','proof')),warning_summary=section('limitations'))


@dataclass(frozen=True)
class CommunicationFact:
    fact_id: str
    family: BlockKey
    evidence_ids: tuple[str, ...]
    surfaces: tuple[str, ...]


def communication_plan(evidence: DecisionEvidence, request: SummaryRequest) -> tuple[CommunicationFact, ...]:
    """Select material facts, not metrics invented from forecast provenance."""
    overview, option = evidence.overview, evidence.option
    vi = request.locale == 'vi'
    facts = []

    def add(key, family, pointers, vietnamese, english):
        refs = tuple(next(r.evidence_id for r in evidence.references if r.pointer == p) for p in pointers)
        surfaces = vietnamese if vi else english
        facts.append(CommunicationFact(key, family, refs, tuple(surfaces)))

    if overview.recommendation_available:
        winner = next(o for o in overview.options if o.option_id == overview.explanation.winner.option_id)
        labels = {'lean':'tinh gọn', 'balanced':'cân bằng', 'protected':'bảo vệ'}
        strategy = '/'.join(labels[s] if vi else s for s in winner.source_strategies)
        add('recommendation', 'outcome', ('/overview/recommendation_available','/overview/explanation','/overview/options'),
            (f'Kế hoạch đề xuất phương án {strategy}.', f'Phương án {strategy} được khuyến nghị cho kế hoạch này.'),
            (f'The plan recommends the {strategy} option.', f'The recommended option is {strategy}.'))
    else:
        state = ('error' if overview.status == 'failed' else 'no_eligible' if overview.outcome == 'no_eligible_candidate'
                 else 'blocked' if overview.outcome == 'computation_blocked' else 'missing')
        messages = {
            'error':(('Lần chạy gặp lỗi thực thi và không có khuyến nghị khả dụng.', 'Chưa có khuyến nghị khả dụng vì lần chạy gặp lỗi thực thi.'),
                     ('Execution failed; no recommendation is available.',)),
            'no_eligible':(('Chưa có phương án đủ điều kiện được chọn trong lần chạy này.', 'Lần chạy này chưa chọn được phương án đủ điều kiện.'),
                            ('No eligible option was selected in this Run.',)),
            'blocked':(('Việc tính kế hoạch bị chặn; chưa có khuyến nghị.', 'Chưa có khuyến nghị do việc tính kế hoạch bị chặn.'),
                        ('Computation was blocked; no recommendation is available.',)),
            'missing':(('Chưa có đủ bằng chứng kết quả để đưa ra khuyến nghị.',), ('Result evidence is insufficient for a recommendation.',)),
        }
        add(state, 'outcome', ('/overview/status','/overview/outcome','/overview/recommendation_available'), *messages[state])

    if option:
        if overview.status == 'failed' or not overview.recommendation_available:
            add('reference', 'cost', ('/overview/recommendation_available','/option/option_id'),
                ('Phương án đang xem chỉ là dữ liệu tham khảo, không phải khuyến nghị khả dụng.',),
                ('The viewed option is reference evidence, not an available recommendation.',))
        elif option.option_id != overview.explanation.winner.option_id:
            add('viewed', 'cost', ('/option/option_id','/overview/explanation'),
                ('Chi phí dưới đây thuộc phương án đang xem, khác phương án được khuyến nghị.',),
                ('The following costs belong to the viewed option, not the recommendation.',))
        c = option.costs
        # decimal_view is for display; nonterminating fractions retain exact meaning.
        def amount(q):
            from decimal import Decimal
            from fractions import Fraction
            exact = Fraction(int(q.numerator), int(q.denominator))
            return q.decimal_view if Fraction(Decimal(q.decimal_view)) == exact else f'{q.numerator}/{q.denominator}'
        total, purchase, fee = (amount(q) for q in (c.total,c.purchase,c.payable_fees))
        add('costs', 'cost', ('/option/option_id','/option/costs'),
            (f'Tổng chi của phương án đang xem là {total} {c.currency}, gồm tiền mua {purchase} {c.currency} và phí phải trả {fee} {c.currency}.',
             f'Phương án đang xem cần tổng chi {total} {c.currency}: tiền mua {purchase} {c.currency}, phí phải trả {fee} {c.currency}.'),
            (f'The viewed option has total outlay {total} {c.currency}: purchase {purchase} {c.currency}, payable fees {fee} {c.currency}.',))
        if not option.purchases:
            add('zero_purchase', 'cost', ('/option/purchases','/option/costs'),
                ('Phương án này không cần mua thêm nguyên liệu.', 'Không phát sinh mua thêm nguyên liệu trong phương án này.'),
                ('This option requires no additional ingredient purchases.',))
        if c.fee_classification == 'PAYABLE_FEE_TYPE_NOT_CAPTURED':
            add('fee_kind', 'limitations', ('/option/costs',),
                ('Phí phải trả đã được lưu nhưng chưa xác định là phí giao hàng.',),
                ('Payable fees are retained, but their classification as delivery fees is unavailable.',))
    else:
        add('cost_missing', 'cost', ('/overview/omissions',),
            ('Chưa có chi phí phương án; không thể coi chi phí chưa biết là bằng không.',),
            ('Option costs are unavailable; unknown costs do not mean zero.',))
    budget = overview.configuration.budget
    add('budget', 'cost', ('/overview/configuration',),
        (f'Giới hạn ngân sách đã lưu là {budget.limit} {budget.currency}.',),
        (f'The retained budget limit is {budget.limit} {budget.currency}.',))

    assessments = option.requirements_assessment if option else None
    if assessments is not None:
        passed, failed, unevaluated = (sum(a.status == s for a in assessments) for s in ('PASS','FAIL','NOT_EVALUATED'))
        add('assessments', 'requirements', ('/option/requirements_assessment',),
            (f'Đánh giá theo món và đường nhu cầu ghi nhận {passed} đạt, {failed} chưa đạt và {unevaluated} chưa đánh giá.',
             f'Có {passed} đánh giá đạt, {failed} chưa đạt, {unevaluated} chưa đánh giá theo từng món và đường nhu cầu.'),
            (f'Product/path assessments record {passed} pass, {failed} fail and {unevaluated} not evaluated.',))
    else:
        add('assessments_missing', 'requirements', ('/overview/explanation',),
            ('Chưa có đánh giá đáp ứng yêu cầu của phương án.',), ('Option requirement assessments are unavailable.',))
    scope = overview.scope
    if scope:
        add('scope', 'coverage', ('/overview/scope',),
            (f'Kế hoạch đã tính {scope.computed_count}/{scope.menu_count} món.', f'Phạm vi đã tính gồm {scope.computed_count} trong tổng số {scope.menu_count} món.'),
            (f'The computed scope covers {scope.computed_count}/{scope.menu_count} Products.',))
        if scope.excluded_products:
            add('exclusions', 'coverage', ('/overview/scope',),
                ('Các món bị loại chưa được đánh giá; không có nghĩa nhu cầu của chúng bằng không.',),
                ('Excluded Products are not evaluated; their demand is not zero by implication.',))
    else:
        add('scope_missing', 'coverage', ('/overview/scope',), ('Phạm vi tính chưa được lưu đầy đủ.',), ('Computed scope is unavailable.',))
    if overview.forecast:
        start, end = overview.forecast.start_date.isoformat(), overview.forecast.end_date.isoformat()
        add('horizon', 'coverage', ('/overview/forecast',),
            (f'Khoảng dự báo đã lưu từ {start} đến {end}.',),
            (f'The retained forecast horizon is {start} to {end}.',))
    unproven = any(s.proof == 'UNPROVEN' or not s.search_complete for s in overview.strategies)
    if unproven:
        add('unproven', 'proof', ('/overview/strategies',),
            ('Tìm kiếm chưa được chứng minh đầy đủ trong miền giới hạn đã lưu.', 'Kết quả tìm kiếm còn thiếu chứng nhận đầy đủ trong miền đã lưu.'),
            ('Search is incomplete or unproven over the retained finite domain.',))
    elif overview.strategies:
        add('finite', 'proof', ('/overview/strategies',),
            ('Chứng nhận tìm kiếm chỉ áp dụng cho miền hữu hạn đã lưu.',), ('Search certification applies only to the retained finite domain.',))
    else:
        add('proof_missing', 'proof', ('/overview/strategies',), ('Chưa có bằng chứng tìm kiếm để kết luận tính khả thi.',), ('Search evidence cannot establish feasibility.',))
    if overview.selection_proof:
        add('evaluated', 'proof', ('/overview/selection_proof',),
            ('Việc so sánh chỉ bao gồm các phương án đã đánh giá, không chứng minh tối ưu toàn cục.',),
            ('Comparison concerns evaluated options only; global optimality is not established.',))
    warnings, blockers = len(overview.explanation.warnings), len(overview.explanation.blockers)
    if warnings or blockers:
        add('notices', 'limitations', ('/overview/explanation',),
            (f'Lần chạy lưu {warnings} cảnh báo và {blockers} vấn đề chặn cần xem trong chi tiết.',),
            (f'The Run retains {warnings} warnings and {blockers} blockers; review their details.',))
    if any(n.code == 'PAYABLE_FEE_UNKNOWN' for n in (*overview.explanation.warnings,*overview.explanation.blockers)):
        add('unknown_fee', 'limitations', ('/overview/explanation',),
            ('Phạm vi phí phải trả chưa được xác định đầy đủ; không được mặc định phí bằng không.',),
            ('Payable fee coverage is unknown; fees cannot be assumed zero.',))
    if overview.explanation.availability != 'available':
        add('partial', 'limitations', ('/overview/explanation',), ('Bằng chứng kết quả còn thiếu hoặc chỉ có một phần.',), ('Result evidence is partial or unavailable.',))
    if overview.temporal_basis and overview.temporal_basis.kind == 'HYPOTHETICAL_CURRENT_CAPTURE':
        add('hypothetical', 'limitations', ('/overview/temporal_basis',),
            ('Tồn hiện tại được dùng theo giả định cho ngày kế hoạch khác ngày chụp dữ liệu, không phải tồn kho lịch sử.',),
            ('Current stock is hypothetical for a different planning date, not historical stock.',))
    add('simulation', 'limitations', ('/overview/assumptions','/overview/omissions'),
        ('Đây là kế hoạch mô phỏng, chưa phải mua hàng hay tiêu thụ thực tế.', 'Kết quả mô phỏng chưa tạo đơn mua và không phản ánh tiêu thụ thực tế.'),
        ('This is a simulated plan, not actual purchases or consumption.',))
    if request.detail_level == 'technical':
        add('schema', 'limitations', ('/overview/explanation',),
            (f'Nguồn kết quả: {evidence.identity.result_schema_version or "chưa có"}; evidence decision_evidence/1.',),
            (f'Result source: {evidence.identity.result_schema_version or "unavailable"}; evidence decision_evidence/1.',))
    return tuple(facts)


def deterministic_narrative(plan: tuple[CommunicationFact, ...]) -> SummaryNarrative:
    def section(family):
        return NarrativeSection(family=family, clauses=tuple(NarrativeClause(fact_id=f.fact_id,text=f.surfaces[0],evidence_ids=f.evidence_ids)
            for f in plan if f.family == family))
    return SummaryNarrative(schema_version='summary_narrative/2', headline=section('outcome'), summary=section('cost'),
        key_points=tuple(section(k) for k in ('requirements','coverage','proof')), warning_summary=section('limitations'))


def reconcile_narrative(plan: tuple[CommunicationFact, ...], narrative: SummaryNarrative) -> tuple[SummaryClaim, ...]:
    """Require complete selected obligations and exact semantic clause bindings.

    A fact_id is a hint: the entire clause must independently match that fact's
    admitted surfaces. Wrong entity, units, polarity, amount, scope, reference or
    extra causal assertions fail. No stripping or repairing invalid prose.
    """
    expected = {f.fact_id:f for f in plan}
    seen = set()
    claims = []
    sections = narrative.sections()
    if tuple(s.family for s in sections) != DEFAULT_EXPRESSION.ordering:
        raise ValueError('Narrative section scope differs')
    for section in sections:
        refs = []
        for clause in section.clauses:
            fact = expected.get(clause.fact_id)
            if fact is None or fact.fact_id in seen or fact.family != section.family:
                raise ValueError('Unknown, duplicate or misplaced claim')
            if clause.text not in fact.surfaces or clause.evidence_ids != fact.evidence_ids:
                raise ValueError('Unsupported clause or claim binding')
            seen.add(fact.fact_id)
            refs.extend(fact.evidence_ids)
        claims.append(SummaryClaim(family=section.family,text=' '.join(c.text for c in section.clauses), evidence_ids=tuple(dict.fromkeys(refs))))
    if seen != set(expected):
        raise ValueError('Missing material summary fact')
    return tuple(claims)


def render_narrative(evidence: DecisionEvidence, request: SummaryRequest, diagnostics: SummaryDiagnostics,
                     narrative: SummaryNarrative | None = None) -> SummaryAnswer:
    plan = communication_plan(evidence,request)
    claims = reconcile_narrative(plan, narrative or deterministic_narrative(plan))
    used = {r for c in claims for r in c.evidence_ids}
    return SummaryAnswer(identity=evidence.identity,option_id=evidence.option.option_id if evidence.option else None,
        locale=request.locale,detail_level=request.detail_level,
        source='model_presentation' if diagnostics.disposition == 'ACCEPTED' else 'deterministic_fallback',
        presentation=DEFAULT_EXPRESSION, answer='\n\n'.join(c.text for c in claims),claims=claims,
        references=tuple(r for r in evidence.references if r.evidence_id in used),
        diagnostics=diagnostics_v2(diagnostics),renderer_version=VERSIONS['renderer'])


def replay_narrative(evidence: DecisionEvidence, request: SummaryRequest, result: SummaryAnswer) -> SummaryAnswer:
    """Recover internal bindings from immutable public clauses without a provider."""
    if result.diagnostics.disposition == 'FALLBACK':
        return render_narrative(evidence,request,result.diagnostics)
    plan = communication_plan(evidence,request)
    sections = []
    for claim in result.claims:
        remaining = claim.text
        clauses = []
        while remaining:
            matches = [(f,s) for f in plan if f.family == claim.family for s in f.surfaces
                       if remaining == s or remaining.startswith(s+' ')]
            if len(matches) != 1: raise ValueError('Unreconciled retained narrative')
            fact, surface = matches[0]
            clauses.append(NarrativeClause(fact_id=fact.fact_id,text=surface,evidence_ids=fact.evidence_ids))
            remaining = remaining[len(surface):].removeprefix(' ')
        sections.append(NarrativeSection(family=claim.family,clauses=tuple(clauses)))
    if len(sections) != 6: raise ValueError('Missing retained section')
    narrative = SummaryNarrative(schema_version='summary_narrative/2',headline=sections[0],summary=sections[1],
        key_points=tuple(sections[2:5]),warning_summary=sections[5])
    return render_narrative(evidence,request,result.diagnostics,narrative)
