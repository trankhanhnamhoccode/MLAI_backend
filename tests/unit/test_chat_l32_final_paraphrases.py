"""Two observed legitimate paraphrases; V5 remains immutable, V6 fixes offline."""
import pytest
from tests.unit.test_chat_l32 import current,answer
from app.application.chat_assertions import inspect_output,proposal


@pytest.mark.parametrize('kind',['detail_unknown','rejection'])
def test_remaining_live_paraphrases_preserve_slots_scope_and_negative_meaning(kind):
    p,_,_=current('Vì sao Sữa tươi cần mua?') if kind=='detail_unknown' else current('Không có winner, vướng gì?',kind='infeasible')
    out=answer(p);facts={f.fact_id:f for f in p.facts};rows=[]
    for a in out.assertions:
        if facts[a.fact_id].kind==kind:
            a=a.model_copy(update={'text':a.text.replace('Evidence đang dùng chưa có','Không có') if kind=='detail_unknown' else a.text.replace(': ',' ',1)})
        rows.append(a)
    observed=out.model_copy(update={'assertions':tuple(rows)})
    assert inspect_output(observed,p,'vi').output
    assert inspect_output(observed,p.model_copy(update={'version':'chat_evidence/5'}),'vi').output is None
    # Exact quantity, role, path/entity and polarity remain independently checked.
    selected=next(i for i,a in enumerate(rows) if facts[a.fact_id].kind==kind)
    for update in ({'polarity':'affirmed' if kind=='detail_unknown' else 'unavailable'},
                   {'text':rows[selected].text+' Vì nhu cầu tăng.'},
                   {'text':'Không phải không có '+rows[selected].text},
                   {'text':rows[selected].text.replace('Không có','Có') if kind=='detail_unknown' else rows[selected].text.replace('chưa đáp ứng','đáp ứng')}):
        bad=observed.model_copy(update={'assertions':tuple(a.model_copy(update=update) if i==selected else a for i,a in enumerate(rows))})
        assert inspect_output(bad,p,'vi').output is None


def test_rejection_optional_colon_cannot_authorize_a_different_option_or_unknown_reference():
    p,_,_=current('Không có winner, vướng gì?',kind='infeasible');out=answer(p)
    fact=next(f for f in p.facts if f.kind=='rejection');idx=next(i for i,a in enumerate(out.assertions) if a.fact_id==fact.fact_id)
    a=proposal(fact).model_copy(update={'text':proposal(fact).text.replace(': ',' ',1).replace(fact.entity_id,'other-option')})
    assert inspect_output(out.model_copy(update={'assertions':(*out.assertions[:idx],a,*out.assertions[idx+1:])}),p,'vi').output is None

    a=proposal(fact).model_copy(update={'fact_id':'unknown'})
    assert inspect_output(out.model_copy(update={'assertions':(*out.assertions[:idx],a,*out.assertions[idx+1:])}),p,'vi').output is None


def test_current_provider_task_uses_semantic_schema_and_v6_diagnostics_with_fake_transport():
    from pydantic import SecretStr
    from tests.unit.test_conversational_chat import Transport
    from app.infrastructure.conversational_provider import OpenRouterConversationalProvider,payload_for
    from app.application.contracts.chat_generation import ChatProfile
    p,r,_=current('Vì sao chọn phương án này?');output=answer(p);transport=Transport(output);fences=[]
    result=OpenRouterConversationalProvider(SecretStr('synthetic'),opener=transport).generate(payload_for(p,r),
        ChatProfile(enabled=True,model='synthetic-gemini',input_bytes=24000,max_tokens=1200),before_completion=lambda:fences.append(True))
    assert result.output==output and result.diagnostics.reason=='NONE'
    assert result.diagnostics.prompt_version=='conversational_chat_prompt/5' and result.diagnostics.validator_version=='chat_assertions/6'
    assert result.diagnostics.attempts==transport.completions==len(fences)==1
