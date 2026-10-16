"""Offline generation loop in isolation; SQL/authority tests remain separate."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tests.unit.test_chat_l32 import current
from app.application.contracts.chat_generation import ChatProfile,SemanticOutput
from app.application.contracts.assistant_chat import ChatDiagnostics
from app.application.chat_assertions import proposal
from app.application.use_cases.conversational_chat import ConversationalChat
from app.infrastructure.conversational_provider import ChatProviderResult


@pytest.mark.parametrize('mode,expected,calls',[('repair','REPAIRED',1),('trim','TRIMMED',1),('regen','REGENERATED',2),('bad_main','FALLBACK',2),('unknown','FALLBACK',1),('unknown_second','FALLBACK',2)])
def test_offline_generation_dispositions_and_replayable_verified_output(mode,expected,calls):
    p,r,_=current();raw=[];before=[]
    class Fake:
        def generate(self,payload,profile,*,before_completion):
            before_completion();n=len(raw)
            rows=[proposal(f) for f in p.facts if f.fact_id in p.required]
            if mode=='unknown' or mode=='unknown_second' and n==1:
                raw.append({'transport':'UNKNOWN'});raise TimeoutError()
            if mode=='repair':rows[0]=rows[0].model_copy(update={'value':'99','text':'Tổng chi là 99 VND.'})
            if mode=='trim':rows.append(proposal(next(f for f in p.facts if f.kind=='fees'),'Phí là 9 kg.'))
            if mode=='bad_main' or mode in ('regen','unknown_second') and n==0:rows[0]=rows[0].model_copy(update={'text':'Tổng chi là 10 VND vì nhu cầu tăng.'})
            output=SemanticOutput(assertions=tuple(rows));raw.append(output.model_dump(mode='json'))
            return ChatProviderResult(output,ChatDiagnostics(reason='NONE',disposition='ACCEPTED',model='fake',resolved_model='fake',provider='OFFLINE_FAKE',
                attempts=1,input_tokens=10,output_tokens=20,cost_usd='.001',prompt_version='conversational_chat_prompt/4',validator_version='chat_assertions/4'))
    use=ConversationalChat(SimpleNamespace(engine=None,provider=Fake()))
    use.before_completion=lambda *args:before.append('fenced')
    claimed=SimpleNamespace(profile=ChatProfile(enabled=True,model='fake',completion_limit=2),prompt_version='conversational_chat_prompt/4',validator_version='chat_assertions/4')
    final,verified=use.generate(claimed,p,r,None,None)
    assert final.diagnostics.disposition==expected and len(raw)==calls and len(before)==calls
    if mode in ('unknown','unknown_second'):
        assert final.diagnostics.cost_usd is None and final.diagnostics.input_tokens is None and final.diagnostics.output_tokens is None
    if verified:
        from app.application.chat_assertions import semantic_answer
        assert semantic_answer(verified,p,final.diagnostics)==final
    out=Path('runtime/assistant-test/l32');out.mkdir(parents=True,exist_ok=True)
    (out/f'offline-generation-{mode}.json').write_text(json.dumps(dict(mode='OFFLINE_FAKE_PROVIDER',request=r.model_dump(mode='json'),
        facts=[f.model_dump() for f in p.facts],raw=raw,final=final.model_dump(mode='json'),verified_output=verified.model_dump(mode='json') if verified else None,
        limitation='Generation loop only; not HTTP/PostgreSQL authorization or live acceptance.'),ensure_ascii=False,indent=2),encoding='utf8')
