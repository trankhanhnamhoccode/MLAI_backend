from decimal import Decimal
import pytest
from scripts import conversational_l4_live as batch


def test_l4_separate_caps_unknown_and_fail_closed(tmp_path):
    old=tmp_path/'L32-V6-acceptance-1';old.mkdir();artifact=old/'attempt-11.json';artifact.write_bytes(b'original')
    for n in range(1,25):assert batch.reserve(tmp_path,{'case':'OFFLINE_FAKE'})==n
    with pytest.raises(ValueError,match='cap exhausted'):batch.reserve(tmp_path,{})
    rows,total=batch.reservations(tmp_path)
    assert len(rows)==24 and total==Decimal('0.3374208') and artifact.read_bytes()==b'original'
    lock=tmp_path/batch.GROUP/'reservation.lock';lock.write_text('uncertain')
    with pytest.raises(FileExistsError):batch.reserve(tmp_path,{})
    assert lock.read_text()=='uncertain'


def test_l4_price_and_429_guards(tmp_path,monkeypatch):
    monkeypatch.setattr(batch,'MAX_USD',batch.BOUND-Decimal('.0000001'))
    with pytest.raises(ValueError,match='cap exhausted'):batch.reserve(tmp_path,{})
    (tmp_path/batch.GROUP/'STOP-429.json').write_text('{}')
    with pytest.raises(ValueError,match='429'):batch.reserve(tmp_path,{})


def test_l4_cli_requires_own_optin(monkeypatch):
    calls=[];monkeypatch.setattr(batch.subprocess,'call',lambda *a,**k:calls.append((a,k)) or 0)
    monkeypatch.setattr(batch.sys,'argv',['runner','--phase','baseline'])
    with pytest.raises(SystemExit) as e:batch.main()
    assert e.value.code==2 and not calls
    monkeypatch.setattr(batch.sys,'argv',['runner','--phase','baseline',batch.OPT_IN])
    with pytest.raises(SystemExit) as e:batch.main()
    assert e.value.code==0 and calls[0][1]['env']['SHELFCASH_CHAT_L4_LIVE']=='baseline'
