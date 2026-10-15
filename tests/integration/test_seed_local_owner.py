"""Synthetic local tooling uses real application transactions on the test DB only."""
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contracts.auth import AuthError, LoginRequest
from app.application.use_cases.auth import AuthUseCases
from app.domain.permissions import PERMISSIONS
from app.infrastructure.database.engine import create_database_engine
from app.models import Ingredient, Product, Store, StoreMembership, User
from app.models.auth import AuthAccount, AuthAudit, AuthSession
from scripts.seed_local_owner import seed_owner


def test_interrupted_setup_resumes_without_duplicate_store(database_settings, tmp_path, monkeypatch):
    engine = create_database_engine(database_settings)
    path = tmp_path / "test-owner.json"
    complete = AuthUseCases.complete
    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic interruption before completion")
    try:
        monkeypatch.setattr(AuthUseCases, "complete", interrupted)
        with pytest.raises(RuntimeError):
            seed_owner(engine, database_settings, path)
        original = path.read_bytes()
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(Store)) == 1
            assert not fresh.scalar(select(AuthAccount)).credential_ready
        monkeypatch.setattr(AuthUseCases, "complete", complete)
        receipt = seed_owner(engine, database_settings, path)
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(Store)) == 1
            assert fresh.get(AuthAccount, receipt.user_id).credential_ready
        assert path.read_bytes() == original
    finally:
        engine.dispose()


def test_local_owner_replay_recovery_and_current_authority(database_settings, tmp_path):
    engine = create_database_engine(database_settings)
    path = tmp_path / "test-owner.json"
    try:
        first = seed_owner(engine, database_settings, path)
        original = path.read_bytes()
        assert seed_owner(engine, database_settings, path) == first
        assert path.read_bytes() == original
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(User)) == 1
            assert fresh.scalar(select(func.count()).select_from(Store)) == 1
            assert fresh.scalar(select(func.count()).select_from(StoreMembership)) == 1
            assert fresh.scalar(select(func.count()).select_from(Product)) == 0
            assert fresh.scalar(select(func.count()).select_from(Ingredient)) == 0
            account = fresh.get(AuthAccount, first.user_id)
            assert account.credential_ready and account.verified_at
            revision = account.credential_revision
            assert fresh.get(AuthAudit, first.audit_id).kind == "STORE_PROVISIONED"
            assert all(row.revoked_at for row in fresh.scalars(select(AuthSession)))
        auth = AuthUseCases(engine)
        context, token = auth.login(LoginRequest(**json.loads(path.read_text())), "test-owner")
        try:
            assert context.default_store_id == first.store_id
            assert set(auth.store_context(token, first.store_id).membership.effective_permissions) == set(PERMISSIONS)
        finally:
            auth.logout(token, context.session.csrf_token)
        # Revocation must survive replay, with no reset or implicit reactivation.
        with Session(engine) as session:
            session.scalar(select(StoreMembership)).active = False
            session.commit()
        with pytest.raises(AuthError):
            seed_owner(engine, database_settings, path)
        with Session(engine) as fresh:
            assert not fresh.scalar(select(StoreMembership)).active
            assert fresh.get(AuthAccount, first.user_id).credential_revision == revision
        assert path.read_bytes() == original
    finally:
        engine.dispose()
