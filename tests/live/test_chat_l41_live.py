import json,os
from pathlib import Path
import pytest
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.live import test_chat_l32_live as original
from tests.live.test_chat_v6_acceptance import audit_authority
from tests.assistant_l41_cases import create_milk_run
from tests.assistant_cases import row_for
from scripts import conversational_l41_live as acceptance
from scripts import conversational_l4_live as ledger

pytestmark=pytest.mark.skipif(os.environ.get('SHELFCASH_CHAT_L41_LIVE')!='remaining-l4',reason='Explicit remaining L4 paid opt-in required')


@pytest.mark.parametrize('case',acceptance.CASES)
def test_l41_live_as03(assistant,case,monkeypatch):
    monkeypatch.setattr(original,'ROOT',acceptance.ROOT)
    monkeypatch.setattr(original,'reserve',lambda base,record:ledger.reserve(base,dict(record,phase='l41-candidate8')))
    monkeypatch.setattr(original,'reservations',ledger.reservations)
    monkeypatch.setattr(original,'MAX_ATTEMPTS',24);monkeypatch.setattr(original,'CASES',acceptance.CASES)
    factory=original.AssistantChat
    monkeypatch.setattr(original,'AssistantChat',lambda *a,**k:factory(*a,**k,presentation_version=8))
    parent=original.Transport
    class Transport(parent):
        def open(self,request,timeout):
            assert not (ledger.ROOT/'STOP-429.json').exists(),'HTTP429 stops whole L4 group'
            try:return super().open(request,timeout)
            finally:
                if self.rate_limited:
                    stop=ledger.ROOT/'STOP-429.json'
                    if not stop.exists():
                        with stop.open('x',encoding='utf8') as out:json.dump(dict(http_status=429,phase='l41-candidate8',usage='UNKNOWN unless saved'),out)
    monkeypatch.setattr(original,'Transport',Transport)
    def retained(engine,actor):
        record=create_milk_run(engine,actor,'milk' if case=='conversation' else case)
        path=acceptance.ROOT/f'retained-{case}-{record.run_id}.json'
        with path.open('x',encoding='utf8') as out:json.dump(dict(mode='SYNTHETIC_ENGINE_FACTORY_VALIDATED_PERSISTED',
            aggregate_sha256=row_for(record).record_digest,record=record.model_dump(mode='json')),out,ensure_ascii=False,indent=2)
        return record
    original.run_case(assistant,case,monkeypatch,audit_final=audit_authority,record_factory=retained)
