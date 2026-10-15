"""Question context from retained identities; history supplies references, not facts."""
from app.application.assistant_chat_rendering import scope_question, normalized, ChatScope
from dataclasses import replace


def resolve_question(request,evidence):
    q=normalized(request.question)
    if request.ingredient_id is not None:
        from app.application.contracts.planning_configuration import ConfigurationError
        if evidence.overview.scope is None:raise ConfigurationError('COMPUTED_SCOPE_NOT_AVAILABLE',409)
        if not any(i.ingredient_id==request.ingredient_id for i in evidence.overview.ingredients):
            raise ConfigurationError('INGREDIENT_NOT_IN_RUN',404)
    if any(p in q for p in ('what if','what-if','tang ngan sach','giam ngan sach','doi yeu cau')) or \
       (any(p in q for p in ('neu ','gia su')) and any(p in q for p in ('tang ','giam ','thay doi','doi dau vao'))):
        return ChatScope('what_if',request.ingredient_id,'QUERY_UNSUPPORTED')
    # User history alone may identify a referenced entity/explicit option.
    follow=any(p in q for p in ('con no','vua noi','nguyen lieu do','phuong an do','what about it','bao nhieu nua'))
    context=request
    history_option=None
    if follow and request.ingredient_id is None:
        for message in reversed(request.history):
            if message.role!='user':continue
            text=normalized(message.content)
            rows=[i for i in evidence.overview.ingredients if str(i.ingredient_id) in text or (i.name and normalized(i.name) in text)]
            if len(rows)==1:context=request.model_copy(update={'ingredient_id':rows[0].ingredient_id})
            elif len(rows)>1:return ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',tuple(rows))
            break
    if follow and request.option_id is None:
        for message in reversed(request.history):
            if message.role!='user':continue
            rows=[o for o in evidence.overview.options if o.option_id in message.content]
            if len(rows)==1:history_option=rows[0].option_id
            elif len(rows)>1:return ChatScope('option',context.ingredient_id,'ENTITY_AMBIGUOUS',option_candidates=tuple(rows))
            break
    # Recognize common natural questions before the frozen legacy resolver.
    if any(p in q for p in ('dat hon','duoc loi gi','trade-off','tradeoff','phuong an khac','so voi','so sanh')):
        intent='comparison'
    elif any(p in q for p in ('vi sao chon','tai sao chon','why selected','ly do chon','sao lai chon')):
        intent='proof'
    elif any(p in q for p in ('ton bao nhieu','het bao nhieu tien','chi het','bao nhieu tien')):
        intent='cost'
    elif 'winner' in q or any(p in q for p in ('vuong dieu kien','chua du dieu kien','khong chon duoc')):
        intent='outcome'
    else:intent=None
    if follow and history_option and intent is None:
        previous=next((normalized(m.content) for m in reversed(request.history) if m.role=='user'),'')
        intent='cost' if any(p in previous for p in ('chi phi','ton bao nhieu','ngan sach','cost','budget')) else 'summary'
    scoped=scope_question(context,evidence)
    if scoped.clarification and scoped.clarification!='QUERY_UNSUPPORTED' and not (intent=='comparison' and scoped.intent=='option'):return scoped
    if any(p in q for p in ('dat hang','place order','cap quyen','sua du lieu','bo qua chi dan','ignore instructions')):
        return ChatScope('unsupported',scoped.ingredient_id,'QUERY_UNSUPPORTED')
    if scoped.ingredient_id and any(p in q for p in ('mua','bao nhieu','con no','purchase')):
        intent='ingredient'
    if intent=='comparison':
        pairs=evidence.overview.comparisons or ()
        mentioned={o.option_id for o in evidence.overview.options if o.option_id in request.question}
        narrowed=tuple(p for p in pairs if mentioned<={p.from_option_id,p.to_option_id}) if mentioned else pairs
        if mentioned and not narrowed and pairs:
            return ChatScope('option',scoped.ingredient_id,'ENTITY_CONTEXT_MISMATCH',option_candidates=evidence.overview.options)
        if len(narrowed)>1:return ChatScope('option',scoped.ingredient_id,'ENTITY_AMBIGUOUS',option_candidates=evidence.overview.options)
        pair=(narrowed[0].from_option_id,narrowed[0].to_option_id) if len(narrowed)==1 else None
        return ChatScope(intent,scoped.ingredient_id,option_id=history_option,comparison_pair=pair)
    if intent:return ChatScope(intent,scoped.ingredient_id,option_id=history_option)
    if any(p in q for p in ('can mua','mua bao nhieu','purchase quantity')) and scoped.ingredient_id is None:
        return ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',tuple(evidence.overview.ingredients))
    return replace(scoped,option_id=history_option)
