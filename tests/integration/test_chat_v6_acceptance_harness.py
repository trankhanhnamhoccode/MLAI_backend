"""No paid calls: actual HTTP and authority audit with a fake provider."""
import json
import pytest
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env


@pytest.mark.parametrize('case',['budget','conversation'])
def test_acceptance_authority_and_four_turn_harness_offline(assistant,monkeypatch,tmp_path,case):
    from tests.live import test_chat_v6_acceptance as live
    from tests.live import test_chat_l32_live as original
    from scripts import conversational_v6_acceptance as batch
    from app.application.contracts.chat_generation import FactCard,SemanticOutput
    from app.application.chat_assertions import proposal
    from app.application.contracts.assistant_chat import ChatDiagnostics
    from app.infrastructure.conversational_provider import ChatProviderResult
    import dotenv
    root=tmp_path/batch.GROUP;root.mkdir()
    version=original.fingerprint()
    (root/f'freeze-{version}.json').write_text(json.dumps({'frozen_version':version}))
    monkeypatch.setattr(batch,'ROOT',root);monkeypatch.setattr(original,'BASE',tmp_path)
    monkeypatch.setattr(dotenv,'dotenv_values',lambda *a,**k:dict(SUMMARY_MODEL='google/gemini-2.5-flash',OPENROUTER_API_KEY='OFFLINE_FAKE_NOT_A_KEY'))
    class Fake:
        def __init__(self,*a,**k):pass
        def generate(self,payload,profile,*,before_completion):
            before_completion();assertions=[]
            for data in payload['facts']:
                if data['fact_id'] in payload['required']:
                    card=FactCard(**{k:v for k,v in data.items() if k!='wording'})
                    assertions.append(proposal(card,data['wording']+'.'))
            return ChatProviderResult(SemanticOutput(assertions=tuple(assertions)),ChatDiagnostics(reason='NONE',disposition='ACCEPTED',provider='OFFLINE_FAKE'))
    monkeypatch.setattr(original,'OpenRouterConversationalProvider',Fake)
    live.test_v6_acceptance_as03(assistant,case,monkeypatch)
    finals=[json.loads(p.read_text(encoding='utf8')) for p in root.glob('final-*')]
    assert len(finals)==(4 if case=='conversation' else 1)
    assert all(f['authority_checks']['other_store_membership_status']==404 for f in finals)
    assert all(f['replay_completions']==0 and f['fresh_persisted_response'] for f in finals)
    if case=='conversation':
        turns=sorted(finals,key=lambda f:f['turn'])
        assert turns[0]['final']['kind']=='clarification'
        assert turns[1]['final']['ingredient_id']!=turns[3]['final']['ingredient_id']
