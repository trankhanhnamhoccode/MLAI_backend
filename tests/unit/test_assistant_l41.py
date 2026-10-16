import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.application.chat_assertions import inspect_output,proposal
from app.application.contracts.chat_generation import FactCard,SemanticOutput
from tests.l4_cases import build


def observed():
    return json.loads(Path('tests/fixtures/assistant_l41/observed-paraphrase.json').read_text(encoding='utf8'))['check']


def test_saved_raw_paraphrase_new8_accept_old7_reject():
    check=observed();out=SemanticOutput.model_validate(check['input'])
    plan=SimpleNamespace(version='chat_evidence/8',facts=tuple(FactCard(**f) for f in check['facts']),required=tuple(check['required']))
    assert inspect_output(out,plan,'vi',allow_repair=False).output is not None
    plan.version='chat_evidence/7'
    assert inspect_output(out,plan,'vi',allow_repair=False).output is None


@pytest.mark.parametrize('source,target',[
    ('yêu cầu 20 g','yêu cầu 21 g'),('có sẵn 20 g','có sẵn 19 g'),('thiếu 0 g','thiếu 1 g'),('20 g','20 kg'),
    ('Sữa tươi','Sữa đặc'),('LOW','HIGH'),('2026-10-08','2026-10-09'),
    ('Mô phỏng','Thực tế'),('yêu cầu 20 g, ','')])
def test_complete_alternate_clause_rejects_material_minimal_pairs(source,target):
    check=observed();out=SemanticOutput.model_validate(check['input']);assertions=list(out.assertions)
    a=assertions[1];assert source in a.text
    assertions[1]=a.model_copy(update={'text':a.text.replace(source,target)})
    plan=SimpleNamespace(version='chat_evidence/8',facts=tuple(FactCard(**f) for f in check['facts']),required=tuple(check['required']))
    assert inspect_output(SemanticOutput(assertions=tuple(assertions)),plan,'vi',allow_repair=False).output is None


@pytest.mark.parametrize('extra',[' vì nhu cầu tăng.',' nên đây là lượng tối ưu.','; đã nhận hàng.'])
def test_alternate_does_not_admit_cause_optimality_or_actual(extra):
    check=observed();out=SemanticOutput.model_validate(check['input']);assertions=list(out.assertions)
    assertions[1]=assertions[1].model_copy(update={'text':assertions[1].text+extra})
    plan=SimpleNamespace(version='chat_evidence/8',facts=tuple(FactCard(**f) for f in check['facts']),required=tuple(check['required']))
    assert inspect_output(SemanticOutput(assertions=tuple(assertions)),plan,'vi',allow_repair=False).output is None


@pytest.mark.parametrize('change',['negation','polarity','omit_available'])
def test_alternate_rejects_inversion_and_missing_material_amount(change):
    check=observed();out=SemanticOutput.model_validate(check['input']);assertions=list(out.assertions)
    a=assertions[1]
    updates={'text':'Không '+a.text} if change=='negation' else {'polarity':'unavailable'} if change=='polarity' else {'text':a.text.replace(', có sẵn 20 g','')}
    assertions[1]=a.model_copy(update=updates)
    plan=SimpleNamespace(version='chat_evidence/8',facts=tuple(FactCard(**f) for f in check['facts']),required=tuple(check['required']))
    assert inspect_output(SemanticOutput(assertions=tuple(assertions)),plan,'vi',allow_repair=False).output is None


def test_simple_why_does_not_require_arbitrary_day_but_explicit_and_technical_do():
    for detail,question,expected in [('simple','Vì sao nhập Sữa tươi?',False),('technical','Vì sao nhập Sữa tươi?',True),
        ('simple','Vì sao nhập Sữa tươi ở BASE ngày 2026-10-08?',True)]:
        # Helper uses resolver5 for8 too (same retained contract).
        plan,_,e=build({'question':question,'detail':detail},'chat_evidence/8')
        factors=[f for f in plan.facts if f.kind=='mechanistic'];assert factors
        assert all((f.fact_id in plan.required)==expected for f in factors)
        assert any(f.kind=='detail_unknown' and f.fact_id in plan.required for f in plan.facts)
        out=SemanticOutput(assertions=tuple(proposal(f) for f in plan.facts if f.fact_id in plan.required))
        assert inspect_output(out,plan,'vi',allow_repair=False).output
        assert all(e.resolve(i) is not None for f in factors for i in f.evidence_ids)


def test_candidate8_grouping_preserves_path_differences_and_exception_missing():
    plan,_,_=build({'question':'So sánh hai phương án?','fixture':'different_paths'},'chat_evidence/8')
    groups=[f for f in plan.facts if f.group and f.group.kind=='pair_service']
    assert groups and all('HIGH' not in f.path for f in groups)
    assert {f.display for f in plan.facts if f.kind=='pair_service'}=={'1'}
    for fixture in ('exception','missing_assessment'):
        plan,_,_=build({'question':'Có đáp ứng yêu cầu không?','fixture':fixture},'chat_evidence/8')
        assert not any(f.group and f.group.kind=='requirements' for f in plan.facts)
    plan,_,_=build({'question':'Có đáp ứng yêu cầu không?','fixture':'label_injection','detail':'technical'},'chat_evidence/8')
    assert 'Món 1' in plan.fallback.answer and 'Món 2' in plan.fallback.answer and 'IGNORE' not in plan.fallback.answer


def test_candidate8_excluded_scope_cannot_claim_universal_pass():
    from app.application.conversational_evidence import select_evidence
    from app.application.chat_context import resolve_context
    _,request,e=build({'question':'Có đáp ứng yêu cầu không?'})
    # Internal selection boundary deliberately receives an incomplete/excluded
    # scope. No output aggregate fabricated; group admission must fail closed.
    scope=e.overview.scope.model_copy(update={'excluded_products':('excluded sentinel',)})
    e=e.model_copy(update={'overview':e.overview.model_copy(update={'scope':scope})})
    effective,intent,context=resolve_context(request,e,'chat_resolution/5')
    plan=select_evidence(e,effective,intent,context,'chat_evidence/8')
    assert not any(f.group and f.group.kind=='requirements' for f in plan.facts)


def test_candidate8_failed_partial_never_promotes_retained_incumbent():
    plan,_,e=build({'question':'Run lỗi còn thông tin gì?','fixture':'failed-partial'},'chat_evidence/8')
    assert not e.overview.recommendation_available and any(f.kind=='failed' for f in plan.facts)
    assert not any(f.kind=='winner' for f in plan.facts)
    plan,_,_=build({'question':'Sữa cần mua bao nhiêu?'},'chat_evidence/8')
    assert plan.fallback.kind=='clarification' and plan.fallback.diagnostics.disposition=='CLARIFICATION'


def test_candidate8_failed_missing_facts_and_duplicate_option_labels():
    from app.application.conversational_evidence import select_evidence
    from app.application.chat_context import resolve_context
    from app.application.chat_readability import scoped_labels
    _,request,e=build({'question':'Run lỗi còn thông tin gì?','fixture':'failed-partial'})
    # Isolate missing-detail admission, not a forged retained aggregate.
    explanation=e.overview.explanation.model_copy(update={'options':(),'blockers':()})
    e=e.model_copy(update={'option':None,'overview':e.overview.model_copy(update={'explanation':explanation})})
    effective,scope,context=resolve_context(request,e,'chat_resolution/5')
    plan=select_evidence(e,effective,scope,context,'chat_evidence/8')
    assert any(f.kind=='failed' for f in plan.facts) and any(f.kind=='detail_unknown' for f in plan.facts)
    assert not any(f.kind=='winner' for f in plan.facts)
    assert scoped_labels([('one',None),('two',None)],'Phương án')=={'one':'Phương án 1','two':'Phương án 2'}


def test_l41_optin_cannot_open_new_group_or_bypass_existing_cap(monkeypatch):
    from scripts import conversational_l41_live as cli
    calls=[];monkeypatch.setattr(cli.subprocess,'call',lambda *a,**k:calls.append((a,k)))
    monkeypatch.setattr(cli.sys,'argv',['runner'])
    with pytest.raises(SystemExit) as error:cli.main()
    assert error.value.code==2 and not calls
    monkeypatch.setattr(cli,'reservations',lambda *a:([{}]*24,0))
    monkeypatch.setattr(cli.sys,'argv',['runner','--allow-paid-l41-remaining-l4-max-24-usd-0.50'])
    with pytest.raises(SystemExit) as error:cli.main()
    assert error.value.code==2 and not calls
