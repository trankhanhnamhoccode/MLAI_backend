"""Owner summary/2: retained warning qualifiers and distinct purchase-line scope.

Profile/5 remains in owner_summary unchanged for exact historical reconciliation.
This module selects presentation facts only; no IO, eligibility or computation.
"""
from app.application.contracts.decision_evidence import DecisionEvidence
from app.application.contracts.plan_summary import SummaryAnswer,SummaryClaim,SummaryDiagnostics,SummaryRequest
from app.application.contracts.summary_narrative import CompactNarrative
from app.application.owner_summary import OwnerFact,exact,safe_label,owner_plan as old_plan,validate_surface as old_validate
from app.application.plan_summary_rendering import DEFAULT_EXPRESSION

OWNER_VERSIONS=dict(renderer='plan_summary_renderer/4',prompt='plan_summary_prompt/5',
    schema='summary_narrative/3',validator='summary_owner_guard/4',selection='owner_summary_selection/2')

# Meanings are supported by retained producers; unknown codes use neutral wording.
WARNINGS={
    'BASELINE_FALLBACK':('baseline','Dự báo đã dùng phương pháp dự phòng; cần xem giới hạn dự báo trong chi tiết.',
        'The forecast used a fallback method; review its retained limitations.'),
    'FORECAST_TRAINING_OVERLAP':('overlap','Khoảng huấn luyện trùng kỳ dự báo; kết quả này chưa chứng minh độ chính xác trên dữ liệu mới.',
        'Training overlaps the forecast period; this does not establish accuracy on new data.'),
    'FORECAST_TRAINING_BOUNDS_UNKNOWN':('training_bounds','Chưa có đủ mốc huấn luyện để kiểm tra quan hệ với kỳ dự báo.',
        'Training bounds are unavailable for checking their relationship to the forecast period.'),
    'OFFER_OMITTED':('offers','Có chào giá bị loại; đề xuất chỉ xét các chào giá được giữ lại trong lần chạy này.',
        'Some offers were omitted; the recommendation considers only offers retained in this Run.'),
}
ROUTINE_ASSUMPTIONS=frozenset(('DAY_START_CAPTURE','COMPLETE_INVENTORY_SCOPE','NO_ADDITIONAL_ORDERS',
    'CURRENT_BALANCES_NOT_HISTORICAL_AS_OF','NO_INTERVENING_STOCK_EVOLUTION','ORIGINAL_RECEIPT_EXPIRY_DATES'))


def owner_plan(evidence: DecisionEvidence,request: SummaryRequest) -> tuple[OwnerFact,...]:
    o,opt=evidence.overview,evidence.option;vi=request.locale=='vi'
    facts=[f for f in old_plan(evidence,request) if not f.fact_id.startswith('buy_') and f.fact_id!='purchase_shortlist']
    def fact(key,family,pointers,vi_text,en_text):
        refs=tuple(next(r.evidence_id for r in evidence.references if r.pointer==p) for p in pointers)
        return OwnerFact(key,family,'required',refs,(vi_text if vi else en_text,))
    if o.recommendation_available and opt and opt.purchases:
        names={i.ingredient_id:i for i in o.ingredients}
        selected=[(index,p,names[p.ingredient_id].name) for index,p in enumerate(opt.purchases)
            if p.ingredient_id in names and names[p.ingredient_id].name_availability=='captured' and safe_label(names[p.ingredient_id].name)][:3]
        abbreviated=len(selected)<len(opt.purchases)
        additions=[fact('purchase_line_scope','cost',('/option/purchases','/overview/ingredients'),
            ('Một số dòng mua được đề xuất dưới đây là danh sách rút gọn, không phải tổng lượng theo nguyên liệu; xem toàn bộ dòng mua trong chi tiết kế hoạch.' if abbreviated else
             'Các lượng mua đề xuất dưới đây thuộc từng dòng mua, không phải tổng lượng theo nguyên liệu.'),
            ('The following proposed purchase lines are abbreviated, not ingredient totals; see all lines in plan details.' if abbreviated else
             'The following proposed quantities belong to individual purchase lines, not ingredient totals.'))]
        for index,p,name in selected:
            # Collection-level pointers are the existing supported evidence granularity.
            # Original ordinal + exact arrival date identify the retained member;
            # never merge supplier/term/date-distinct or equal-valued purchases.
            additions.append(fact(f'buy_{index}','cost',('/option/purchases','/overview/ingredients'),
                f'Dòng mua số {index+1}: đề xuất {exact(p.quantity)} {p.unit} “{name}”, dự kiến nhận ngày {p.arrival_date.isoformat()}.',
                f'Purchase line {index+1}: proposed {exact(p.quantity)} {p.unit} of “{name}”, expected arrival {p.arrival_date.isoformat()}.'))
        position=next(n for n,f in enumerate(facts) if f.fact_id=='costs')+1
        facts[position:position]=additions

    # C08 already collects capture problems, forecast/result and engine option/BOM
    # warnings. Inspect forecast and selected-option notices too; never copy their
    # untrusted message strings or infer that a notice makes the winner ineligible.
    sources=[('/overview/explanation',o.explanation.warnings)]
    if o.forecast:sources.append(('/overview/forecast',o.forecast.warnings))
    if opt:sources.append(('/option/issues',opt.issues))
    groups={};unknown=[]
    for pointer,notices in sources:
        for notice in notices:
            key=WARNINGS.get(notice.code)
            if key:
                entry=groups.setdefault(key[0],(key,[]))
                if pointer not in entry[1]:entry[1].append(pointer)
            elif pointer not in unknown:unknown.append(pointer)
    for key,(_,pointers) in groups.items():
        values=next(v for v in WARNINGS.values() if v[0]==key)
        facts.append(fact('warning_'+key,'limitations',pointers,values[1],values[2]))
    if unknown:
        facts.append(fact('warning_unknown','limitations',unknown,
            'Kế hoạch có thông tin lưu ý đã ghi nhận; cần xem chi tiết trước khi quyết định mua hàng.',
            'The plan retains additional notices; review their details before deciding purchases.'))
    if any(a not in ROUTINE_ASSUMPTIONS and not a.startswith('NO_ADDITIONAL_ORDERS_ATTESTATION:') for a in o.assumptions):
        facts.append(fact('assumptions','limitations',('/overview/assumptions',),
            'Kế hoạch còn dựa trên các giả định đã lưu; cần xem các giả định trong chi tiết.',
            'The plan also relies on retained assumptions; review them in the details.'))
    return tuple(facts)


def validate_surface(fact: OwnerFact,text: str) -> bool:
    # New line sentences bind ordinal/date/name/unit/quantity as one whole fact.
    if fact.fact_id.startswith('buy_'):return text in fact.examples
    return old_validate(fact,text)


def render_owner(evidence: DecisionEvidence,request: SummaryRequest,diagnostics: SummaryDiagnostics,
                 compact: CompactNarrative | None=None) -> SummaryAnswer:
    plan=owner_plan(evidence,request);allowed={f.fact_id:f for f in plan if f.obligation!='detail'}
    compact=compact or CompactNarrative(clauses=tuple(dict(fact_id=f.fact_id,text=f.examples[0]) for f in allowed.values() if f.obligation=='required'))
    seen=set();paired=[]
    for clause in compact.clauses:
        f=allowed.get(clause.fact_id)
        if f is None or clause.fact_id in seen or not validate_surface(f,clause.text):raise ValueError('Unsupported owner fact, sentence or duplicate binding')
        seen.add(clause.fact_id);paired.append((clause.fact_id,SummaryClaim(family=f.family,text=clause.text,evidence_ids=f.references)))
    if not {f.fact_id for f in allowed.values() if f.obligation=='required'}<=seen:raise ValueError('Missing required owner-summary fact')
    order={f.fact_id:n for n,f in enumerate(plan)}
    claims=tuple(claim for _,claim in sorted(paired,key=lambda p:order[p[0]]))
    paragraphs=[' '.join(c.text for c in claims if c.family in ('outcome','cost'))]
    paragraphs+=[' '.join(c.text for c in claims if c.family==family) for family in ('requirements','coverage','proof','limitations')]
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
