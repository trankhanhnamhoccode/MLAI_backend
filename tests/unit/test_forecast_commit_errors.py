"""S2.3 corrective exception semantics; no DB/network connection required."""
import psycopg
import pytest
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError, ProgrammingError

import app.application.use_cases.forecast_execution as execution


@pytest.mark.parametrize('error,uncertain', [
    (ValueError('programming'), False),
    (RuntimeError('connection lost is merely a message'), False),
    (OperationalError(None, None, psycopg.OperationalError('generic')), False),
    (OperationalError(None, None, psycopg.OperationalError('transport'), connection_invalidated=True), True),
    (InterfaceError(None, None, psycopg.InterfaceError('transport'), connection_invalidated=True), True),
    (DBAPIError(None, None, psycopg.OperationalError('generic'), connection_invalidated=True), False),
    (OperationalError(None, None, ValueError('not a psycopg transport error'), connection_invalidated=True), False),
    (OperationalError(None, None, psycopg.errors.ConnectionFailure()), True),
    (OperationalError(None, None, psycopg.errors.TransactionResolutionUnknown()), True),
    (OperationalError(None, None, psycopg.errors.StatementCompletionUnknown()), True),
    (OperationalError(None, None, psycopg.errors.SerializationFailure(), connection_invalidated=True), False),
    (OperationalError(None, None, psycopg.errors.DeadlockDetected()), False),
    (OperationalError(None, None, psycopg.errors.SqlclientUnableToEstablishSqlconnection(), connection_invalidated=True), False),
    (IntegrityError(None, None, psycopg.errors.UniqueViolation(), connection_invalidated=True), False),
    (ProgrammingError(None, None, psycopg.errors.SyntaxError(), connection_invalidated=True), False),
    (psycopg.OperationalError('unwrapped/unsupported'), False),
])
def test_commit_classifier(error, uncertain):
    assert execution._is_uncertain_commit(error) is uncertain


def test_real_after_commit_callback_preserves_primary_and_cleanup(caplog):
    primary = ValueError('programming callback')
    with pytest.raises(ValueError) as caught:
        with execution._execution_session(None) as session:
            session.begin()
            def broken(_session):
                raise primary
            event.listen(session, 'after_commit', broken)
            execution._commit(session)
    assert caught.value is primary
    assert any('rollback' in note and 'InvalidRequestError' in note for note in primary.__notes__)
    assert 'rollback' in caplog.text


def test_cleanup_invalidation_failure_is_recorded_without_masking(monkeypatch, caplog):
    from sqlalchemy.orm import Session
    primary = ValueError('execution error')
    real_close = Session.close
    def broken(*_args):
        raise RuntimeError('cleanup failure')
    def close(session):
        real_close(session)
        raise RuntimeError('close failure')
    monkeypatch.setattr(Session, 'rollback', broken)
    monkeypatch.setattr(Session, 'invalidate', broken)
    monkeypatch.setattr(Session, 'close', close)
    with pytest.raises(ValueError) as caught:
        with execution._execution_session(None):
            raise primary
    assert caught.value is primary
    assert any('invalidation after rollback' in n for n in primary.__notes__)
    assert any('invalidation after close' in n for n in primary.__notes__)
    assert 'invalidation after rollback' in caplog.text and 'invalidation after close' in caplog.text
