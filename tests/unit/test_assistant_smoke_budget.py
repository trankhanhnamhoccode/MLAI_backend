"""Budget exhaustion and request guard fail closed with fake metadata/network."""
import io
import json
from urllib.request import Request
import pytest
from tests.live.test_assistant_smoke import CappedTransport


def test_three_reserved_attempts_prevent_a_fourth_call(tmp_path,monkeypatch):
    import tests.live.test_assistant_smoke as smoke
    metadata={'data':{'endpoints':[{'supported_parameters':['temperature','max_tokens','response_format','structured_outputs'],
                                  'pricing':{'prompt':'0.0000003','completion':'0.0000025'}}]}}
    monkeypatch.setattr(smoke,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(metadata).encode()))
    calls=[]
    class Down:
        def open(self,*args,**kwargs):calls.append(1);raise TimeoutError('uncertain completion')
    monkeypatch.setattr(smoke,'build_opener',lambda *args:Down())
    transport=CappedTransport(tmp_path,'google/gemini-2.5-flash')
    def request():return Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(dict(
        model='google/gemini-2.5-flash',max_tokens=256,provider={'allow_fallbacks':False})).encode())
    for _ in range(3):
        with pytest.raises(TimeoutError):transport.open(request(),20)
    with pytest.raises(AssertionError,match='Three completion attempts'):transport.open(request(),20)
    assert len(calls)==3 and len(list(tmp_path.glob('attempt-*.json')))==3


@pytest.mark.parametrize('change',[{'model':'other/model'},{'max_tokens':257},{'provider':{'allow_fallbacks':True}}])
def test_unapproved_model_token_or_route_is_rejected_before_metadata(tmp_path,monkeypatch,change):
    def forbidden(*a,**k):raise AssertionError('Network must not be called')
    import tests.live.test_assistant_smoke as smoke
    monkeypatch.setattr(smoke,'urlopen',forbidden)
    transport=CappedTransport(tmp_path,'google/gemini-2.5-flash')
    body={**dict(model='google/gemini-2.5-flash',max_tokens=256,provider={'allow_fallbacks':False}),**change}
    with pytest.raises(AssertionError):transport.open(Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(body).encode()),20)
    assert transport.calls==0 and not list(tmp_path.glob('attempt-*.json'))
