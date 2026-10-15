"""Opt-in harness caps count uncertain requests and never records credentials."""
import io,json
from urllib.request import Request
from urllib.error import HTTPError
import pytest
from tests.live.test_conversational_smoke import BudgetTransport


def request():
    return Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(dict(model='google/gemini-2.5-flash',
        temperature=0,max_tokens=768,reasoning={'enabled':False},provider=dict(allow_fallbacks=False,require_parameters=True,
            max_price=dict(prompt='0.3',completion='2.5',request=0)))).encode(),headers={'Authorization':'Bearer synthetic-only'})


def test_eight_full_plus_two_small_uncertain_requests_exhaust_authorized_ten(tmp_path):
    class Down:
        calls=0
        def open(self,*a,**k):self.calls+=1;raise TimeoutError()
    transport=BudgetTransport(tmp_path,'offline','google/gemini-2.5-flash');transport.opener=Down()
    for _ in range(8):
        with pytest.raises(TimeoutError):transport.open(request(),20)
    with pytest.raises(AssertionError,match='smaller input/output'):transport.open(request(),20)
    assert transport.opener.calls==8
    for _ in range(2):
        small=request();data=json.loads(small.data);data['max_tokens']=128;small.data=json.dumps(data).encode()
        with pytest.raises(TimeoutError):transport.open(small,20)
    with pytest.raises(AssertionError,match='Ten reservations'):transport.open(request(),20)
    assert transport.opener.calls==10 and len(list(tmp_path.glob('attempt-*.json')))==10


def test_http_error_is_recorded_with_secret_removed(tmp_path):
    class Rejected:
        def open(self,*args,**kwargs):raise HTTPError('https://openrouter.ai/api/v1/chat/completions',400,'rejected',{},
            io.BytesIO(json.dumps({'error':{'code':400,'message':'Invalid request synthetic-only'}}).encode()))
    transport=BudgetTransport(tmp_path,'offline','google/gemini-2.5-flash');transport.opener=Rejected()
    with pytest.raises(HTTPError):transport.open(request(),20)
    raw=(tmp_path/'raw-1.json').read_text(encoding='utf8')
    assert 'synthetic-only' not in raw and '[REDACTED]' in raw and transport.raw['http_status']==400
