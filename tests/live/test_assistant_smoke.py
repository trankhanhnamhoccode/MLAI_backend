"""Explicit opt-in only. Synthetic fixtures, owned DB, write-ahead paid-call cap."""
import io
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen, build_opener

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('SHELFCASH_LIVE_SMOKE') != 'authorized-synthetic-3-0.10',
                              reason='Explicit standalone live smoke authorization required')

from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from app.infrastructure.import_suggestions import NoRedirect
from app.infrastructure.plan_summary_provider import OpenRouterSummaryProvider
from app.application.contracts.plan_summary import SummaryAnswer


class CappedTransport:
    def __init__(self, root, model):
        self.root, self.model = root, model
        self.calls = 0
        self.observed = {}

    def open(self, request, timeout):
        sent = json.loads(request.data)
        assert sent['model'] == self.model == 'google/gemini-2.5-flash'
        assert len(request.data) <= 16000 and sent['max_tokens'] <= 256
        assert sent['provider']['allow_fallbacks'] is False
        required = {'temperature', 'max_tokens', 'response_format', 'structured_outputs'}
        url = f'https://openrouter.ai/api/v1/models/{self.model}/endpoints'
        with urlopen(url, timeout=15) as response:
            metadata = json.load(response)
        endpoints = metadata['data']['endpoints']
        assert any(required <= set(e['supported_parameters']) for e in endpoints)
        # USD per million: exclude expensive endpoints rather than raise the cap.
        prices = {'prompt': Decimal('0.0000003'), 'completion': Decimal('0.0000025')}
        assert any(all(Decimal(e['pricing'][k]) <= v for k,v in prices.items())
                   and required <= set(e['supported_parameters']) for e in endpoints)
        assert all(Decimal(e['pricing'].get('request','0')) == 0 for e in endpoints)
        # Text-only <=16KiB serialized input, generous envelope/token overhead.
        bound = Decimal(65536)*prices['prompt'] + Decimal(256)*prices['completion']
        assert bound*3 <= Decimal('0.10')
        self.root.mkdir(parents=True, exist_ok=True)
        # Exclusive slots survive crashes/timeouts. Never refund an uncertain call.
        for attempt in range(1, 4):
            try:
                with (self.root/f'attempt-{attempt}.json').open('x', encoding='utf-8') as output:
                    json.dump({'reserved_usd':str(bound),'model':self.model,'timestamp':time.time()}, output)
                break
            except FileExistsError:
                continue
        else:
            raise AssertionError('Three completion attempts already reserved; no network call')
        sent['provider']['max_price'] = {'prompt':0.3,'completion':2.5}
        request.data = json.dumps(sent).encode()
        self.calls += 1
        started = time.monotonic()
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(65537)
        assert len(raw) <= 65536
        body = json.loads(raw)
        # Only allowlisted synthetic output/metrics; never headers or request secrets.
        self.observed = {k:body.get(k) for k in ('model','provider','usage','choices')}
        self.observed.update(latency_seconds=time.monotonic()-started, attempt=attempt,
                             reserved_usd=str(bound))
        (self.root/f'response-{attempt}.json').write_text(json.dumps(self.observed,ensure_ascii=False,indent=2),encoding='utf-8')
        return io.BytesIO(raw)


def test_live_summary_application_and_retained_get(assistant):
    state,record,service,headers,body,path = assistant
    # Explicit file parsing, not inherited env (offline runner disables providers).
    from dotenv import dotenv_values
    values = dotenv_values(Path(__file__).resolve().parents[2]/'.env')
    from pydantic import SecretStr
    from app.application.contracts.plan_summary import SummaryProfile
    assert values.get('SUMMARY_LLM_ENABLED','').lower() == 'true'
    profile = SummaryProfile(enabled=True,model=values.get('SUMMARY_MODEL') or 'UNCONFIGURED',
        providers=tuple(json.loads(values.get('SUMMARY_PROVIDERS') or '[]')),
        max_tokens=int(values.get('SUMMARY_MAX_TOKENS') or 256),
        input_bytes=int(values.get('SUMMARY_INPUT_BYTES') or 16000))
    assert profile.max_tokens <= 256 and profile.input_bytes <= 16000
    root = Path('runtime/assistant-test/live-smoke')
    transport = CappedTransport(root,profile.model)
    service.profile = profile
    service.provider = OpenRouterSummaryProvider(SecretStr(values['OPENROUTER_API_KEY']),opener=transport)
    values.clear()
    response = state[5].post(path,headers=headers,json=body)
    assert response.status_code == 200, response.text
    result = response.json()['data']
    SummaryAnswer.model_validate(result['result'])
    assert transport.calls == 1
    final = {'raw':transport.observed,'final':result['result']}
    (root/f"final-{transport.observed['attempt']}.json").write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
    assert state[5].get(path+'/'+result['generation_id']).json()['data'] == result
    assert state[5].post(path,headers=headers,json=body).json()['data'] == result
    assert transport.calls == 1
    # Verify fallback through the same real path, using an offline failing transport.
    from uuid import uuid4
    class Down:
        def open(self,*args,**kwargs): raise TimeoutError()
    service.provider = OpenRouterSummaryProvider(SecretStr('synthetic'),opener=Down())
    fallback = state[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},
                            json={**body,'locale':'en'})
    assert fallback.status_code == 200
    assert fallback.json()['data']['result']['source'] == 'deterministic_fallback'
    assert fallback.json()['data']['result']['diagnostics']['reason'] == 'PROVIDER_UNAVAILABLE'
    assert result['result']['source'] == 'model_presentation', result['result']['diagnostics']
