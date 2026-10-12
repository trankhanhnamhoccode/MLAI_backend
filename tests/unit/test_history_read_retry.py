"""Only rolled-back PostgreSQL serialization reads are retried, with a bound."""
from types import SimpleNamespace
import pytest
from sqlalchemy.exc import OperationalError
from app.application.use_cases.import_history import ImportHistoryReads


def failure(code):
    class DatabaseFailure(Exception):
        sqlstate=code
    return OperationalError('synthetic safe query',{},DatabaseFailure())


def reader():
    return ImportHistoryReads(SimpleNamespace(auth=None,engine=None))


def test_serialization_retries_whole_read_and_rechecks_authority(monkeypatch):
    value=reader();calls=[]
    def attempt(*args):
        calls.append(1)
        if len(calls)<3:raise failure('40001')
        return 'fresh authorized snapshot'
    monkeypatch.setattr(value,'_read_once',attempt)
    assert value._read(*([None]*8))=='fresh authorized snapshot'
    assert len(calls)==3


@pytest.mark.parametrize('code,expected',[('40001',5),('08006',1),('42P01',1)])
def test_exhaustion_other_connection_and_schema_failures_propagate(monkeypatch,code,expected):
    value=reader();calls=[]
    def attempt(*args):calls.append(1);raise failure(code)
    monkeypatch.setattr(value,'_read_once',attempt)
    with pytest.raises(OperationalError):value._read(*([None]*8))
    assert len(calls)==expected
