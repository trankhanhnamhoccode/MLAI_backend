"""Real PostgreSQL schema integrity and fresh-session persistence for S1.1."""
from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID, uuid4

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine


@pytest.fixture
def engine(database_settings: Settings) -> Iterator[Engine]:
    instance = create_database_engine(database_settings)
    try:
        yield instance
    finally:
        instance.dispose()


def create_parents(engine: Engine) -> tuple[UUID, UUID]:
    from app.models import Store, User
    with Session(engine) as session:
        user = User(email="owner@example.test", password_hash="opaque-test-hash", display_name="Owner")
        store = Store(name="Demo Cafe")
        session.add_all([user, store])
        session.flush()
        identifiers = user.id, store.id
        session.commit()
    return identifiers


def test_schema_exact_tables_constraints_indexes_and_metadata(engine: Engine) -> None:
    import app.models
    from app.infrastructure.database.base import Base

    inspector = inspect(engine)
    assert sorted(inspector.get_table_names(schema="public")) == [
        "alembic_version", "store_memberships", "stores", "users",
    ]
    assert set(Base.metadata.tables) == {"users", "stores", "store_memberships"}
    for table in Base.metadata.tables:
        assert inspector.get_pk_constraint(table)["constrained_columns"] == ["id"]
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert not any(column["nullable"] for column in columns.values())
        assert columns["created_at"]["type"].timezone
        assert columns["updated_at"]["type"].timezone
    assert [item["column_names"] for item in inspector.get_unique_constraints("users")] == [["email"]]
    assert inspector.get_unique_constraints("stores") == []
    assert [item["column_names"] for item in inspector.get_unique_constraints("store_memberships")] == [["store_id", "user_id"]]
    foreign_keys = inspector.get_foreign_keys("store_memberships")
    assert {(item["constrained_columns"][0], item["referred_table"]) for item in foreign_keys} == {
        ("user_id", "users"), ("store_id", "stores"),
    }
    explicit_indexes = [index for index in inspector.get_indexes("store_memberships") if not index.get("duplicates_constraint")]
    assert [(index["name"], index["column_names"]) for index in explicit_indexes] == [
        ("ix_store_memberships_user_id", ["user_id"]),
    ]
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) == "shelfcash_test"
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == "0002_identity_store"
        assert compare_metadata(MigrationContext.configure(connection, opts={"compare_server_default": True}), Base.metadata) == []


def test_user_commit_close_and_reload(engine: Engine) -> None:
    from app.models import User
    identifier = UUID("10000000-0000-0000-0000-000000000001")
    with Session(engine) as session:
        session.add(User(id=identifier, email="owner@example.test", password_hash="opaque-test-hash", display_name="Owner", active=False))
        session.commit()
    with Session(engine) as fresh:
        user = fresh.get(User, identifier)
        assert user is not None
        assert (user.email, user.password_hash, user.display_name, user.active) == (
            "owner@example.test", "opaque-test-hash", "Owner", False,
        )
        assert user.created_at.utcoffset() == timedelta(0)
        assert user.updated_at == user.created_at


def test_store_persistence_defaults_and_nonunique_name(engine: Engine) -> None:
    from app.models import Store
    with Session(engine) as session:
        first, second = Store(name="Same Cafe"), Store(name="Same Cafe")
        session.add_all([first, second])
        session.flush()
        identifiers = first.id, second.id
        session.commit()
    with Session(engine) as fresh:
        for identifier in identifiers:
            store = fresh.get(Store, identifier)
            assert store is not None
            assert (store.name, store.timezone, store.currency, store.active) == (
                "Same Cafe", "Asia/Ho_Chi_Minh", "VND", True,
            )
            assert isinstance(store.id, UUID) and store.id.version == 4
            assert store.created_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("role", ["OWNER", "STAFF"])
def test_membership_persists_existing_references(engine: Engine, role: str) -> None:
    from app.models import StoreMembership
    user_id, store_id = create_parents(engine)
    with Session(engine) as session:
        member = StoreMembership(user_id=user_id, store_id=store_id, role=role)
        session.add(member)
        session.flush()
        identifier = member.id
        session.commit()
    with Session(engine) as fresh:
        member = fresh.get(StoreMembership, identifier)
        assert member is not None
        assert (member.user_id, member.store_id, member.role) == (user_id, store_id, role)
        assert member.user.id == user_id and member.store.id == store_id
        assert member.active and member.delegated_permissions == []
        assert member.created_at.utcoffset() == timedelta(0)


def test_duplicate_canonical_email_rejected_by_database(engine: Engine) -> None:
    from app.models import User
    create_parents(engine)
    with Session(engine) as session, pytest.raises(IntegrityError) as failure:
        session.add(User(email="owner@example.test", password_hash="another-opaque-hash", display_name="Other"))
        session.commit()
    assert failure.value.orig.diag.constraint_name == "uq_users_email"


@pytest.mark.parametrize("email", ["Owner@example.test", " owner@example.test ", "owner@example.test\t"])
def test_noncanonical_email_rejected_without_silent_normalization(engine: Engine, email: str) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError) as failure:
        connection.execute(text("INSERT INTO users (email, password_hash, display_name) VALUES (:email, 'opaque-test-hash', 'Owner')"), {"email": email})
    assert failure.value.orig.diag.constraint_name == "ck_users_email_canonical"


def test_duplicate_store_user_pair_rejected(engine: Engine) -> None:
    from app.models import StoreMembership
    user_id, store_id = create_parents(engine)
    with Session(engine) as session:
        session.add(StoreMembership(user_id=user_id, store_id=store_id, role="OWNER"))
        session.commit()
    with Session(engine) as session, pytest.raises(IntegrityError) as failure:
        session.add(StoreMembership(user_id=user_id, store_id=store_id, role="STAFF"))
        session.commit()
    assert failure.value.orig.diag.constraint_name == "uq_store_memberships_store_user"


@pytest.mark.parametrize("role", ["ADMIN", "owner"])
def test_invalid_role_rejected_by_postgresql(engine: Engine, role: str) -> None:
    user_id, store_id = create_parents(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError) as failure:
        connection.execute(text("INSERT INTO store_memberships (user_id, store_id, role) VALUES (:user, :store, :role)"), {"user": user_id, "store": store_id, "role": role})
    assert failure.value.orig.diag.constraint_name == "ck_store_memberships_role"


@pytest.mark.parametrize("missing", ["user", "store"])
def test_missing_membership_parent_rejected(engine: Engine, missing: str) -> None:
    user_id, store_id = create_parents(engine)
    if missing == "user":
        user_id = uuid4()
    else:
        store_id = uuid4()
    with engine.begin() as connection, pytest.raises(IntegrityError) as failure:
        connection.execute(text("INSERT INTO store_memberships (user_id, store_id, role) VALUES (:user, :store, 'OWNER')"), {"user": user_id, "store": store_id})
    assert failure.value.orig.diag.constraint_name == f"fk_store_memberships_{missing}"


@pytest.mark.parametrize("permissions", ['["CHANGE_BUDGET"]', '{}'])
def test_unaccepted_permissions_rejected(engine: Engine, permissions: str) -> None:
    user_id, store_id = create_parents(engine)
    with engine.begin() as connection, pytest.raises(IntegrityError) as failure:
        connection.execute(text("INSERT INTO store_memberships (user_id, store_id, role, delegated_permissions) VALUES (:user, :store, 'OWNER', CAST(:permissions AS jsonb))"), {"user": user_id, "store": store_id, "permissions": permissions})
    assert failure.value.orig.diag.constraint_name == "ck_store_memberships_permissions_reserved"


@pytest.mark.parametrize("parent", ["users", "stores"])
def test_membership_restricts_parent_deletion(engine: Engine, parent: str) -> None:
    from app.models import StoreMembership
    user_id, store_id = create_parents(engine)
    with Session(engine) as session:
        session.add(StoreMembership(user_id=user_id, store_id=store_id, role="OWNER"))
        session.commit()
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text(f"DELETE FROM {parent} WHERE id = :identifier"), {"identifier": user_id if parent == "users" else store_id})


def test_utc_timestamps_and_orm_update_semantics(engine: Engine) -> None:
    from app.models import Store, StoreMembership, User
    user_id, store_id = create_parents(engine)
    with Session(engine) as session:
        member = StoreMembership(user_id=user_id, store_id=store_id, role="OWNER")
        session.add(member)
        session.flush()
        member_id = member.id
        session.commit()
    identifiers = [(User, user_id), (Store, store_id), (StoreMembership, member_id)]
    with Session(engine) as fresh:
        originals = {model: (fresh.get(model, identifier).created_at, fresh.get(model, identifier).updated_at) for model, identifier in identifiers}
    with Session(engine) as session:
        for model, identifier in identifiers:
            session.get(model, identifier).active = False
        session.commit()
    with Session(engine) as fresh:
        assert fresh.scalar(text("SHOW TIME ZONE")) == "UTC"
        for model, identifier in identifiers:
            row = fresh.get(model, identifier)
            assert row.created_at == originals[model][0]
            assert row.updated_at > originals[model][1]
            assert row.updated_at.utcoffset() == timedelta(0)


def test_raw_sql_insert_uses_database_defaults(engine: Engine) -> None:
    with engine.begin() as connection:
        identifier = connection.scalar(text("INSERT INTO users (email, password_hash, display_name) VALUES ('sql@example.test', 'opaque-test-hash', 'SQL User') RETURNING id"))
    with engine.connect() as fresh:
        row = fresh.execute(text("SELECT id, active, created_at, updated_at FROM users WHERE id = :identifier"), {"identifier": identifier}).one()
        assert isinstance(row.id, UUID) and row.id.version == 4
        assert row.active and row.created_at.utcoffset() == timedelta(0)
        assert row.updated_at == row.created_at


@pytest.mark.parametrize("currency", ["vnd", "VN"])
def test_currency_storage_shape_rejected(engine: Engine, currency: str) -> None:
    with engine.begin() as connection, pytest.raises(IntegrityError) as failure:
        connection.execute(text("INSERT INTO stores (name, currency) VALUES ('Cafe', :currency)"), {"currency": currency})
    assert failure.value.orig.diag.constraint_name == "ck_stores_currency_shape"
