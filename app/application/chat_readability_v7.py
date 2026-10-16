"""L4 deterministic presentation over retained facts; never recomputes business metrics."""
from collections import Counter,defaultdict
from app.application.assistant_chat_rendering import normalized
from app.application.contracts.chat_generation import FactCard,FactGroup,GroupMember
from app.application.contracts.assistant_chat import ChatClaim,ChatDiagnostics
from app.application.planning_serialization import digest


def scoped_labels(rows,prefix):
    """Stable captured names or local ordinal labels, never a live lookup."""
    rows=sorted(rows,key=lambda row:str(row[0]));counts=Counter(normalized(name or '') for _,name in rows)
    result={}
    for n,(identity,name) in enumerate(rows,1):
        text=normalized(name or '')
        safe=bool(name and len(name)<=60 and all(c.isalnum() or c in ' -_()' for c in name))
        safe=safe and not any(word in text for word in ('ignore','bo qua','system','secret','instruction','toi uu','an toan nhat'))
        result[str(identity)]=name if safe and counts[text]==1 else f'{prefix} {n}'
    return result


def group_card(kind,members,text,*,display=None,unit=None,entity=None,path=None,assessments=None):
    fields=('fact_id','kind','entity_id','path','display','unit','meaning','evidence_ids')
    rows=[]
    for m in members:
        data={k:getattr(m,k) for k in fields}
        if assessments:
            a,u=assessments[(m.entity_id,m.path)]
            data.update(target_percent=a.target_percent,status=a.status,shortfall=a.shortfall.decimal_view,unit=u)
        rows.append(GroupMember(**data))
    group=FactGroup(kind=kind,members=tuple(rows))
    refs=tuple(dict.fromkeys(i for m in members for i in m.evidence_ids))
    return FactCard(fact_id='f-'+digest('chat-group/1',[group,text])[:20],kind='grouped_'+kind,meaning=text,presentation=text,
        display=display,unit=unit,entity_id=entity,path=path,evidence_ids=refs,group=group)


def select_readable(evidence,request,scope,context):
    from app.application.conversational_evidence import select_evidence,display_fact
    baseline=select_evidence(evidence,request,scope,context,'chat_evidence/6')
    vi=request.locale=='vi';o=evidence.overview
    products=scoped_labels([(p.product_id,p.name) for p in o.scope.menu_products], 'Món' if vi else 'Product') if o.scope else {}
    ingredients=scoped_labels([(p.ingredient_id,p.name) for p in o.ingredients], 'Nguyên liệu' if vi else 'Ingredient')
    strategies={'lean':'tiết kiệm','balanced':'cân bằng','protected':'bảo vệ'} if vi else {'lean':'lean','balanced':'balanced','protected':'protected'}
    options={r.option_id:('Phương án ' if vi else 'Option ')+', '.join(strategies[s] for s in r.source_strategies) for r in o.options}
    counts=Counter(options.values())
    for n,key in enumerate(sorted(options),1):
        if counts[options[key]]>1:options[key]+=f' ({n})'
    replacements={**products,**ingredients,**options}
    cards=[]
    for c in baseline.facts:
        if c.kind=='gap':continue # rebuild below with Product identity, not label matching
        updates={}
        if c.kind=='purchase_quantity' and scope.ingredient_id:
            updates['label']=ingredients[str(scope.ingredient_id)]
        if c.kind=='pair_service' and c.entity_id in products:updates['label']=products[c.entity_id]
        text=display_fact(c,request.locale)
        if c.label:
            own=products.get(c.entity_id) if c.kind in ('requirement','pair_service') else ingredients.get(c.entity_id) if c.kind=='mechanistic' else None
            if own:text=text.replace(c.label,own)
        for original,label in sorted(replacements.items(),key=lambda p:-len(p[0])):text=text.replace(original,label)
        text=text.replace('Phương án Phương án ','Phương án ').replace('Option Option ','Option ')
        if c.kind=='winner':text='Có phương án được khuyến nghị.' if vi else 'A recommended option is available.'
        if c.kind=='selector':text=('Chỉ so sánh các phương án đủ điều kiện: ưu tiên chi phí, rồi mức đáp ứng từng món và quy tắc khi hòa.' if vi else
            'Compare eligible evaluated options by cost, then per-Product service and the retained tie-break rule.')
        if text!=display_fact(c,request.locale) or c.kind in ('rejection','gap','eligibility','requirement','pair_cost'):
            updates['presentation']=text.rstrip('.')
        cards.append(c.model_copy(update=updates))
    if scope.intent=='outcome':
        refs=tuple(r.evidence_id for r in evidence.references if r.pointer=='/overview/explanation')
        seen=set()
        for option in o.explanation.options:
            for row in option.evidence:
                for gap in row.customer_gaps:
                    key=(option.option_id,str(gap.product_id),gap.path,gap.shortfall.decimal_view,gap.unit)
                    if gap.shortfall.numerator=='0' or key in seen:continue
                    seen.add(key);name=products[str(gap.product_id)]
                    text=(f'{options[option.option_id]}, món «{name}», {gap.path}: còn thiếu {gap.shortfall.decimal_view} {gap.unit} để đáp ứng yêu cầu đã lưu' if vi else
                        f'{options[option.option_id]}, Product «{name}», {gap.path}: retained requirement shortfall {gap.shortfall.decimal_view} {gap.unit}')
                    cards.append(FactCard(fact_id='f-'+digest('chat-gap/3',[evidence.identity,key])[:20],kind='gap',meaning='retained Product/path shortfall',
                        display=gap.shortfall.decimal_view,unit=gap.unit,entity_id=option.option_id,product_id=gap.product_id,path=gap.path,label=name,presentation=text,evidence_ids=refs))

    # Group only exact matching assessments with complete declared Product/path
    # coverage and no excluded scope. Exceptions/missing rows stay explicit.
    if request.detail_level=='simple' and evidence.option and o.scope and not o.scope.excluded_products and not (context and context.product_id):
        assessment=evidence.option.requirements_assessment
        expected={(p.product_id,r.path) for p in o.scope.menu_products if p.product_id in o.scope.computed_product_ids
            for r in o.configuration.effective_requirements.paths}
        actual={(a.product_id,a.path) for a in assessment}
        if actual==expected and len(actual)==len(assessment):
            groups=defaultdict(list)
            by_key={(str(a.product_id),a.path):a for a in assessment}
            for c in cards:
                if c.kind=='requirement':
                    a=by_key[(c.entity_id,c.path)]
                    if a.status=='PASS' and a.shortfall and a.shortfall.numerator=='0':
                        unit=next(p.selling_unit for p in o.scope.menu_products if str(p.product_id)==c.entity_id)
                        groups[(c.path,a.target_percent,unit)].append(c)
            for (path,target,unit),members in groups.items():
                if len(members)<2:continue
                names=', '.join('«'+products[c.entity_id]+'»' for c in members)
                text=(f'Các món {names}: đạt yêu cầu {path} tối thiểu {target}%; thiếu 0 {unit} mỗi món' if vi else
                    f'Products {names}: PASS minimum {target}% on {path}; shortfall 0 {unit} each')
                values={(c.entity_id,c.path):(by_key[(c.entity_id,c.path)],unit) for c in members}
                ids={c.fact_id for c in members};cards=[c for c in cards if c.fact_id not in ids]+[group_card('requirements',members,text,assessments=values)]
    if request.detail_level=='simple':
        groups=defaultdict(list)
        for c in cards:
            if c.kind=='pair_service':groups[(c.entity_id,c.display,c.unit)].append(c)
        for (entity,value,unit),members in groups.items():
            if len(members)<2 or len({m.path for m in members})!=len(members):continue
            paths=', '.join(sorted(m.path for m in members))
            text=(f'Mô phỏng món «{products[entity]}»: chênh lệch lượng phục vụ {value} {unit} trên {paths}' if vi else
                f'Simulated Product «{products[entity]}»: fulfilled quantity delta {value} {unit} on {paths}')
            ids={c.fact_id for c in members};cards=[c for c in cards if c.fact_id not in ids]+[group_card('pair_service',members,text,display=value,unit=unit,entity=entity,path=paths)]
        boundary=[c for c in cards if c.kind in ('proof_boundary','unproven')]
        if {c.kind for c in boundary}=={'proof_boundary','unproven'}:
            text=('Chỉ xét các phương án đã đánh giá; tìm kiếm chưa có chứng nhận đầy đủ trong miền hữu hạn đã lưu và chưa chứng minh tối ưu toàn cục' if vi else
                'Only evaluated options are compared; search has no complete retained finite-domain certificate or global optimality proof')
            ids={c.fact_id for c in boundary};cards=[c for c in cards if c.fact_id not in ids]+[group_card('boundary',boundary,text)]
    required=tuple(c.fact_id for c in cards if c.fact_id in baseline.required or c.group is not None or c.kind=='gap')
    safety=baseline.safety_claims
    pair=next((p for p in o.comparisons or () if (p.from_option_id,p.to_option_id)==scope.comparison_pair),None)
    if pair and scope.intent=='comparison':
        refs=tuple(r.evidence_id for r in evidence.references if r.pointer=='/overview/comparisons')
        safety=(ChatClaim(text=(f'So sánh {options[pair.to_option_id]} trừ {options[pair.from_option_id]}; lượng phục vụ là mô phỏng.' if vi else
            f'Compare {options[pair.to_option_id]} minus {options[pair.from_option_id]}; fulfilled quantities are simulated.'),evidence_ids=refs),)
    fallback=baseline.fallback
    if fallback.kind=='clarification':
        fallback=fallback.model_copy(update={'diagnostics':ChatDiagnostics(reason='EVIDENCE_INSUFFICIENT',validator_version='decision_chat_renderer/8',disposition='CLARIFICATION')})
    elif cards:
        claims=tuple(ChatClaim(text=display_fact(c,request.locale).rstrip('.')+'.',evidence_ids=c.evidence_ids) for c in cards if c.fact_id in required)+safety
        used={i for c in claims for i in c.evidence_ids}
        fallback=fallback.model_copy(update={'answer':'\n\n'.join(c.text for c in claims),'claims':claims,
            'references':tuple(r for r in evidence.references if r.evidence_id in used),
            'diagnostics':ChatDiagnostics(reason='MODEL_DISABLED',validator_version='decision_chat_renderer/8')})
    return baseline.model_copy(update={'version':'chat_evidence/7','resolver_version':'chat_resolution/5','facts':tuple(cards),'required':required,'safety_claims':safety,'fallback':fallback})
