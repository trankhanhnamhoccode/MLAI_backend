"""Small typed facts from verified retained projections, never from question/history."""
from app.application.contracts.chat_generation import FactCard,ChatEvidencePlan
from dataclasses import replace
from app.application.contracts.assistant_chat import ChatClaim,ChatDiagnostics,AssistantResponse
from app.application.assistant_chat_rendering import render_chat,ChatScope,normalized
from app.application.planning_serialization import digest


def select_chat_evidence(evidence,request,scope):
    fallback_scope=replace(scope,intent='cost') if scope.intent=='comparison' else scope
    fallback=render_chat(evidence,request,fallback_scope)
    if scope.intent=='what_if':
        text=('Chưa có kết quả mô phỏng với đầu vào thay đổi. Hãy tạo Run mới với ngân sách hoặc yêu cầu mới; cuộc chat này không chạy lại hay sửa dữ liệu.' if request.locale=='vi' else
              'No simulation exists for changed inputs. Create a new Run with the new budget or requirements; this chat does not rerun or change data.')
        clarification=fallback.clarification.model_copy(update={'question':text})
        fallback=fallback.model_copy(update={'answer':text,'clarification':clarification})
    cards=[]
    backend_only=scope.intent=='summary' or (scope.intent=='ingredient' and any(
        word in normalized(request.question) for word in ('ton kho','stock','thieu','shortage','so du','expiry','het han','khi nao','ngay nao')))
    def refs(*paths):return tuple(next(r.evidence_id for r in evidence.references if r.pointer==p) for p in paths)
    def add(kind,meaning,*paths,display=None,unit=None,entity=None,path=None,requested=None,lost_sales=None,service_percent=None):
        role=None
        if kind in ('total','purchase_cost','fees','purchase_quantity') and evidence.option:
            role='recommended' if evidence.overview.recommendation_available and evidence.overview.explanation.winner.option_id==evidence.option.option_id else 'viewed'
            paths+=('/overview/recommendation_available','/overview/explanation','/option/option_id')
        ids=refs(*paths)
        key='f-'+digest('chat-fact/1',[evidence.identity,kind,display,unit,entity,path,ids])[:20]
        cards.append(FactCard(fact_id=key,kind=kind,meaning=meaning,display=str(display) if display is not None else None,unit=unit,
            entity_id=entity,path=path,evidence_ids=ids,requested=requested,lost_sales=lost_sales,service_percent=service_percent,option_role=role))
    o=evidence.overview;option=evidence.option
    if not scope.clarification and not backend_only:
        if scope.intent in ('cost','summary'):
            if option:
                add('total','total outlay for viewed option','/option/costs',display=option.costs.total.decimal_view,unit=option.costs.currency)
                add('purchase_cost','purchase outlay for viewed option','/option/costs',display=option.costs.purchase.decimal_view,unit=option.costs.currency)
                add('fees','payable fees for viewed option','/option/costs',display=option.costs.payable_fees.decimal_view,unit=option.costs.currency)
            else:add('cost_unknown','option outlay unavailable, not zero','/overview/omissions')
            add('budget','retained budget limit','/overview/configuration',display=o.configuration.budget.limit,unit=o.configuration.budget.currency)
        if scope.intent in ('proof','outcome','summary'):
            kind=('winner' if o.recommendation_available else
                  ('failed' if o.explanation.winner.option_id else 'failed_unknown') if o.status=='failed' else
                  'no_winner' if o.outcome=='no_eligible_candidate' else 'blocked')
            meaning={'winner':'Run recommendation available',
                'failed':'Run failed; retained selector winner is diagnostic only',
                'failed_unknown':'Run failed; result/winner unavailable, never an infeasibility certificate',
                'blocked':'Computation blocked/incomplete; no recommendation, not a no-pass or infeasibility certificate',
                'no_winner':'No eligible option selected in this Run; not a global infeasibility certificate'}[kind]
            add(kind,meaning,
                '/overview/recommendation_available','/overview/outcome','/overview/explanation')
            if not o.recommendation_available:
                translations={'CUSTOMER_REQUIREMENTS_NOT_MET':'chưa đáp ứng yêu cầu khách hàng đã lưu',
                    'RELATED_BLOCKER':'có vấn đề chặn liên quan'}
                for row in o.explanation.options:
                    for code in row.rejection_reasons:
                        add('rejection','retained option eligibility reason; quote the supplied display, not a physical procurement cause',
                            '/overview/explanation',display=translations.get(code,code),entity=row.option_id)
            if o.recommendation_available and scope.intent in ('proof','summary'):
                add('selector','eligible evaluated candidates compared by outlay, then service and stable tie-break','/overview/selection_proof','/overview/explanation')
            if scope.intent in ('proof','summary'):
                add('proof_boundary' if o.selection_proof else 'proof_unknown',
                    'only evaluated candidates, no global optimality claim' if o.selection_proof else 'selector evidence unavailable, no ranking known',
                    '/overview/selection_proof')
                if any(s.proof=='UNPROVEN' or not s.search_complete for s in o.strategies):
                    add('unproven','search incomplete or unproven, no complete finite certificate','/overview/strategies')
        if scope.intent=='comparison':
            pair=next((p for p in o.comparisons or () if (p.from_option_id,p.to_option_id)==scope.comparison_pair),None)
            if pair:
                add('pair_cost','pairwise outlay change (to minus from), only this pair','/overview/comparisons',
                    display=pair.total_outlay_delta.decimal_view,unit=pair.currency,entity=pair.from_option_id+' -> '+pair.to_option_id)
                # Preserve zero as known: no total across Product units or paths.
                for p in pair.products:
                    add('pair_service','pairwise fulfilled quantity change (to minus from), not causality','/overview/comparisons',
                        display=p.fulfilled.decimal_view,unit=p.unit,entity=str(p.product_id),path=p.path)
            else:add('comparison_unknown','pairwise trade-off evidence unavailable','/overview/comparison_availability','/overview/comparisons')
        if scope.intent=='ingredient':
            row=evidence.ingredient
            if row is None:raise ValueError('Resolved Ingredient evidence missing')
            if row.purchases is None:add('purchase_unknown','purchase quantity unavailable, not zero','/ingredient/purchases')
            elif not row.purchases:add('purchase_zero','no proposed purchase lines for this Ingredient in viewed option','/ingredient/purchases')
            else:
                for p in row.purchases:
                    add('purchase_quantity','proposed purchase quantity per retained line, not an actual receipt','/ingredient/purchases',
                        display=p.quantity.decimal_view,unit=p.unit,entity=str(p.supplier_term_id) if len(row.purchases)>1 else None)
        if scope.intent=='requirements' and option:
            for p in option.product_services:
                add('service','simulated fulfilled/requested/lost sales and service percent by Product/path; null service is undefined, not zero','/option/product_services',
                    display=p.fulfilled.decimal_view,unit=p.unit,entity=str(p.product_id),path=p.path,
                    requested=p.requested.decimal_view,lost_sales=p.lost_sales.decimal_view,
                    service_percent=p.service.percent_view if p.service else None)
        if scope.intent=='coverage' and o.scope:
            add('coverage','computed Product count / retained Menu count','/overview/scope',
                display=str(o.scope.computed_count),unit=str(o.scope.menu_count))
        if scope.intent=='limitations':add('limitations','no causal/probability/actual or zero-purchase evidence','/overview/omissions')
    # Required guardrails remain server-owned; no salvage/removal of model errors.
    safety=tuple(c for c in fallback.claims if c.text and
                 any(r.pointer in ('/overview/omissions','/overview/strategies') for r in fallback.references if r.evidence_id in c.evidence_ids))
    if scope.intent=='ingredient' and evidence.ingredient:
        safety+=(ChatClaim(text=('Lượng mua trong câu trả lời thuộc phương án đang xem và chỉ là đề xuất; không phải đơn hàng hoặc hàng đã nhận.' if request.locale=='vi' else
            'Purchase quantities belong to the viewed option and are proposals, not orders or actual receipts.'),
            evidence_ids=refs('/ingredient/purchases','/ingredient/selected_option_id')),)
    # Expose existing blockers/rejections verbatim as retained evidence, not invented causality.
    if scope.intent=='outcome' and not o.recommendation_available:
        reasons=tuple(n.message for n in o.explanation.blockers)
        rejected=tuple(reason for row in o.explanation.options for reason in row.rejection_reasons)
        text=('Vấn đề chặn đã lưu: ' if request.locale=='vi' else 'Retained blockers: ')+('; '.join((*reasons,*rejected)) if reasons or rejected else
            ('chưa có lý do chi tiết được lưu; không suy ra nguyên nhân hoặc chứng nhận bất khả thi.' if request.locale=='vi' else 'detailed reasons unavailable; no cause or infeasibility certificate can be inferred.'))
        safety+=(ChatClaim(text=text,evidence_ids=refs('/overview/explanation')),)
    # A complete, topic-specific fallback for model failures, using the same cards.
    # Grammar owns canonical displays, not provider arithmetic.
    from app.application.chat_grounding import canonical_clause
    if cards:
        claims=tuple(ChatClaim(text=canonical_clause(c,request.locale)+'.',evidence_ids=c.evidence_ids) for c in cards)+safety
        used={i for c in claims for i in c.evidence_ids}
        fallback=AssistantResponse(**{**fallback.model_dump(),'kind':'answer','source':'deterministic_fallback',
            'answer':'\n\n'.join(c.text for c in claims),'claims':claims,
            'references':tuple(r for r in evidence.references if r.evidence_id in used),'clarification':None,
            'diagnostics':ChatDiagnostics(reason='MODEL_DISABLED')})
    return ChatEvidencePlan(identity=evidence.identity,intent=scope.intent,option_id=option.option_id if option else None,
        ingredient_id=scope.ingredient_id,facts=tuple(cards),required=tuple(c.fact_id for c in cards),safety_claims=safety,fallback=fallback)
