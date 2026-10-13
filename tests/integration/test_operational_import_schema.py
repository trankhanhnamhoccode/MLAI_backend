"""Additive S4.6 migration roundtrip and database evidence invariants."""
from sqlalchemy.engine import make_url
from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.infrastructure.database.engine import create_database_engine
from app.models import Ingredient, Store, Supplier, SupplierTerm
from app.models.operational_import import ScopeDeclarationRecord, TermSourceRecord, InventoryThreshold
from scripts.dev import migration_config
from tests.integration.test_auth_public import env, setup, provision

TABLES={"supplier_source_records","term_source_records","payable_fee_records","scope_declaration_records", "inventory_receipt_records","inventory_thresholds","stock_request_receipts","inventory_audit"}

def test_additive_migration_roundtrip_preserves_prior_tables_and_matches_model_columns(database_settings):
    engine=create_database_engine(database_settings)
    try:
        schedule={'email_verification_tokens', 'email_verification_deliveries', 'password_reset_deliveries', 'import_history_records','notification_intents','notifications','notification_read_receipts', 'planning_exports', 'recipe_schedule_changes', 'saved_requirements', 'model_serving_configurations', 'recipe_schedule_request_receipts', 'planning_configuration_events', 'forecast_serving_identities', 'planning_configuration_receipts', 'planning_configuration_revisions', 'planning_budgets', 'planning_defaults'}
        before=set(inspect(engine).get_table_names())-TABLES-schedule
        command.downgrade(migration_config(),"0013_import_staging")
        assert set(inspect(engine).get_table_names())==before
        command.upgrade(migration_config(),"head")
        inspector=inspect(engine)
        assert set(inspector.get_table_names())==before|TABLES|schedule
        from app.infrastructure.database.base import Base
        for table in TABLES:
            actual={c["name"]:c for c in inspector.get_columns(table)}
            assert set(actual)==set(Base.metadata.tables[table].columns.keys())
            for c in Base.metadata.tables[table].columns:assert actual[c.name]["nullable"]==c.nullable
        with engine.connect() as c:assert c.scalar(text("SELECT current_database()")) == make_url(database_settings.database_url).database
    finally:engine.dispose()

def test_immutable_declaration_and_scoped_threshold_database_constraints(env):
    owner=setup(env);other=provision(env,"other-schema@example.test")
    ingredient=uuid4();declaration=uuid4()
    with Session(env[1]) as s:
        s.add(Ingredient(id=ingredient,store_id=owner.store_id,name="Scoped ingredient",base_unit="l",expiry_tracking=False,active=True))
        from hashlib import sha256
        s.add(ScopeDeclarationRecord(id=declaration,store_id=owner.store_id,source_system_key="S",source_record_key="D",source_record_hash=sha256(b"D").hexdigest(),version=1,
            payload=dict(domain="scope_declarations",source_declaration_key="D",declaration=dict(kind="INVENTORY",ingredient_id=str(ingredient),state="UNKNOWN")),
            dependency_digest="synthetic-evidence-digest",provenance={}));s.commit()
        with pytest.raises(IntegrityError) as error:
            s.get(ScopeDeclarationRecord,declaration).payload={"changed":True};s.commit()
        assert error.value.orig.sqlstate=="23514";s.rollback()
        with pytest.raises(IntegrityError) as error:
            s.add(InventoryThreshold(store_id=other.store_id,ingredient_id=ingredient,minimum_usable_quantity=0,unit="l",version="v1",updated_at=env[4][0],updated_by=owner.user_id));s.commit()
        assert error.value.orig.sqlstate=="23503";s.rollback()
    with Session(env[1]) as fresh:
        assert fresh.get(ScopeDeclarationRecord,declaration).payload.get("changed") is None
        assert fresh.scalar(select(InventoryThreshold)) is None

def test_unicode_source_identity_at_current_typed_model_limit_does_not_exceed_postgres_index_limit(env):
    from app.application.use_cases.operational_configuration import OperationalConfiguration
    from app.application.contracts.import_domains import SupplierSource,FeeSource,DeclarationSource
    from app.models.operational_import import SupplierSourceRecord,PayableFeeRecord
    owner=setup(env);source_key="供"*1000;ident=uuid4()
    with Session(env[1]) as s:
        writer=OperationalConfiguration(s,owner.store_id)
        supplier=SupplierSource(source_supplier_key=source_key,name="Synthetic supplier",active=True)
        writer.supplier(supplier,ident,"SOURCE",{},create=True)
        writer.supplier(supplier,ident,"SOURCE",{},create=False)
        writer.fee(FeeSource(source_fee_key=source_key,scope="STORE_PROCUREMENT",effective_from="2026-10-10",effective_to=None,
            mode="NONE",coverage="COMPLETE",currency="VND",components=(),covered_source_term_keys=(),covered_source_supplier_keys=(),
            evidence_reference="Explicit empty offer scope",reason="Explicit none"),uuid4(),"SOURCE",{},dict(terms=[],suppliers=[],bindings=[]))
        s.commit()
    with Session(env[1]) as s:
        assert s.scalar(select(SupplierSourceRecord)).source_record_key==source_key
        assert s.scalar(select(PayableFeeRecord)).payload["source_fee_key"]==source_key
