"""Offline sealed-fact/contract probes, not model outputs or naturalness grading."""
import argparse,json
from pathlib import Path
from app.application.chat_assertions import proposal,inspect_output
from app.application.contracts.chat_generation import SemanticOutput
from tests.l4_cases import build,CORPUS


def evaluate(spec,version):
    if spec.get('check'):
        return dict(id=spec['id'],split=spec['split'],stratum=spec['stratum'],status='SEPARATE_SQL_AUTHORITY_GATE',passed=None)
    context=None;turns=[]
    for q in spec.get('turns',[spec.get('question')]):
        plan,req,evidence=build(spec,version,question=q,context=context);context=plan.fallback.context
        # A valid pointer may resolve to null (known unavailable). Only a raised
        # resolution error means dangling, not the value's truthiness.
        for ref in plan.fallback.references:evidence.resolve(ref.evidence_id)
        turns.append(dict(question=q,ingredient_id=str(plan.ingredient_id),kind=plan.fallback.kind,answer=plan.fallback.answer,
            required=list(plan.required),facts=[f.model_dump(mode='json') for f in plan.facts],references_resolve=True))
    checks=[]
    if 'expected_quantity' in spec:checks.append(any(f.kind=='purchase_quantity' and f.display==spec['expected_quantity'] for f in plan.facts))
    if 'expected_kind' in spec:checks.append(any(f.kind==spec['expected_kind'] for f in plan.facts))
    if 'expected_values' in spec:checks.extend(any(f.kind==k and f.display==v for f in plan.facts) for k,v in spec['expected_values'].items())
    if spec.get('turns'):
        expected=['20','35'] if spec['id']=='D10' else ['35','20']
        checks.append(turns[0]['kind']=='clarification')
        checks.append(expected[0]+' g' in turns[1]['answer'] and expected[1]+' g' in turns[-1]['answer'])
        checks.append(turns[1]['ingredient_id']!=turns[-1]['ingredient_id'])
    if spec.get('fixture')=='foreign_context':checks.append(plan.fallback.kind=='clarification')
    if spec.get('fixture')=='named_other':checks.append(any(f.kind=='viewed_role' for f in plan.facts))
    if spec.get('fixture')=='failed-partial':checks.append(not evidence.overview.recommendation_available and 'lỗi' in plan.fallback.answer.lower())
    # Independent oracle values, not just valid references or validator self-agreement.
    pair=next((f for f in plan.facts if f.kind=='pair_cost'),None)
    if spec['stratum']=='comparison':
        expected='-5' if spec.get('fixture')=='negative_pair' else '0' if spec.get('fixture')=='zero_pair' else '5'
        checks.append(pair is not None and pair.display==expected)
        members=[m for f in plan.facts if f.group for m in f.group.members] if version=='chat_evidence/7' else []
        services=[f for f in plan.facts if f.kind=='pair_service']+[m for m in members if m.kind=='pair_service']
        checks.append({f.path for f in services}=={'BASE','HIGH','LOW'} and len(services)==6)
        expected_values={'-5','-10'} if expected=='-5' else {'0'} if expected=='0' else {'1','5','10'} if spec.get('fixture')=='different_paths' else {'5','10'}
        checks.append({f.display for f in services}==expected_values)
    if spec.get('fixture')=='exception':checks.append(any('FAIL' in f.meaning and '1 cup' in f.meaning for f in plan.facts))
    if spec.get('fixture')=='missing_assessment':checks.append(not any(f.group for f in plan.facts) if version=='chat_evidence/7' else True)
    if spec.get('fixture')=='infeasible' and spec['stratum']=='outcome':checks.append({f.display for f in plan.facts if f.kind=='gap'}=={'9.5','19'})
    if spec['stratum']=='why':
        checks.append(any(f.kind=='detail_unknown' for f in plan.facts))
        if spec.get('fixture')=='different_milk':checks.append(any(f.kind=='purchase_quantity' and f.display=='35' for f in plan.facts))
    probe=None
    if 'expected_valid' in spec:
        out=SemanticOutput(assertions=tuple(proposal(f) for f in plan.facts if f.fact_id in plan.required))
        assertions=list(out.assertions)
        if 'text' in spec:assertions[0]=assertions[0].model_copy(update={'text':spec['text']})
        mutation=spec.get('mutation')
        if mutation=='wrong_path':assertions[-1]=assertions[-1].model_copy(update={'path':'PRIVATE_PATH'})
        if mutation=='wrong_polarity':assertions[0]=assertions[0].model_copy(update={'polarity':'unavailable'})
        if mutation=='wrong_option_role':assertions[0]=assertions[0].model_copy(update={'option_role':'viewed'})
        if mutation=='wrong_cost_role':assertions[0]=assertions[0].model_copy(update={'text':'Ngân sách là 5 VND.'})
        if mutation=='unproven_optimal':
            n=next(i for i,a in enumerate(assertions) if any(f.fact_id==a.fact_id and f.kind in ('unproven','grouped_boundary') for f in plan.facts))
            assertions[n]=assertions[n].model_copy(update={'text':'Đây là phương án tối ưu toàn cục.'})
        if mutation=='missing_main':assertions.pop()
        inspection=inspect_output(SemanticOutput(assertions=tuple(assertions)),plan,'vi',allow_repair=False)
        accepted=inspection.output is not None
        probe=dict(expected_valid=spec['expected_valid'],accepted=accepted,failures=inspection.failures,
            false_acceptance=accepted and not spec['expected_valid'],false_rejection=not accepted and spec['expected_valid'])
        checks.append(accepted==spec['expected_valid'])
    checks.append(all(t['references_resolve'] for t in turns))
    return dict(id=spec['id'],split=spec['split'],stratum=spec['stratum'],passed=all(checks),checks=checks,probe=probe,turns=turns,
        canonical_fallback_chars=len(plan.fallback.answer),canonical_claims=len(plan.fallback.claims),
        opaque_ids_in_prose='cmp1_' in plan.fallback.answer,mode='OFFLINE_CONTRACT_INPUTS_AND_AUTHORED_ASSERTIONS_NOT_MODEL_OUTPUTS')


def main():
    p=argparse.ArgumentParser();p.add_argument('--version',choices=('6','7'),required=True);p.add_argument('--split',choices=('development','evaluation','all'),default='development')
    p.add_argument('--output',required=True);a=p.parse_args()
    corpus=json.loads(CORPUS.read_text(encoding='utf8'));rows=[]
    for spec in corpus['scenarios']:
        if a.split!='all' and spec['split']!=a.split:continue
        try:rows.append(evaluate(spec,'chat_evidence/'+a.version))
        except Exception as e:rows.append(dict(id=spec['id'],split=spec['split'],stratum=spec['stratum'],passed=False,error=type(e).__name__+': '+str(e)))
    result=dict(version='chat_evidence/'+a.version,split=a.split,author=corpus['label_author'],mode='OFFLINE_NO_PROVIDER_NO_DB',
        passed=sum(r.get('passed') is True for r in rows),failed=sum(r.get('passed') is False for r in rows),
        separately_verified=sum(r.get('passed') is None for r in rows),false_acceptances=sum(bool((r.get('probe') or {}).get('false_acceptance')) for r in rows),
        false_rejections=sum(bool((r.get('probe') or {}).get('false_rejection')) for r in rows),rows=rows)
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as out:json.dump(result,out,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':main()
