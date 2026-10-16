"""Question obligations versus optional supporting facts on a verified projection."""
from dataclasses import replace
from decimal import Decimal
from uuid import UUID
import re
from app.application.chat_evidence_selection import select_chat_evidence
from app.application.chat_grounding import canonical_clause
from app.application.assistant_chat_rendering import normalized
from app.application.contracts.chat_generation import FactCard
from app.application.contracts.assistant_chat import ChatClaim,ChatDiagnostics,ProductCandidate
from app.application.planning_serialization import digest


def display_fact(card,locale='vi'):
    if card.presentation is not None:return card.presentation
    vi=locale=='vi';label=card.label or ('nguyên liệu đang xem' if vi else 'the viewed Ingredient')
    if card.kind=='stock_lot':return (f'Tồn đã chụp của {label}, lô {card.entity_id}: {card.display} {card.unit}' if vi else f'Captured stock for {label}, lot {card.entity_id}: {card.display} {card.unit}')
    if card.kind in ('daily_shortage','daily_ending'):
        word=('thiếu' if card.kind=='daily_shortage' else 'cuối ngày') if vi else ('shortage' if card.kind=='daily_shortage' else 'ending')
        return f'{"Mô phỏng" if vi else "Simulated"} {label}, {card.path}: {word} {card.display} {card.unit}'
    if card.kind in ('detail_unknown','mechanistic'):return card.meaning.rstrip('.')
    if card.kind in ('eligibility','requirement','viewed_role'):return card.meaning.rstrip('.')
    if card.kind=='blocker':return ('Vấn đề chặn đã lưu: ' if vi else 'Retained blocker: ')+card.display
    if card.kind=='gap':return (f'Phương án {card.entity_id}, món {card.label}, {card.path}: còn thiếu {card.display} {card.unit} để đáp ứng yêu cầu đã lưu' if vi else f'Option {card.entity_id}, Product {card.label}, {card.path}: retained requirement shortfall {card.display} {card.unit}')
    if card.kind=='pair_cost' and card.label:return (f'Chênh lệch tổng chi ({card.label}): {card.display} {card.unit}' if vi else f'Total outlay delta ({card.label}): {card.display} {card.unit}')
    if card.kind=='pair_service' and card.label:return (f'Mô phỏng, chênh lệch lượng phục vụ món {card.label}, đường {card.path}: {card.display} {card.unit}' if vi else f'Simulated fulfilled quantity delta for Product {card.label}, path {card.path}: {card.display} {card.unit}')
    return canonical_clause(card,locale)


def select_evidence(evidence,request,scope,context,version='chat_evidence/3'):
    if version=='chat_evidence/7':
        from app.application.chat_readability_v7 import select_readable
        return select_readable(evidence,request,scope,context)
    if version=='chat_evidence/8':
        from app.application.chat_readability import select_readable
        return select_readable(evidence,request,scope,context)
    plan=select_chat_evidence(evidence,request,scope)
    q=normalized(request.question);o=evidence.overview;cards=list(plan.facts);required=[]
    def add(kind,meaning,pointer,*,value=None,unit=None,entity=None,path=None,label=None):
        refs=tuple(r.evidence_id for r in evidence.references if r.pointer==pointer)
        card=FactCard(fact_id='f-'+digest('chat-fact/2',[evidence.identity,kind,value,unit,entity,path,label,refs])[:20],kind=kind,meaning=meaning,
            display=value,unit=unit,entity_id=entity,path=path,label=label,evidence_ids=refs)
        cards.append(card);return card
    if not scope.clarification:
        if scope.intent=='cost':
            kinds={'total','cost_unknown'}
            if any(w in q for w in ('ngan sach','budget')):kinds.add('budget')
            if any(w in q for w in ('phi','fees','chi tiet','breakdown')):kinds.update(('fees','purchase_cost'))
            required=[c.fact_id for c in cards if c.kind in kinds]
        elif scope.intent=='ingredient':
            row=evidence.ingredient;label=row.display_name
            if version in ('chat_evidence/3','chat_evidence/4','chat_evidence/5','chat_evidence/6') and any(w in q for w in ('xac suat','probability','loi nhuan','profit')):
                cards=[]
                add('detail_unknown','Evidence của Run không có xác suất hay lợi nhuận để trả lời câu hỏi này.' if request.locale=='vi' else
                    'Run evidence does not contain probability or profit metrics for this question.','/overview/omissions')
            elif version in ('chat_evidence/3','chat_evidence/4','chat_evidence/5','chat_evidence/6') and any(w in q for w in ('vi sao','tai sao','why','nguyen nhan','cause','khong mua','zero-purchase')):
                if version in ('chat_evidence/4','chat_evidence/5','chat_evidence/6') and row.daily_balances:
                    # One retained row is a scoped mechanistic factor, not a
                    # derivation of optimal quantity or an invented causal chain.
                    paths=set(re.findall(r'\b(?:LOW|BASE|HIGH)\b',q.upper()))
                    dates=set(re.findall(r'\b\d{4}-\d{2}-\d{2}\b',q))
                    daily=[d for d in row.daily_balances if (not paths or d.path in paths) and (not dates or str(d.day) in dates)]
                    if daily:
                        d=daily[0]
                        meaning=(f'Mô phỏng {label}, {d.path} / {d.day}: yêu cầu {d.requested.decimal_view} {d.unit}; '
                            f'có sẵn {d.available.decimal_view} {d.unit}; thiếu {d.shortage.decimal_view} {d.unit}' if request.locale=='vi' else
                            f'Simulated {label}, {d.path} / {d.day}: requested {d.requested.decimal_view} {d.unit}; '
                            f'available {d.available.decimal_view} {d.unit}; shortage {d.shortage.decimal_view} {d.unit}')
                        add('mechanistic',meaning,'/ingredient/daily_balances',entity=str(row.ingredient_id),path=f'{d.path} / {d.day}',label=label)
                    else:add('detail_unknown','Chưa lưu dòng mô phỏng cho ngày hoặc đường được hỏi.' if request.locale=='vi' else
                        'No retained simulation row matches the requested date/path.','/ingredient/daily_balances')
                if version in ('chat_evidence/5','chat_evidence/6') and not row.purchases:
                    missing_reason=('Chưa lưu bằng chứng nhân quả hoặc so sánh không mua để giải thích lý do mua; không suy ra có một lượng mua đề xuất.' if request.locale=='vi' else
                        'Causal or zero-purchase evidence was not retained; no proposed purchase quantity is inferred.')
                else:missing_reason=('Evidence đang dùng chưa có bằng chứng nhân quả hoặc so sánh không mua để giải thích lý do mua; lượng mua chỉ là đề xuất đã lưu.' if request.locale=='vi' else
                    'This evidence has no causal or zero-purchase comparison explaining the purchase; quantities are retained proposals.')
                add('detail_unknown',missing_reason,'/overview/omissions')
            elif any(w in q for w in ('ton','stock','so du','thieu','shortage','ngay nao','khi nao','ending')):
                cards=[]
                if any(w in q for w in ('ngay','thieu','shortage','ending','so du')):
                    daily=row.daily_balances
                    if daily is None:add('detail_unknown','Chưa lưu dữ liệu mô phỏng theo ngày; không suy ra bằng không.' if request.locale=='vi' else 'Daily simulation evidence was not retained; this does not mean zero.','/ingredient/daily_balances')
                    else:
                        selected=[d for d in daily if (not any(p in q.upper() for p in ('LOW','BASE','HIGH')) or d.path in q.upper()) and
                            (not any(str(x.day) in q for x in daily) or str(d.day) in q)]
                        for d in selected:
                            kind='daily_shortage' if any(w in q for w in ('thieu','shortage')) else 'daily_ending'
                            v=d.shortage if kind=='daily_shortage' else d.ending
                            add(kind,'retained daily simulation, not actual inventory','/ingredient/daily_balances',value=v.decimal_view,unit=d.unit,
                                entity=str(row.ingredient_id),path=f'{d.path} / {d.day}',label=label)
                else:
                    for lot in row.captured_stock.lots:
                        add('stock_lot','quantity per captured lot, not current live stock','/ingredient/captured_stock',value=lot.quantity.decimal_view,unit=lot.unit,
                            entity=str(lot.lot_id),label=label)
                    if not cards:add('detail_unknown','Ảnh chụp đã lưu không có dòng lô; không suy ra tồn hiện tại.' if request.locale=='vi' else 'The retained capture has no lot rows; current inventory is not inferred.','/ingredient/captured_stock')
            else:cards=[c.model_copy(update={'label':label}) for c in cards]
            required=[c.fact_id for c in cards]
        elif scope.intent=='outcome':
            for n in o.explanation.blockers:add('blocker','quoted retained blocker, not an inferred cause','/overview/explanation',value=n.message)
            for option in o.explanation.options:
                seen=set()
                for row in option.evidence:
                    for gap in row.customer_gaps:
                        key=(gap.product_id,gap.path,gap.shortfall.decimal_view)
                        if gap.shortfall.numerator!='0' and key not in seen:
                            seen.add(key)
                            add('gap','retained customer requirement shortfall, no causal inference','/overview/explanation',value=gap.shortfall.decimal_view,
                                unit=gap.unit,entity=option.option_id,path=gap.path,
                                label=next((p.name for p in o.scope.menu_products if p.product_id==gap.product_id),str(gap.product_id)) if o.scope else str(gap.product_id))
            if not o.recommendation_available and not any(c.kind in ('gap','blocker') for c in cards):
                add('detail_unknown','Chưa lưu gap hoặc vấn đề chặn chi tiết; không suy ra nguyên nhân hay bất khả thi.' if request.locale=='vi' else 'Detailed gaps/blockers were not retained; no cause or infeasibility is inferred.','/overview/explanation')
            required=[c.fact_id for c in cards]
        elif (scope.intent=='proof' and version=='chat_evidence/3') or (scope.intent in ('proof','requirements') and version in ('chat_evidence/4','chat_evidence/5','chat_evidence/6')):
            if scope.intent=='requirements':cards=[] # assessments answer requirements; service tables are separate detail
            if evidence.option:
                option=evidence.option
                role='Phương án đang xem đủ điều kiện theo đánh giá đã lưu.' if option.eligible else 'Phương án đang xem không đủ điều kiện theo đánh giá đã lưu.'
                if request.locale=='en':role='The viewed option is eligible in the retained assessment.' if option.eligible else 'The viewed option is not eligible in the retained assessment.'
                add('eligibility',role,'/option/eligible',entity=option.option_id)
                if option.option_id!=o.explanation.winner.option_id:
                    add('viewed_role','Phương án đang xem không phải winner đã lưu của Run.' if request.locale=='vi' else 'The viewed option is not the retained Run winner.',
                        '/overview/explanation',entity=option.option_id)
                names={p.product_id:p.name for p in o.scope.menu_products} if o.scope else {}
                units={p.product_id:p.selling_unit for p in o.scope.menu_products} if o.scope else {}
                for a in option.requirements_assessment:
                    shortfall=a.shortfall.decimal_view if a.shortfall else None
                    label=names.get(a.product_id,str(a.product_id))
                    meaning=(f'Yêu cầu đã lưu cho món {label}, đường {a.path}: tối thiểu {a.target_percent}%, trạng thái {a.status}' if request.locale=='vi' else
                        f'Retained requirement for Product {label}, path {a.path}: minimum {a.target_percent}%, status {a.status}')
                    if shortfall is not None:meaning+=('; thiếu '+shortfall if request.locale=='vi' else '; shortfall '+shortfall)+' '+units[a.product_id]
                    add('requirement',meaning,'/option/requirements_assessment',entity=str(a.product_id),path=a.path,label=label)
            required=[c.fact_id for c in cards]
        elif scope.intent=='comparison':
            pair=next((p for p in o.comparisons or () if (p.from_option_id,p.to_option_id)==scope.comparison_pair),None)
            names={p.product_id:p.name for p in o.scope.menu_products} if o.scope else {}
            if pair:
                options={r.option_id:', '.join(r.source_strategies) for r in o.options}
                direction=f'{options[pair.to_option_id]} trừ {options[pair.from_option_id]}' if request.locale=='vi' else f'{options[pair.to_option_id]} minus {options[pair.from_option_id]}'
                cards=[c.model_copy(update={'label':direction if c.kind=='pair_cost' else names.get(UUID(c.entity_id)) if c.kind=='pair_service' else c.label,
                    'display':format(Decimal(c.display),'f') if c.display is not None else None}) for c in cards]
            required=[c.fact_id for c in cards]
        else:required=[c.fact_id for c in cards]
        if context and context.product_id and scope.intent in ('requirements','comparison'):
            cards=[c for c in cards if c.kind not in ('service','pair_service') or c.entity_id==str(context.product_id)]
            required=[k for k in required if k in {c.fact_id for c in cards}]
    # Only contextual guardrails. No generic summary disclaimer on every answer.
    safety=()
    pair_card=next((c for c in cards if c.kind=='pair_cost' and c.label),None)
    if pair_card and version in ('chat_evidence/3','chat_evidence/4','chat_evidence/5','chat_evidence/6'):
        safety=(ChatClaim(text=(f'Chênh lệch theo chiều {pair_card.label}; lượng phục vụ là mô phỏng.' if request.locale=='vi' else
            f'Deltas are {pair_card.label}; fulfilled quantities are simulated.'),evidence_ids=pair_card.evidence_ids),)
    if scope.intent=='proof':safety=() # proof boundary is already a main obligation
    if scope.intent not in ('outcome','proof') and o.explanation.blockers:
        safety=tuple(ChatClaim(text=('Vấn đề chặn đã lưu: ' if request.locale=='vi' else 'Retained blocker: ')+n.message,
            evidence_ids=tuple(r.evidence_id for r in evidence.references if r.pointer=='/overview/explanation')) for n in o.explanation.blockers)
    fallback=plan.fallback
    if cards and not scope.clarification:
        claims=tuple(ChatClaim(text=display_fact(c,request.locale)+'.',evidence_ids=c.evidence_ids) for c in cards if c.fact_id in required)+safety
        ids={i for c in (*claims,*cards) for i in c.evidence_ids}
        fallback=fallback.model_copy(update={'answer':'\n\n'.join(c.text for c in claims),'claims':claims,
            'references':tuple(r for r in evidence.references if r.evidence_id in ids),'diagnostics':ChatDiagnostics(reason='MODEL_DISABLED',validator_version='decision_chat_renderer/7' if version=='chat_evidence/6' else 'decision_chat_renderer/6' if version=='chat_evidence/5' else 'decision_chat_renderer/5' if version=='chat_evidence/4' else 'decision_chat_renderer/4' if version=='chat_evidence/3' else 'decision_chat_renderer/3')})
    if fallback.clarification and scope.candidates:
        text=('Bạn muốn hỏi nguyên liệu nào? Chọn một tên bên dưới.' if request.locale=='vi' else 'Which Ingredient do you mean? Choose a name below.')
        if not any(r.name for r in scope.candidates):text=('Run chưa lưu tên nguyên liệu; chỉ có các ID đã lưu.' if request.locale=='vi' else 'Ingredient labels were not captured; only retained IDs are available.')
        fallback=fallback.model_copy(update={'answer':text,'clarification':fallback.clarification.model_copy(update={'question':text})})
    if fallback.clarification and scope.product_candidates:
        text='Bạn muốn hỏi món nào? Chọn tên bên dưới.' if request.locale=='vi' else 'Which Product do you mean? Choose a name below.'
        fallback=fallback.model_copy(update={'answer':text,'clarification':fallback.clarification.model_copy(update={'question':text,
            'product_candidates':tuple(ProductCandidate(product_id=p.product_id,name=p.name) for p in scope.product_candidates)})})
    fallback=fallback.model_copy(update={'context':context})
    return plan.model_copy(update={'version':version,'resolver_version':'chat_resolution/4' if version in ('chat_evidence/4','chat_evidence/5','chat_evidence/6') else 'chat_resolution/3','facts':tuple(cards),
        'required':tuple(required),'safety_claims':safety,'fallback':fallback,
        'resolved_question':request.question if version in ('chat_evidence/4','chat_evidence/5','chat_evidence/6') else None})
