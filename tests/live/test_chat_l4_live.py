"""Paired, separately opt-in synthetic L4; no old ledger writes."""
import json,os
import pytest
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.live import test_chat_l32_live as original
from tests.live.test_chat_v6_acceptance import audit_authority
from scripts import conversational_l4_live as batch

PHASE=os.environ.get('SHELFCASH_CHAT_L4_LIVE')
pytestmark=pytest.mark.skipif(PHASE not in ('baseline','candidate'),reason='Separate paid L4 opt-in required')
CORPUS=json.loads(open('tests/fixtures/assistant_l4/corpus.json',encoding='utf8').read())


@pytest.mark.parametrize('case',CORPUS['live_subset'])
def test_l4_live_as03(assistant,case,monkeypatch):
    monkeypatch.setattr(original,'ROOT',batch.ROOT/PHASE)
    monkeypatch.setattr(original,'reserve',lambda base,record:batch.reserve(base,dict(record,phase=PHASE)))
    monkeypatch.setattr(original,'reservations',batch.reservations)
    monkeypatch.setattr(original,'MAX_ATTEMPTS',batch.MAX_ATTEMPTS)
    monkeypatch.setattr(original,'CASES',CORPUS['live_questions'])
    if PHASE=='candidate':
        factory=original.AssistantChat
        monkeypatch.setattr(original,'AssistantChat',lambda *args,**kwargs:factory(*args,**kwargs,presentation_version=7))
    parent=original.Transport
    class Transport(parent):
        def open(self,request,timeout):
            assert not (batch.ROOT/'STOP-429.json').exists(),'HTTP429 stops whole L4 batch'
            try:return super().open(request,timeout)
            finally:
                if self.rate_limited:
                    stop=batch.ROOT/'STOP-429.json'
                    if not stop.exists():
                        with stop.open('x',encoding='utf8') as out:json.dump(dict(http_status=429,phase=PHASE,usage='UNKNOWN unless saved'),out)
    monkeypatch.setattr(original,'Transport',Transport)
    original.run_case(assistant,case,monkeypatch,audit_final=audit_authority)
