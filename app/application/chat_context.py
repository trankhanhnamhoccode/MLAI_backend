"""Bounded client context is an identity hint, never facts or authorization."""
from dataclasses import replace
import re
from app.application.assistant_chat_rendering import normalized, ChatScope, INTENTS
from app.application.contracts.assistant_chat import ChatContext, PendingQuestion
from app.application.contracts.planning_configuration import ConfigurationError


def resolve_context(request,evidence,version='chat_resolution/4'):
    if version=='chat_resolution/4':
        from app.application.chat_context_v4 import resolve_context as legacy
        return legacy(request,evidence)
    if version=='chat_resolution/3':
        from app.application.chat_context_v3 import resolve_context as legacy
        return legacy(request,evidence)
    o=evidence.overview; identity=evidence.identity; old=request.context
    ingredients=o.ingredients
    options={r.option_id for r in o.options}
    products={p.product_id for p in o.scope.menu_products} if o.scope else set()
    def matches(text):
        text=normalized(text)
        exact=tuple(r for r in ingredients if r.name and re.search(r'\b'+re.escape(normalized(r.name))+r'\b',text) or str(r.ingredient_id) in text)
        if exact:return exact
        # A token span of a retained label is a candidate, not a new alias.
        words=set(re.findall(r'\w+',text))
        return tuple(r for r in ingredients if r.name and words.intersection(normalized(r.name).split())-{'nguyen','lieu','loai'})
    valid_old=old is not None and (old.run_id,old.evidence_version)==(identity.run_id,identity.aggregate_digest)
    if old and not valid_old:
        return request,ChatScope('ingredient',None,'ENTITY_CONTEXT_MISMATCH',ingredients),None
    if old:
        if old.ingredient_id and not any(r.ingredient_id==old.ingredient_id for r in ingredients):
            raise ConfigurationError('INGREDIENT_NOT_IN_RUN',404)
        if old.product_id and old.product_id not in products:raise ConfigurationError('RESOURCE_NOT_FOUND',404)
        if old.option_id and old.option_id not in options:raise ConfigurationError('OPTION_NOT_FOUND',404)
        if old.comparison_pair and (len(set(old.comparison_pair))!=2 or not set(old.comparison_pair)<=options):
            raise ConfigurationError('OPTION_NOT_FOUND',404)
        if old.pending:
            allowed=products if old.pending.entity_kind=='product' else {r.ingredient_id for r in ingredients}
            if not set(old.pending.candidate_ids)<=allowed:raise ConfigurationError('RESOURCE_NOT_FOUND',404)
    if request.ingredient_id and not any(r.ingredient_id==request.ingredient_id for r in ingredients):
        raise ConfigurationError('INGREDIENT_NOT_IN_RUN',404)
    q=normalized(request.question); rows=matches(q)
    product_rows=tuple(p for p in o.scope.menu_products if re.search(r'\b'+re.escape(normalized(p.name))+r'\b',q) or str(p.product_id) in q) if o.scope else ()
    product=product_rows[0].product_id if len(product_rows)==1 else old.product_id if old else None
    if product_rows and any(w in q for w in ('mon ','product')) and 'nguyen lieu' not in q:rows=()
    if len(product_rows)>1:
        ctx=ChatContext(run_id=identity.run_id,evidence_version=identity.aggregate_digest,
            pending=PendingQuestion(original_question=request.question,candidate_ids=tuple(p.product_id for p in product_rows),entity_kind='product'))
        return request,ChatScope('product',None,'ENTITY_AMBIGUOUS',product_candidates=product_rows),ctx
    explicit=request.ingredient_id
    if explicit and rows and not any(r.ingredient_id==explicit for r in rows):
        return request,ChatScope('ingredient',explicit,'ENTITY_CONTEXT_MISMATCH',rows),None
    if explicit:rows=tuple(r for r in rows if r.ingredient_id==explicit) or tuple(r for r in ingredients if r.ingredient_id==explicit)
    if len(rows)>1:
        return request,ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',rows),ChatContext(run_id=identity.run_id,evidence_version=identity.aggregate_digest,
            option_id=request.option_id or (old.option_id if old else None),pending=PendingQuestion(original_question=request.question,candidate_ids=tuple(r.ingredient_id for r in rows)))
    ingredient=explicit or (rows[0].ingredient_id if rows else None)
    effective=request
    if old and old.pending and old.pending.entity_kind=='product' and product in old.pending.candidate_ids:
        effective=request.model_copy(update={'question':old.pending.original_question})
        q=normalized(effective.question)
    if old and old.pending and old.pending.entity_kind=='ingredient' and ingredient and ingredient in old.pending.candidate_ids:
        effective=request.model_copy(update={'question':old.pending.original_question,'ingredient_id':ingredient})
        q=normalized(effective.question)
    follow=any(re.search(r'\b'+re.escape(p)+r'\b',q) for p in ('no','cai do','loai nay','nguyen lieu do','luong do','it','that ingredient','that amount'))
    if ingredient is None and follow and product is None:
        antecedents=tuple(r for m in request.history[-2:] if m.role=='user' for r in matches(m.content))
        ids={r.ingredient_id for r in antecedents}
        if len(ids)>1:return effective,ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',tuple(r for r in ingredients if r.ingredient_id in ids)),None
        ingredient=old.ingredient_id if old and old.ingredient_id else next(iter(ids),None)
        if ingredient is None:return effective,ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',ingredients),None
    if ingredient and (rows or explicit) and not product_rows:product=None
    # Explicit new labels/IDs replace old entity. Merely supplied stale context
    # must not bind a fresh broad Ingredient question to an unrelated entity.
    if ingredient is None and old and old.ingredient_id and follow and not any(p in q for p in ('sua','ingredient','nguyen lieu')):
        ingredient=old.ingredient_id
    option=request.option_id or (old.option_id if old else None)
    mentioned=tuple(r for r in o.options if r.option_id in request.question or any(s in q.split() for s in r.source_strategies))
    if request.option_id and mentioned and any(r.option_id!=request.option_id for r in mentioned):
        return effective,ChatScope('option',ingredient,'ENTITY_CONTEXT_MISMATCH',option_candidates=mentioned),None
    pair=old.comparison_pair if old else None
    if request.option_id and pair and request.option_id not in pair:pair=None
    if len(mentioned)==1 and request.option_id is None:option=mentioned[0].option_id
    if len(mentioned)==2:pair=(mentioned[0].option_id,mentioned[1].option_id)
    if any(p in q for p in ('what if','what-if','tang ngan sach','giam ngan sach','doi yeu cau','dat hang','place order','cap quyen','ignore instructions','bo qua chi dan')):
        intent='what_if' if any(p in q for p in ('what','ngan sach','yeu cau')) else 'unsupported'
        scope=ChatScope(intent,ingredient,'QUERY_UNSUPPORTED')
    else:
        if any(p in q for p in ('dat hon','tradeoff','trade-off','duoc loi gi','so sanh','so voi')):intent='comparison'
        elif any(p in q for p in ('vi sao chon','tai sao chon','why selected')):intent='proof'
        elif any(p in q for p in ('rui ro','risk','du lieu con thieu','missing data')):intent='limitations'
        elif any(p in q for p in ('winner','vuong','khong chon duoc','run loi','run that bai','failed run')):intent='outcome'
        elif ingredient or any(p in q for p in ('can mua','mua bao nhieu','ton bao nhieu')) and 'ke hoach' not in q:intent='ingredient'
        elif any(p in q for p in ('ton bao nhieu','bao nhieu tien','het bao nhieu')):intent='cost'
        else:intent=next((k for k,words in INTENTS if any(w in q for w in words)),'unsupported')
        if intent=='ingredient' and not ingredient:scope=ChatScope(intent,None,'ENTITY_AMBIGUOUS',rows or ingredients)
        elif intent=='comparison':
            available=o.comparisons or ()
            if pair is None and len(available)==1:pair=(available[0].from_option_id,available[0].to_option_id)
            scope=ChatScope(intent,ingredient,'ENTITY_AMBIGUOUS' if pair is None and len(available)>1 else None,
                option_id=option,comparison_pair=pair,option_candidates=o.options)
        else:scope=ChatScope(intent,ingredient,'QUERY_UNSUPPORTED' if intent=='unsupported' else None,option_id=option)
    topic=None
    if scope.intent=='ingredient':
        topic=('purchase_rationale' if any(p in q for p in ('vi sao','tai sao','why','nguyen nhan','cause')) else
            'daily_shortage' if any(p in q for p in ('thieu','shortage')) else 'daily_ending' if any(p in q for p in ('cuoi ngay','so du','ending')) else
            'stock' if any(p in q for p in ('ton','stock')) else 'purchase' if any(p in q for p in ('mua','nhap','buy','purchase')) else old.topic if old else 'purchase')
        if not any(p in q for p in ('vi sao','tai sao','why','nguyen nhan','cause','mua','nhap','buy','purchase','ton','stock','thieu','shortage','cuoi ngay','so du','ending')) and topic:
            effective=effective.model_copy(update={'question':{'purchase':'Cần mua bao nhiêu?','purchase_rationale':'Vì sao cần mua lượng đó?',
                'stock':'Tồn đã chụp bao nhiêu?','daily_shortage':'Ngày nào thiếu?','daily_ending':'Số dư cuối ngày?'}[topic]})
    context=ChatContext(run_id=identity.run_id,evidence_version=identity.aggregate_digest,option_id=option,
        comparison_pair=pair,ingredient_id=ingredient,product_id=product,topic=topic)
    if scope.clarification=='ENTITY_AMBIGUOUS' and scope.intent=='ingredient':
        context=context.model_copy(update={'pending':PendingQuestion(original_question=effective.question,candidate_ids=tuple(r.ingredient_id for r in scope.candidates)[:30])})
    return effective,scope,context
