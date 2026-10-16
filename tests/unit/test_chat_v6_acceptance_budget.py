import json
from decimal import Decimal
import pytest
from scripts import conversational_v6_acceptance as batch


def test_new_group_caps_and_old_groups_untouched(tmp_path):
    old=tmp_path/'conversational-l32-live';old.mkdir()
    artifact=old/'attempt-30.json';artifact.write_bytes(b'old immutable evidence')
    for n in range(1,17):assert batch.reserve(tmp_path,{'case':'OFFLINE_FAKE'})==n
    with pytest.raises(ValueError,match='cap exhausted'):batch.reserve(tmp_path,{})
    rows,total=batch.reservations(tmp_path)
    assert len(rows)==16 and total==Decimal('0.2249472') and artifact.read_bytes()==b'old immutable evidence'


def test_crash_lock_429_and_cost_fences(tmp_path,monkeypatch):
    root=tmp_path/batch.GROUP;root.mkdir()
    lock=root/'reservation.lock';lock.write_text('uncertain')
    with pytest.raises(FileExistsError):batch.reserve(tmp_path,{})
    assert lock.read_text()=='uncertain';lock.unlink()  # isolated fake fixture only
    (root/'STOP-429.json').write_text('{}')
    with pytest.raises(ValueError,match='HTTP429'):batch.reserve(tmp_path,{})
    (root/'STOP-429.json').unlink()
    monkeypatch.setattr(batch,'MAX_USD',batch.BOUND-Decimal('.0000001'))
    with pytest.raises(ValueError,match='cap exhausted'):batch.reserve(tmp_path,{})
    assert not list(root.glob('attempt-*'))


def test_cli_requires_separate_optin(monkeypatch):
    calls=[];monkeypatch.setattr(batch.subprocess,'call',lambda *a,**k:calls.append((a,k)) or 0)
    monkeypatch.setattr(batch.sys,'argv',['runner'])
    with pytest.raises(SystemExit) as e:batch.main()
    assert e.value.code==2 and not calls
    monkeypatch.setattr(batch.sys,'argv',['runner',batch.OPT_IN,'--case','conversation'])
    with pytest.raises(SystemExit) as e:batch.main()
    assert e.value.code==0 and calls[0][1]['env']['SHELFCASH_CHAT_V6_ACCEPTANCE']==batch.GROUP
