"""No network: 30 durable reservations and uncertain billing stay consumed."""
import io,json
from urllib.request import Request
from decimal import Decimal
import pytest
from tests.live.test_chat_l31_live import LedgerTransport,BOUND


def body():return dict(model='google/gemini-2.5-flash',max_tokens=1200,reasoning={'enabled':False},
    provider=dict(allow_fallbacks=False,require_parameters=True,max_price=dict(prompt='.3',completion='2.5',request=0)))


def test_ledger_30_attempt_cap_and_unknown_transport_consumes_reservation(tmp_path):
    transport=LedgerTransport(tmp_path,'offline-budget','synthetic-version')
    transport.preflights=[{'data':{'id':'synthetic-metadata'}}]
    class Offline:
        def open(self,*args,**kwargs):raise TimeoutError('synthetic unknown outcome')
    transport.opener=Offline()
    request=Request('https://example.invalid',data=json.dumps(body()).encode())
    for i in range(30):
        with pytest.raises(TimeoutError):transport.open(request,timeout=1)
    with pytest.raises(AssertionError,match='exhausted'):transport.open(request,timeout=1)
    assert len(list(tmp_path.glob('attempt-*.json')))==30
    assert len(list(tmp_path.glob('raw-*.json')))==30
    assert BOUND*30==Decimal('.4217760')
    raw=json.loads((tmp_path/'raw-1.json').read_text(encoding='utf8'))
    assert raw['outcome']=='TRANSPORT_UNKNOWN' and 'usage' not in raw
