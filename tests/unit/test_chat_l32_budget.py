import json
from decimal import Decimal
import pytest
from scripts.conversational_shared_ledger import reserve,reservations,BOUND


def test_shared_cap_counts_existing_other_batch_and_unknown_calls(tmp_path):
    old=tmp_path/'conversational-l31-live';old.mkdir()
    for n in range(1,7):
        (old/f'attempt-{n}.json').write_text(json.dumps({'attempt':n,'reserved_usd':str(BOUND)}))
    for n in range(7,31):assert reserve(tmp_path,dict(case='OFFLINE_FAKE'))==n
    with pytest.raises(ValueError,match='cap exhausted'):reserve(tmp_path,{})
    rows,total=reservations(tmp_path)
    assert len(rows)==30 and total==BOUND*30
    assert all('usage' not in r for r in rows)


def test_shared_cost_cap_and_abandoned_lock_fail_closed(tmp_path):
    old=tmp_path/'conversational-l31-live';old.mkdir()
    (old/'attempt-1.json').write_text(json.dumps({'reserved_usd':'.999'}))
    with pytest.raises(ValueError,match='cap exhausted'):reserve(tmp_path,{})
    lock=tmp_path/'conversational-l32-live/reservation.lock';lock.write_text('uncertain')
    with pytest.raises(FileExistsError):reserve(tmp_path,{})
    assert lock.read_text()=='uncertain'


def test_cli_requires_explicit_optin_and_offline_freeze_does_not_launch_tests(monkeypatch):
    import scripts.conversational_l32_live as cli
    calls=[]
    monkeypatch.setattr(cli.subprocess,'call',lambda *a,**k:calls.append((a,k)) or 0)
    monkeypatch.setattr(cli.sys,'argv',['runner'])
    with pytest.raises(SystemExit) as error:cli.main()
    assert error.value.code==2 and not calls
    monkeypatch.setattr(cli,'freeze_source',lambda:'OFFLINE_SYNTHETIC_HASH')
    monkeypatch.setattr(cli.sys,'argv',['runner','--freeze-source']);cli.main()
    assert not calls
    monkeypatch.setattr(cli.sys,'argv',['runner','--allow-paid-shared-l31-l32-max-30-usd-1.00','--case','budget'])
    with pytest.raises(SystemExit) as error:cli.main()
    assert error.value.code==0 and len(calls)==1
    assert calls[0][1]['env']['SHELFCASH_CHAT_L32_LIVE']=='shared-l31-l32-30-usd-1.00'


@pytest.mark.parametrize('stage',['preflight','completion'])
def test_429_stops_batch_without_retry_and_unknown_completion_keeps_slot(tmp_path,monkeypatch,stage):
    from urllib.request import Request
    from urllib.error import HTTPError
    import tests.live.test_chat_l32_live as live
    monkeypatch.setattr(live,'BASE',tmp_path);monkeypatch.setattr(live,'ROOT',tmp_path/'conversational-l32-live')
    monkeypatch.setattr(live,'fingerprint',lambda:'OFFLINE_FAKE')
    transport=live.Transport('offline','OFFLINE_FAKE');transport.model='synthetic'
    class Offline429:
        def open(self,*a,**k):raise HTTPError('https://example.invalid',429,'synthetic',None,None)
    transport.opener=Offline429()
    body=dict(model='synthetic',max_tokens=1200,reasoning={'enabled':False},provider=dict(allow_fallbacks=False,require_parameters=True,
        max_price=dict(prompt='.3',completion='2.5',request=0)))
    req=Request('https://example.invalid',data=json.dumps(body).encode() if stage=='completion' else None)
    with pytest.raises(HTTPError):transport.open(req,1)
    assert transport.rate_limited
    with pytest.raises(AssertionError,match='stops batch'):transport.open(req,1)
    rows,total=reservations(tmp_path)
    assert len(rows)==(1 if stage=='completion' else 0)
    if stage=='completion':
        raw=json.loads((live.ROOT/'raw-1.json').read_text(encoding='utf8'))
        assert raw['http_status']==429 and 'usage' not in raw and total==BOUND


def test_old_live_caller_is_retired_before_any_network_or_reservation():
    from tests.live.test_chat_l31_live import LedgerTransport,ROOT
    from urllib.request import Request
    transport=LedgerTransport(ROOT,'offline-retirement','synthetic')
    with pytest.raises(AssertionError,match='retired'):transport.open(Request('https://example.invalid'),1)
    assert transport.attempts==[]
