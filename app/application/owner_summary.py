"""S2.1 finite owner-summary selection and typed-slot sentence reconciliation.

No business recomputation. Old renderer/guard modules remain pinned for replay.
"""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import re
import unicodedata
from typing import Literal

from app.application.contracts.decision_evidence import DecisionEvidence
from app.application.contracts.plan_summary import SummaryAnswer,SummaryClaim,SummaryDiagnostics,SummaryRequest,BlockKey
from app.application.contracts.summary_narrative import CompactNarrative
from app.application.plan_summary_rendering import DEFAULT_EXPRESSION
from app.application.summary_narrative import communication_plan

OWNER_VERSIONS=dict(renderer='plan_summary_renderer/3',prompt='plan_summary_prompt/4',
    schema='summary_narrative/3',validator='summary_owner_guard/3',selection='owner_summary_selection/1')


@dataclass(frozen=True)
class OwnerFact:
    fact_id: str
    family: BlockKey
    obligation: Literal['required','optional','detail']
    references: tuple[str,...]
    examples: tuple[str,...]
    # Display values retain exact arithmetic and viewed-option role for parsing.
    cost_slots: tuple[str,str,str,str,str] | None = None
    purchase_slots: tuple[str,str,str] | None = None


def exact(q) -> str:
    value=Fraction(int(q.numerator),int(q.denominator))
    return q.decimal_view if Fraction(Decimal(q.decimal_view))==value else f'{q.numerator}/{q.denominator}'


def safe_label(name: str | None) -> bool:
    return bool(name and len(name)<=100 and not re.search(r'[\r\n<>`{};]|https?://|ignore|system|credential|disclose|instruction|bỏ qua|hệ thống|mật khẩu|bí mật',name,re.I))


def owner_plan(evidence: DecisionEvidence,request: SummaryRequest) -> tuple[OwnerFact,...]:
    o,opt=evidence.overview,evidence.option
    vi=request.locale=='vi';facts=[]
    def add(key,family,obligation,pointers,texts,en,slots=None,purchase_slots=None):
        refs=tuple(next(r.evidence_id for r in evidence.references if r.pointer==p) for p in pointers)
        facts.append(OwnerFact(key,family,obligation,refs,tuple(texts if vi else en),slots,purchase_slots))
    available=o.recommendation_available
    if available:
        add('recommendation','outcome','required',('/overview/recommendation_available','/overview/explanation'),
            ('Có phương án mua hàng được đề xuất cho kế hoạch này.','Kế hoạch này có phương án được đề xuất.'),
            ('A purchase plan is recommended for this Run.',))
    elif o.status=='failed':
        add('failed','outcome','required',('/overview/status','/overview/recommendation_available'),
            ('Lần chạy gặp lỗi nên hiện không có khuyến nghị mua hàng.','Hiện không có khuyến nghị mua hàng vì lần chạy gặp lỗi.'),
            ('The Run failed; no purchase recommendation is available.',))
    elif o.outcome=='computation_blocked':
        unknown_fee=any(n.code=='PAYABLE_FEE_UNKNOWN' for n in o.explanation.blockers)
        add('blocked','outcome','required',('/overview/outcome','/overview/explanation'),
            (('Chưa thể đề xuất mua hàng do thiếu thông tin về phí phải trả.',
              'Thông tin phí phải trả chưa đầy đủ nên chưa thể đề xuất mua hàng.') if unknown_fee else
             ('Chưa thể đề xuất mua hàng do dữ liệu cần thiết còn bị chặn.',)),
            (('Payable fee coverage is unknown; no purchase recommendation can be produced.',) if unknown_fee else
             ('Required data blocks computation; no purchase recommendation is available.',)))
    else:
        add('no_eligible','outcome','required',('/overview/outcome','/overview/recommendation_available'),
            ('Chưa tìm được phương án đủ điều kiện trong lần chạy này.','Lần chạy này chưa tìm được phương án đáp ứng điều kiện.'),
            ('No eligible option was found in this Run.',))
    # Diagnostic option amounts remain detail-only on failed/blocked/no-winner Runs.
    if available and opt:
        winner=o.explanation.winner.option_id
        viewed=opt.option_id!=winner
        role='phương án đang xem' if viewed else 'phương án được đề xuất'
        if viewed:
            add('viewed','outcome','required',('/option/option_id','/overview/explanation'),
                ('Phương án đang xem khác phương án được đề xuất; số liệu dưới đây thuộc phương án đang xem.',),
                ('The viewed option differs from the recommendation; the following facts concern the viewed option.',))
        c=opt.costs;total,purchase,fees=map(exact,(c.total,c.purchase,c.payable_fees))
        cost_examples=(f'Tổng chi dự kiến cho {role} là {total} {c.currency}, gồm {purchase} {c.currency} tiền mua và {fees} {c.currency} phí phải trả.',
             f'Chi phí của {role} gồm {purchase} {c.currency} tiền mua và {fees} {c.currency} phí phải trả; tổng cộng {total} {c.currency}.')
        if Fraction(fees)==0:cost_examples=(f'Tổng chi dự kiến cho {role} là {total} {c.currency}.',)+cost_examples
        add('costs','cost','required',('/option/option_id','/option/costs'),cost_examples,
            (f'The viewed option has total outlay {total} {c.currency}: purchase {purchase} {c.currency} and payable fees {fees} {c.currency}.',),
            (total,purchase,fees,c.currency,'viewed' if viewed else 'recommended'))
        if not opt.purchases:
            add('zero_purchase','cost','required',('/option/purchases',),
                ('Phương án này không đề xuất mua thêm nguyên liệu.','Không có đề xuất mua thêm nguyên liệu trong phương án này.'),
                ('This option proposes no additional ingredient purchases.',))
        else:
            names={i.ingredient_id:i for i in o.ingredients}
            chosen=[];signatures=set()
            for p in opt.purchases:
                signature=(p.ingredient_id,exact(p.quantity),p.unit)
                if len(chosen)<3 and signature not in signatures and p.ingredient_id in names and names[p.ingredient_id].name_availability=='captured' and safe_label(names[p.ingredient_id].name):
                    chosen.append(p);signatures.add(signature)
            for n,p in enumerate(chosen):
                name=names[p.ingredient_id].name;quantity=exact(p.quantity)
                add(f'buy_{n}','cost','required',('/option/purchases','/overview/ingredients'),
                    (f'Đề xuất mua {quantity} {p.unit} “{name}”.',f'Lượng mua đề xuất: “{name}” {quantity} {p.unit}.'),
                    (f'Proposed purchase: {name}, {quantity} {p.unit}.',),purchase_slots=(name,quantity,p.unit))
            if len(chosen)<len(opt.purchases):
                add('purchase_shortlist','cost','required',('/option/purchases','/overview/ingredients'),
                    ('Đây là phần mua được tóm tắt; xem danh sách đầy đủ trong chi tiết kế hoạch.',),
                    ('This purchase summary is abbreviated; see the complete list in the plan details.',))
        assessments=opt.requirements_assessment
        if assessments and not any(a.status=='FAIL' for a in assessments) and any(a.status=='PASS' for a in assessments):
            add('requirements','requirements','required',('/option/requirements_assessment',),
                ('Phương án đáp ứng các yêu cầu đã được đánh giá trong phạm vi này.',
                 'Các yêu cầu đã được đánh giá trong phạm vi này đều được đáp ứng.'),
                ('The option meets the requirements evaluated within this scope.',))
        elif any(a.status=='FAIL' for a in assessments):
            add('requirements','requirements','required',('/option/requirements_assessment',),
                ('Phương án đang xem còn yêu cầu đã đánh giá nhưng chưa đáp ứng.',),
                ('The viewed option has evaluated requirements that are not met.',))
        if c.fee_classification=='PAYABLE_FEE_TYPE_NOT_CAPTURED':
            add('fee_kind','limitations','optional',('/option/costs',),
                ('Phí phải trả chưa được phân loại là phí giao hàng.',),('Payable fees are not classified as delivery fees.',))
    scope=o.scope
    if scope:
        add('scope','coverage','required',('/overview/scope',),
            (f'Phạm vi kế hoạch gồm {scope.computed_count}/{scope.menu_count} món.',
             f'Kế hoạch xét {scope.computed_count} trong tổng số {scope.menu_count} món.'),
            (f'The planning scope includes {scope.computed_count}/{scope.menu_count} Products.',))
        excluded={p.product_id:p for p in scope.excluded_products}
        missing=set();grouped=[]
        for notice in o.explanation.blockers:
            d=notice.details
            exclusion=excluded.get(d.entity_id) if d and d.entity=='product' else None
            if notice.code=='RECIPE_MISSING' and exclusion and exclusion.code=='RECIPE_MISSING' and d.affected_dates and set(d.affected_dates)<=set(exclusion.affected_dates):
                missing.add(d.entity_id);grouped.append(notice)
        if missing:
            add('excluded_recipe','limitations','required',('/overview/explanation','/overview/scope'),
                (f'Có {len(missing)} món bị loại do thiếu công thức trong các ngày được ghi nhận; các món này chưa được đánh giá.',),
                (f'{len(missing)} Products were excluded for missing recipes on the recorded dates; they are not evaluated.',))
        other=set(excluded)-missing
        if other:
            add('excluded_other','limitations','required',('/overview/scope',),
                (f'Có {len(other)} món khác bị loại và chưa được đánh giá; xem lý do trong chi tiết kế hoạch.',),
                (f'{len(other)} other Products are excluded and unevaluated; review their retained reasons.',))
        remaining=[n for n in o.explanation.blockers if n not in grouped and n.code!='PAYABLE_FEE_UNKNOWN']
        if remaining and available:
            add('remaining_blockers','limitations','required',('/overview/explanation',),
                ('Kế hoạch còn dữ liệu bị chặn; cần xem đúng phạm vi của chúng trong phần chi tiết.',),
                ('Some retained data is blocked; review its exact scope in the details.',))
    if o.forecast:
        start,end=o.forecast.start_date.isoformat(),o.forecast.end_date.isoformat()
        add('horizon','coverage','optional',('/overview/forecast',),
            (f'Kỳ kế hoạch từ {start} đến {end}.',f'Khoảng thời gian của kế hoạch: {start} đến {end}.'),
            (f'The planning period is {start} to {end}.',))
    if available and any(s.proof=='UNPROVEN' or not s.search_complete for s in o.strategies):
        add('search_limit','proof','required',('/overview/strategies','/overview/selection_proof'),
            ('Đề xuất dựa trên các phương án đã đánh giá; vẫn có thể còn phương án khác chưa được tìm thấy.',
             'Đây là đề xuất từ các phương án đã đánh giá, chưa bảo đảm đã tìm hết các lựa chọn khác.'),
            ('The recommendation uses evaluated options; other options may remain undiscovered.',))
    if o.temporal_basis and o.temporal_basis.kind=='HYPOTHETICAL_CURRENT_CAPTURE':
        add('hypothetical','limitations','required',('/overview/temporal_basis',),
            ('Kế hoạch dùng tồn hiện tại cho một ngày khác theo giả định, không phải tồn kho lịch sử.',),
            ('Current stock is used hypothetically for a different date, not as historical inventory.',))
    # Supporting budget is never a mandatory coverage obligation.
    b=o.configuration.budget
    add('budget','cost','optional' if available else 'detail',('/overview/configuration',),
        (f'Ngân sách của kế hoạch là {b.limit} {b.currency}.',), (f'The plan budget is {b.limit} {b.currency}.',))
    # Keep full old fact families available as detail provenance, outside provider scope.
    for f in communication_plan(evidence,request):
        facts.append(OwnerFact('detail_'+f.fact_id,f.family,'detail',f.evidence_ids,f.surfaces))
    return tuple(facts)


NUMBER=r'(?:0|[1-9][0-9]*)(?:\.[0-9]+|/[1-9][0-9]*)?'


def validate_surface(fact: OwnerFact,text: str) -> bool:
    """Complete sentence grammars + exact typed slots, not keyword/ID matching."""
    normalized=unicodedata.normalize('NFC',text)
    if normalized in fact.examples:return True
    if fact.purchase_slots:
        name,quantity,unit=fact.purchase_slots
        match=re.fullmatch(rf'(?:Đề xuất mua|Dòng mua đề xuất:) (?P<quantity>{NUMBER}) {re.escape(unit)} (?:“{re.escape(name)}”|"{re.escape(name)}"|{re.escape(name)})\.?',normalized)
        return bool(match and Fraction(match['quantity'])==Fraction(quantity))
    if fact.cost_slots is None:return False
    total,purchase,fees,currency,role=fact.cost_slots
    subjects=r'phương án đang xem' if role=='viewed' else r'(?:phương án đang xem|phương án được đề xuất)'
    money=lambda name:rf'(?P<{name}>{NUMBER}) (?P<{name}_currency>[A-Z]{{3}})'
    if Fraction(fees)==0:
        match=re.fullmatch(rf'Tổng chi(?: dự kiến)? cho {subjects} là {money("total")}\.?',normalized)
        if match:return match['total_currency']==currency and Fraction(match['total'])==Fraction(total)
    patterns=(
        rf'Chi phí của {subjects} gồm {money("purchase")} tiền mua và {money("fees")} phí phải trả; tổng cộng {money("total")}\.?',
        rf'Tổng chi(?: dự kiến)? (?:cho|của) {subjects} là {money("total")}, gồm {money("purchase")} tiền mua và {money("fees")} phí phải trả\.?',
        rf'(?:Phương án đang xem|Phương án được đề xuất) (?:có|cần) tổng chi {money("total")}: tiền mua {money("purchase")}, phí phải trả {money("fees")}\.?'
        if role=='recommended' else rf'Phương án đang xem (?:có|cần) tổng chi {money("total")}: tiền mua {money("purchase")}, phí phải trả {money("fees")}\.?')
    for pattern in patterns:
        match=re.fullmatch(pattern,normalized)
        if match and all(match[k+'_currency']==currency for k in ('total','purchase','fees')):
            return all(Fraction(match[k])==Fraction(v) for k,v in (('total',total),('purchase',purchase),('fees',fees)))
    return False


def render_owner(evidence: DecisionEvidence,request: SummaryRequest,diagnostics: SummaryDiagnostics,
                 compact: CompactNarrative | None=None) -> SummaryAnswer:
    plan=owner_plan(evidence,request);allowed={f.fact_id:f for f in plan if f.obligation!='detail'}
    compact=compact or CompactNarrative(clauses=tuple(dict(fact_id=f.fact_id,text=f.examples[0]) for f in allowed.values() if f.obligation=='required'))
    seen=set();claims=[]
    for c in compact.clauses:
        f=allowed.get(c.fact_id)
        if f is None or c.fact_id in seen or not validate_surface(f,c.text):raise ValueError('Unsupported owner fact, sentence or duplicate binding')
        seen.add(c.fact_id);claims.append(SummaryClaim(family=f.family,text=c.text,evidence_ids=f.references))
    if not {f.fact_id for f in allowed.values() if f.obligation=='required'}<=seen:raise ValueError('Missing required owner-summary fact')
    # BE layout is deterministic, preserving original sentences without string repair.
    order={f.fact_id:n for n,f in enumerate(plan)}
    paired=sorted(zip(compact.clauses,claims),key=lambda pair:order[pair[0].fact_id])
    claims=tuple(c for _,c in paired)
    conclusion=' '.join(c.text for c in claims if c.family in ('outcome','cost'))
    paragraphs=[conclusion]+[' '.join(c.text for c in claims if c.family==family) for family in ('requirements','coverage','proof','limitations')]
    used={r for c in claims for r in c.evidence_ids}
    diag=diagnostics.model_copy(update={'prompt_version':OWNER_VERSIONS['prompt'],'validator_version':OWNER_VERSIONS['validator']})
    return SummaryAnswer(identity=evidence.identity,option_id=evidence.option.option_id if evidence.option else None,
        locale=request.locale,detail_level=request.detail_level,source='model_presentation' if diag.disposition=='ACCEPTED' else 'deterministic_fallback',
        presentation=DEFAULT_EXPRESSION,answer='\n\n'.join(p for p in paragraphs if p),claims=claims,
        references=tuple(r for r in evidence.references if r.evidence_id in used),diagnostics=diag,renderer_version=OWNER_VERSIONS['renderer'])


def replay_owner(evidence: DecisionEvidence,request: SummaryRequest,result: SummaryAnswer) -> SummaryAnswer:
    if result.diagnostics.disposition=='FALLBACK':return render_owner(evidence,request,result.diagnostics)
    plan=owner_plan(evidence,request);clauses=[]
    for claim in result.claims:
        matches=[f for f in plan if f.obligation!='detail' and f.family==claim.family and f.references==claim.evidence_ids and validate_surface(f,claim.text)]
        if len(matches)!=1:raise ValueError('Unreconciled retained owner claim')
        clauses.append(dict(fact_id=matches[0].fact_id,text=claim.text))
    return render_owner(evidence,request,result.diagnostics,CompactNarrative(clauses=clauses))
