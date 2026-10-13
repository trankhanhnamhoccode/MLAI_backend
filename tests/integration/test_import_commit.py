"""S4.5 real PostgreSQL + HTTP, synthetic evidence, no live provider."""
from uuid import UUID, uuid4
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, analyzed, approved, previewed, post, sales_bytes, csv_source
from tests.integration.test_import_classification import confirm
from app.models import SalesDaily, Product
from app.models.import_staging import ImportAudit, ImportJob


@pytest.fixture(autouse=True)
def no_live_provider(imp):
    imp[2].settings = imp[2].settings.model_copy(update={"openrouter_api_key": None})


def ready(imp, content=None, **approval):
    ident = analyzed(imp, content)
    approved(imp, ident, **approval)
    read = previewed(imp, ident)
    response = confirm(imp, ident, read)
    assert response.status_code == 200, response.text
    return ident, read, response.json()["data"]["import_revision"]


def analyzed_files(imp, files):
    draft = post(imp, "/stores/" + str(imp[1].store_id) + "/imports", {"data_date": "2026-10-09"}).json()["data"]
    ident = draft["import_id"]
    upload = imp[0][5].post("/api/v1/imports/" + ident + "/files",
        headers={**imp[3], "Idempotency-Key": str(uuid4())},
        files=[("files[]", (name, content, "application/octet-stream")) for name, content in files],
        data={"client_file_ids[]": [str(uuid4()) for _ in files]})
    assert upload.status_code == 200, upload.text
    data = upload.json()["data"]
    response = post(imp, "/imports/" + ident + "/analyze", dict(
        file_set_version=data["file_set_version"], accepted_file_ids=[r["file_id"] for r in data["items"]],
        acknowledged_rejected_client_file_ids=[]), match=data["import_revision"])
    assert response.status_code == 202, response.text
    assert imp[2].run_one() == UUID(response.json()["data"]["job_id"])
    return ident


def commit(imp, ident, read, revision, *, key=None, resolutions=()):
    return post(imp, "/imports/" + ident + "/process", dict(
        phase="commit", preview_id=read["preview"]["summary"]["preview_id"],
        preview_digest=read["preview"]["summary"]["digest"], confirm=True,
        reason="Synthetic reviewed canonical commit", resolutions=list(resolutions)), match=revision, key=key)


def finished(imp, ident, response):
    assert response.status_code == 202, response.text
    jid = response.json()["data"]["job_id"]
    assert imp[2].run_one() == UUID(jid)
    job = imp[0][5].get("/api/v1/jobs/" + jid)
    assert job.json()["data"]["status"] == "completed", job.text
    result = imp[0][5].get("/api/v1/imports/" + ident + "/completion")
    assert result.status_code == 200, result.text
    return result.json()["data"]


def test_http_commit_fresh_rows_retained_completion_and_same_key_retry(imp, monkeypatch):
    ident, read, revision = ready(imp)
    from app.infrastructure import import_suggestions
    from app.application.use_cases import import_staging
    def forbidden(*args, **kwargs):
        pytest.fail("commit called parser/provider/preview computation")
    monkeypatch.setattr(import_suggestions, "suggest_sheet", forbidden)
    monkeypatch.setattr(import_staging, "parse_source", forbidden)
    monkeypatch.setattr(import_staging, "make_preview", forbidden)
    key = str(uuid4())
    response = commit(imp, ident, read, revision, key=key)
    result = finished(imp, ident, response)
    with Session(imp[0][1]) as fresh:
        rows = fresh.scalars(select(SalesDaily)).all()
        assert len(rows) == 1 and rows[0].quantity == 105
        assert fresh.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED")) == 1
    replay = commit(imp, ident, read, revision, key=key)
    assert replay.status_code == 202 and replay.json()["data"] == response.json()["data"]
    assert imp[2].run_one() is None
    assert imp[0][5].get("/api/v1/imports/" + ident + "/completion").json()["data"] == result
    current = imp[0][5].get("/api/v1/imports/" + ident).json()["data"]
    assert current["completion_available"] and current["allowed_actions"] == []
    assert result["outcome"] == "committed" and result["summary"]["errors"] == 0
    assert result["readiness"]["as_of_date"] == "2026-10-10"  # Store day, not display data_date09.
    assert all(a["can_execute"] and a["result_assessment"] == "NOT_ASSESSED" for a in result["readiness"]["actions"])


def test_excel_shared_values_reuse_12_and_zero_require_own_confirmation(imp, monkeypatch):
    from tests.unit.test_import_parser import workbook
    from tests.integration.test_import_field_value_bindings import review, shared, activate
    from app.infrastructure import import_suggestions
    from app.models.import_staging import ImportProfileVersion
    other = uuid4()
    with Session(imp[0][1]) as s:
        p = s.get(Product, imp[4]); p.name = "Trà đào L"; p.selling_unit = "ly"
        s.add(Product(id=other, store_id=imp[1].store_id, name="Latte đá", selling_unit="ly", active=True)); s.commit()
    content = workbook(
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Ngày</t></is></c><c r="B1" t="inlineStr"><is><t>Món</t></is></c><c r="C1" t="inlineStr"><is><t>SL</t></is></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>10/10/2026</t></is></c><c r="B2" t="inlineStr"><is><t>Trà đào L</t></is></c><c r="C2"><v>12</v></c></row>'
        '<row r="3"><c r="A3" t="inlineStr"><is><t>10/10/2026</t></is></c><c r="B3" t="inlineStr"><is><t>Latte đá</t></is></c><c r="C3"><v>0</v></c></row>'
    )
    ident = analyzed_files(imp, [("sales.xlsx", content)])
    review(imp, ident, {"Trà đào L": imp[4], "Latte đá": other}, {"date_format": "DMY_SLASH"})
    assert shared(imp, ident, "sales.unit", "ly", "PROFILE_CONSTANT").status_code == 200
    assert shared(imp, ident, "sales.business_report_key", "POS-20261010").status_code == 200
    profile = activate(imp, ident)
    read = previewed(imp, ident)
    response = confirm(imp, ident, read); assert response.status_code == 200, response.text
    receipt = finished(imp, ident, commit(imp, ident, read, response.json()["data"]["import_revision"]))
    assert receipt["updated_resources"]["sales"]["added_record_count"] == 2
    assert all(r["provenance"]["unit"]["value_source"] == "PROFILE_CONSTANT"
        and r["provenance"]["business_report_key"]["value_source"] == "IMPORT_VALUE" for r in receipt["canonical_references"])
    with Session(imp[0][1]) as fresh:
        assert {r.product_id: r.quantity for r in fresh.scalars(select(SalesDaily))} == {imp[4]: 12, other: 0}
        assert "POS-20261010" not in str(fresh.get(ImportProfileVersion, (UUID(profile["profile_id"]), profile["approved_version"])).spec_json)
    monkeypatch.setattr(import_suggestions, "suggest_sheet", lambda *a, **k: pytest.fail("reused mapping called provider"))
    second = analyzed_files(imp, [("sales.xlsx", content)])
    summary = imp[0][5].get("/api/v1/imports/" + second + "/mapping-summary").json()["data"]
    assert not summary["can_preview"] and any(x["code"] == "MISSING_IMPORT_VALUE" for x in summary["blockers"])
    assert shared(imp, second, "sales.business_report_key", "POS-20261010-REVIEWED").status_code == 200
    read2 = previewed(imp, second)
    assert commit(imp, second, read2, read2["import_revision"]).status_code == 409
    reviewed = confirm(imp, second, read2)
    done = finished(imp, second, commit(imp, second, read2, reviewed.json()["data"]["import_revision"]))
    assert done["outcome"] == "no_changes" and not done["updated_resources"]["sales"]["updated"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 2


def test_reserved_product_commits_before_dependent_sales_with_explicit_false_null(imp):
    from app.models import InventoryLot
    content = sales_bytes(imp).replace(str(imp[4]).encode(), b"NEW-MENU")
    ident, read, revision = ready(imp, content, resolutions={"UNKNOWN_PRODUCT": dict(
        kind="new_entity_proposal", entity="product", source_business_key="NEW-MENU",
        metadata=dict(name="New item", selling_unit="cup", sku="NEW-MENU", price=None, active=False),
        evidence_reference="Owner explicit metadata")})
    done = finished(imp, ident, commit(imp, ident, read, revision))
    assert done["updated_resources"]["catalog"]["created_product_count"] == 1
    assert not done["updated_resources"]["inventory"]["updated"]
    assert done["summary"]["rows"] == 1  # Raw source rows exclude reservation creation.
    assert done["summary"]["counts"]["NEW"] == 2
    assert done["summary"]["inserted_record_count"] == 2
    created = next(r for r in done["canonical_references"] if r["canonical_domain"] == "products")
    assert created["provenance"]["active"]["value_source"] == "IDENTITY_BINDING"
    assert created["provenance"]["active"]["applied_rule_ids"][0].startswith("entity_proposal:")
    with Session(imp[0][1]) as fresh:
        p = fresh.scalar(select(Product).where(Product.sku == "NEW-MENU"))
        assert p.price is None and p.active is False
        assert fresh.scalar(select(SalesDaily.product_id)) == p.id
        assert fresh.scalar(select(func.count()).select_from(InventoryLot)) == 0


@pytest.mark.parametrize("after_accept", [False, True])
def test_changed_dependency_blocks_acceptance_or_execution(imp, after_accept):
    ident, read, revision = ready(imp)
    response = commit(imp, ident, read, revision) if after_accept else None
    with Session(imp[0][1]) as other:
        other.get(Product, imp[4]).name = "Changed after review"; other.commit()
    if after_accept:
        assert response.status_code == 202; imp[2].run_one()
        job = imp[0][5].get("/api/v1/jobs/" + response.json()["data"]["job_id"]).json()["data"]
        assert job["status"] == "failed" and job["error"]["code"] == "PREVIEW_STALE"
    else:
        response = commit(imp, ident, read, revision)
        assert response.status_code == 409 and response.json()["error"]["code"] == "PREVIEW_STALE"
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    assert imp[0][5].get("/api/v1/imports/" + ident + "/completion").status_code == 409


def test_rejected_transaction_rolls_back_earlier_canonical_rows_and_success_audit(imp, monkeypatch):
    from app.application.use_cases.sales import SalesUseCases
    from app.application.contracts.auth import AuthError
    other = uuid4()
    with Session(imp[0][1]) as s:
        s.add(Product(id=other, store_id=imp[1].store_id, name="Second", selling_unit="cup", active=True)); s.commit()
    ident, read, revision = ready(imp, sales_bytes(imp) + (str(other) + ",2026-10-09,0,cup,REPORT-1\n").encode())
    original = SalesUseCases.record_in_transaction
    flushed = []
    def fail_second(self, data):
        result = original(self, data); flushed.append(result.id)
        if len(flushed) == 2:
            raise AuthError("PREVIEW_BLOCKED", 409)
        return result
    monkeypatch.setattr(SalesUseCases, "record_in_transaction", fail_second)
    response = commit(imp, ident, read, revision); assert response.status_code == 202; imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        assert len(flushed) == 2 and fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        assert fresh.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED")) == 0
        assert fresh.get(ImportJob, UUID(response.json()["data"]["job_id"])).status == "failed"


@pytest.mark.parametrize("revoke", ["import.commit", "sales.record", "sales.read"])
def test_worker_current_rights_not_acceptance_grant(imp, revoke):
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    from app.domain.permissions import PERMISSIONS
    ident, read, revision = ready(imp)
    response = commit(imp, ident, read, revision); assert response.status_code == 202
    with Session(imp[0][1]) as s:
        member = s.scalar(select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id)); member.role = "STAFF"
        for key in sorted(PERMISSIONS - {revoke}):
            s.add(MembershipGrant(membership_id=member.id, permission=key))
        s.commit()
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        job = fresh.get(ImportJob, UUID(response.json()["data"]["job_id"]))
        assert job.status == "failed" and job.error_json["code"] == "PERMISSION_DENIED"
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    if revoke == "sales.read":
        assert imp[0][5].get("/api/v1/jobs/" + response.json()["data"]["job_id"]).status_code == 403


@pytest.mark.parametrize("completed", [False, True])
def test_commit_acceptance_and_success_receipt_replay_recheck_current_write_rights(imp, completed):
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    from app.domain.permissions import PERMISSIONS
    ident, read, revision = ready(imp)
    key = str(uuid4())
    if completed:
        finished(imp, ident, commit(imp, ident, read, revision, key=key))
    with Session(imp[0][1]) as s:
        member = s.scalar(select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id))
        member.role = "STAFF"
        for permission in sorted(PERMISSIONS - {"sales.record"}):
            s.add(MembershipGrant(membership_id=member.id, permission=permission))
        s.commit()
    response = commit(imp, ident, read, revision, key=key)
    assert response.status_code == 403 and response.json()["error"]["code"] == "PERMISSION_DENIED"
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == int(completed)
        assert fresh.scalar(select(func.count()).select_from(ImportJob).where(ImportJob.operation == "import_commit")) == int(completed)
        assert fresh.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED")) == int(completed)


def test_parallel_commit_acceptance_worker_retry_and_conflicting_payload(imp):
    ident, read, revision = ready(imp); keys = [str(uuid4()), str(uuid4())]
    with ThreadPoolExecutor(2) as pool:
        calls = list(pool.map(lambda key: commit(imp, ident, read, revision, key=key), keys))
    assert sorted(r.status_code for r in calls) in ([202, 412], [202, 409])
    winner = next(r for r in calls if r.status_code == 202); finished(imp, ident, winner)
    assert imp[2].run_one() is None
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 1
        assert fresh.scalar(select(func.count()).select_from(ImportJob).where(ImportJob.operation == "import_commit")) == 1
    wrong = {**read, "preview": {**read["preview"], "summary": {**read["preview"]["summary"], "digest": "changed"}}}
    conflict = commit(imp, ident, wrong, revision, key=keys[calls.index(winner)])
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_uncertain_commit_after_durable_write_reconciles_without_repeat(imp, monkeypatch):
    original = Session.commit; raised = []
    def lost(self):
        has_success = any(isinstance(r, ImportAudit) and r.kind == "IMPORT_CANONICAL_COMMITTED" for r in self.new)
        original(self)
        if has_success and not raised:
            raised.append(True); raise RuntimeError("Synthetic lost acknowledgment after actual DB COMMIT")
    ident, read, revision = ready(imp)
    response = commit(imp, ident, read, revision); assert response.status_code == 202
    monkeypatch.setattr(Session, "commit", lost)
    assert imp[2].run_one() == UUID(response.json()["data"]["job_id"])
    assert raised and imp[2].run_one() is None
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 1
        assert fresh.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED")) == 1
    assert imp[0][5].get("/api/v1/imports/" + ident + "/completion").status_code == 200


def test_recipe_creates_reserved_ingredient_and_preserves_zero_loss_then_blocks_overlap(imp):
    from app.models import Ingredient, Recipe, RecipeLine, InventoryLot
    sugar = uuid4()
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=sugar, store_id=imp[1].store_id, name="Sugar", base_unit="g", expiry_tracking=False, active=True)); s.commit()
    source = dict(product_id=imp[4], version=1, effective_from="2026-10-11", effective_to=None,
        quantity_basis="WHOLE_BATCH", yield_quantity="1", yield_unit="cup", process_loss_rate="0", ingredient_id="MILK-NEW", quantity="100", unit="ml")
    ident, read, revision = ready(imp, csv_source("recipes", [source, {**source, "ingredient_id": str(sugar), "quantity": "0.1", "unit": "g"}]), report="recipes",
        resolutions={"UNKNOWN_INGREDIENT": dict(kind="new_entity_proposal", entity="ingredient",
            source_business_key="MILK-NEW", metadata=dict(name="Milk", base_unit="ml", sku=None,
                expiry_tracking=False, active=False), evidence_reference="Owner declared ingredient")})
    result = finished(imp, ident, commit(imp, ident, read, revision))
    assert result["updated_resources"]["catalog"]["created_ingredient_count"] == 1
    assert result["updated_resources"]["menu"]["affected_product_count"] == 1
    recipe_ref = next(r for r in result["canonical_references"] if r["canonical_domain"] == "recipes")
    assert len(recipe_ref["line_provenance"]) == 2
    assert {r["source_location"]["row_number"] for r in recipe_ref["line_provenance"]} == {2, 3}
    assert all(r["provenance"]["quantity"]["source_column_index"] is not None for r in recipe_ref["line_provenance"])
    with Session(imp[0][1]) as fresh:
        ing = fresh.scalar(select(Ingredient).where(Ingredient.name == "Milk")); recipe = fresh.scalar(select(Recipe))
        assert ing.expiry_tracking is False and ing.active is False and ing.sku is None
        assert recipe.process_loss_rate == 0 and recipe.effective_to is None
        assert set(fresh.scalars(select(RecipeLine.ingredient_id))) == {ing.id, sugar}
        assert fresh.scalar(select(func.count()).select_from(InventoryLot)) == 0
        iid = ing.id
    source.update(version=2, ingredient_id=str(iid))
    second = analyzed(imp, csv_source("recipes", [source]))
    read2 = previewed(imp, second)
    assert any(b["code"] == "RECIPE_PERIOD_OVERLAP" for b in read2["preview"]["summary"]["blockers"])
    assert confirm(imp, second, read2).status_code == 409
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 1


def test_disjoint_source_retry_revision_205_to_210_and_daily_total_mix_blocked(imp):
    from decimal import Decimal
    with Session(imp[0][1]) as s:
        s.add(SalesDaily(store_id=imp[1].store_id, product_id=imp[4], sales_date=date(2026, 10, 9), quantity=Decimal(100))); s.commit()
    ident, read, revision = ready(imp, context={"sales_semantics": "disjoint_contribution"})
    row = read["preview"]["rows"][0]
    assert row["after"]["quantity"] == "205" and row["normalized_source_quantity"] == "105"
    assert row["provenance"]["quantity"]["origin"] == "DETERMINISTIC_DERIVED"
    resolution = dict(row_id=row["row_id"], action="confirm_disjoint_merge", report_business_key="REPORT-1",
        evidence_reference="Operator verified source is separate from captured base100", reason="Reviewed disjoint set", disjoint_assertion=True)
    done = finished(imp, ident, commit(imp, ident, read, revision, resolutions=[resolution]))
    assert done["updated_resources"]["sales"]["changed_record_count"] == 1
    # Same report reimport is source-aware NO_OP, not 205 + 105.
    second = analyzed(imp); approved(imp, second, context={"sales_semantics": "disjoint_contribution"}); read2 = previewed(imp, second)
    assert read2["preview"]["rows"][0]["proposed_action"] == "NO_OP"
    reviewed = confirm(imp, second, read2)
    done2 = finished(imp, second, commit(imp, second, read2, reviewed.json()["data"]["import_revision"]))
    assert done2["outcome"] == "no_changes"
    third = analyzed(imp, sales_bytes(imp, "110")); approved(imp, third, context={"sales_semantics": "disjoint_contribution"}); read3 = previewed(imp, third)
    r3 = read3["preview"]["rows"][0]
    assert r3["after"]["quantity"] == "210" and r3["normalized_source_quantity"] == "110"
    confirmation = confirm(imp, third, read3)
    correction = {**resolution, "row_id": r3["row_id"], "action": "replace_daily_total", "disjoint_assertion": None}
    finished(imp, third, commit(imp, third, read3, confirmation.json()["data"]["import_revision"], resolutions=[correction]))
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(SalesDaily.quantity)) == 210
        audits = fresh.scalars(select(ImportAudit).where(ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED")).all()
        revisions = sorted((r["source_revision"], r["source_quantity"]) for a in audits for r in a.record_json["sales_sources"])
        assert revisions == [(1, "105"), (2, "110")]
        assert next(r for a in audits for r in a.record_json["sales_sources"] if r["source_revision"] == 1)["baseline"]["quantity"] == "100"
    # A daily-total dataset cannot silently replace/mix partial contributions.
    mixed = analyzed(imp, sales_bytes(imp, "200"))
    from tests.integration.test_import_classification import listing, mapping
    issue = next(i for i in listing(imp, mixed) if i["issue_type"] == "source_context")
    assert mapping(imp, mixed, issue, {"resolution": dict(kind="source_context", source_system_key="POS-B",
        report_type="daily-sales", evidence_reference="Daily total separate scope", sales_semantics="daily_total")}).status_code == 200
    approved(imp, mixed, source="POS-B")
    mixedread = previewed(imp, mixed)
    assert any(b["code"] == "SALES_OVERLAP_UNRESOLVED" for b in mixedread["preview"]["summary"]["blockers"])


def test_inventory_noop_commits_without_fabricating_movement(imp):
    from datetime import datetime, timezone
    from app.models import Ingredient, InventoryLot, InventoryMovement
    ingredient, lot = uuid4(), uuid4()
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=ingredient, store_id=imp[1].store_id, name="Milk", base_unit="ml", expiry_tracking=False, active=True)); s.flush()
        s.add(InventoryLot(id=lot, store_id=imp[1].store_id, ingredient_id=ingredient, unit="ml", on_hand_quantity=12,
            updated_at=datetime(2026, 10, 10, 1, tzinfo=timezone.utc))); s.commit()
    content = csv_source("inventory_count", [dict(ingredient_id=ingredient, lot_id=lot, on_hand="12", unit="ml",
        observed_at="2026-10-10T02:00:00Z", reason="Count unchanged")])
    ident, read, revision = ready(imp, content, context={"inventory_semantics": "lot_stock_count"})
    assert read["preview"]["rows"][0]["proposed_action"] == "NO_OP"
    response = commit(imp, ident, read, revision)
    result = finished(imp, ident, response)
    assert result["summary"]["no_op_count"] == 1
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 0
        assert fresh.scalar(select(func.count()).select_from(ImportJob).where(ImportJob.operation == "import_commit")) == 1


def test_commit_and_completion_foreign_store_reads_deny_and_retained_read_does_no_work(imp, monkeypatch):
    from tests.integration.test_auth_public import setup, login
    from app.application.use_cases import import_staging
    ident, read, revision = ready(imp)
    response = commit(imp, ident, read, revision); result = finished(imp, ident, response)
    setup(imp[0], "other@example.test"); login(imp[0], "other@example.test")
    assert imp[0][5].get("/api/v1/imports/" + ident + "/completion").status_code == 404
    assert imp[0][5].get("/api/v1/jobs/" + response.json()["data"]["job_id"]).status_code == 404
    login(imp[0])
    for name in ("parse_source", "make_preview", "write_rows"):
        monkeypatch.setattr(import_staging, name, lambda *a, **k: pytest.fail("retained GET ran work"))
    assert imp[0][5].get("/api/v1/imports/" + ident + "/completion").json()["data"] == result
    assert imp[0][5].get("/api/v1/jobs/" + response.json()["data"]["job_id"]).json()["data"]["status"] == "completed"


def test_actual_process_death_after_claim_requires_explicit_retry_not_double_write(imp):
    import os
    import subprocess
    import sys
    from app.models.import_staging import ImportBatch
    ident, read, revision = ready(imp)
    key = str(uuid4()); response = commit(imp, ident, read, revision, key=key)
    assert response.status_code == 202
    job_id = UUID(response.json()["data"]["job_id"])
    child = """
import os
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.config import Settings
from scripts.dev import TEST_DATABASE_NAMES, validate_reset_target
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.import_staging import ImportStaging
cfg = Settings(_env_file=None, openrouter_api_key=None, import_worker_enabled=False)
url = make_url(cfg.database_url)
assert cfg.environment == 'test' and url.database in TEST_DATABASE_NAMES
assert url.host in {'localhost','127.0.0.1','::1'} and not url.query
validate_reset_target(cfg)
engine = create_database_engine(cfg)
with engine.connect() as c:
    assert c.scalar(text('SELECT current_database()')) == url.database
class CrashBeforeWrites(ImportStaging):
    def _execute_commit(self, job_id, claim):
        os._exit(86)
clock = lambda: datetime.fromisoformat(os.environ['COMMIT_TEST_TIME'])
CrashBeforeWrites(AuthUseCases(engine, clock=clock), cfg).run_one()
raise AssertionError('No queued commit claimed')
"""
    variables = {**os.environ, "DATABASE_URL": imp[0][0].database_url, "ENVIRONMENT": "test",
                 "COMMIT_TEST_TIME": imp[0][4][0].isoformat(), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-c", child], env=variables, capture_output=True,
                            timeout=25, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 86  # Do not print child env/credentials.
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportJob, job_id).status == "running"
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    assert imp[2].recover() == (job_id,)
    assert commit(imp, ident, read, revision, key=key).json()["data"]["job_id"] == str(job_id)
    current = imp[0][5].get("/api/v1/imports/" + ident + "?include_preview=true").json()["data"]
    assert "commit" in current["allowed_actions"]
    done = finished(imp, ident, commit(imp, ident, read, current["import_revision"]))
    assert done["outcome"] == "committed" and imp[2].recover() == ()
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportBatch, UUID(ident)).status == "completed"
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 1


def test_two_actual_workers_claim_only_one_commit(imp):
    from app.application.use_cases.import_staging import ImportStaging
    ident, read, revision = ready(imp)
    response = commit(imp, ident, read, revision); assert response.status_code == 202
    second = ImportStaging(imp[0][2], imp[2].settings)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda worker: worker.run_one(), [imp[2], second]))
    assert results.count(UUID(response.json()["data"]["job_id"])) == 1 and results.count(None) == 1
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 1
        assert fresh.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED")) == 1


def test_table_fence_blocks_unfenced_writer_until_atomic_commit_finishes(imp, monkeypatch):
    import threading
    import time
    from sqlalchemy import text
    from app.application.contracts.sales import RecordDailySalesInput
    from app.application.use_cases.sales import SalesUseCases
    from app.application.use_cases import import_staging
    ident, read, revision = ready(imp)
    response = commit(imp, ident, read, revision); assert response.status_code == 202
    held, release, writer_entered = threading.Event(), threading.Event(), threading.Event()
    original = import_staging.write_rows
    pid = []
    def hold(*args, **kwargs):
        held.set(); assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(import_staging, "write_rows", hold)
    def unfenced_writer():
        with Session(imp[0][1]) as s:
            pid.append(s.scalar(text("SELECT pg_backend_pid()")))
            writer_entered.set()
            SalesUseCases(s).record_in_transaction(RecordDailySalesInput(store_id=imp[1].store_id,
                product_id=imp[4], sales_date=date(2026, 10, 8), quantity=7))
            s.commit()
    with ThreadPoolExecutor(2) as pool:
        committing = pool.submit(imp[2].run_one); assert held.wait(5)
        writer = pool.submit(unfenced_writer); assert writer_entered.wait(5)
        blocked = False
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                with Session(imp[0][1]) as fresh:
                    blocked = bool(fresh.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid=:pid "
                        "AND relation='sales_daily'::regclass AND mode='RowExclusiveLock' AND NOT granted)"), {"pid": pid[0]}))
                if blocked:
                    break
                time.sleep(0.02)
            assert blocked and not writer.done()
        finally:
            release.set()
        assert committing.result(timeout=10) == UUID(response.json()["data"]["job_id"])
        writer.result(timeout=10)
    with Session(imp[0][1]) as fresh:
        assert sorted(fresh.scalars(select(SalesDaily.quantity))) == [7, 105]


def test_retired_pin_blocks_uncommitted_but_completion_survives_profile_reapproval(imp):
    from app.models.import_staging import ImportProfile, ImportBatch
    ident, read, revision = ready(imp)
    done = finished(imp, ident, commit(imp, ident, read, revision))
    ref = read["preview"]["summary"]["mapping_bindings"][0]
    with Session(imp[0][1]) as fresh:
        profile = fresh.get(ImportProfile, UUID(ref["profile_id"]))
        lifecycle, proposal, active = profile.lifecycle_revision, profile.proposal_revision, profile.active_version
        original_status = fresh.get(ImportBatch, UUID(ident)).status
    change = post(imp, "/stores/" + str(imp[1].store_id) + "/mapping-profiles/" + ref["profile_id"] + "/decisions",
        dict(decision="approve_activate", proposal_revision=proposal, expected_active_version=active,
             reason="Owner reapproved unchanged rule for future batches"), match=lifecycle)
    assert change.status_code == 200, change.text
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportBatch, UUID(ident)).status == original_status
    assert imp[0][5].get("/api/v1/imports/" + ident + "/completion").json()["data"] == done
    second = analyzed(imp); approved(imp, second); read2 = previewed(imp, second)
    reviewed = confirm(imp, second, read2); assert reviewed.status_code == 200
    with Session(imp[0][1]) as fresh:
        profile = fresh.get(ImportProfile, UUID(ref["profile_id"]))
        lifecycle, active = profile.lifecycle_revision, profile.active_version
    retire = post(imp, "/stores/" + str(imp[1].store_id) + "/mapping-profiles/" + ref["profile_id"] + "/decisions",
                  dict(decision="retire", active_version=active, reason="Owner retires pinned rule"), match=lifecycle)
    assert retire.status_code == 200
    rejected = commit(imp, second, read2, reviewed.json()["data"]["import_revision"])
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "MAPPING_VERSION_RETIRED"
    assert imp[0][5].get("/api/v1/imports/" + ident + "/completion").json()["data"] == done


def test_shared_declaration_change_requires_new_preview_and_review(imp):
    from tests.integration.test_import_field_value_bindings import review, shared, activate
    from app.models.import_staging import ImportPreview
    content = ("Ngày,Món,SL\n10/10/2026,Known,12\n").encode()
    ident = analyzed(imp, content)
    review(imp, ident, {"Known": imp[4]}, {"date_format": "DMY_SLASH"})
    assert shared(imp, ident, "sales.unit", "cup", "PROFILE_CONSTANT").status_code == 200
    assert shared(imp, ident, "sales.business_report_key", "REPORT-OLD").status_code == 200
    activate(imp, ident)
    read = previewed(imp, ident); reviewed = confirm(imp, ident, read); assert reviewed.status_code == 200
    assert shared(imp, ident, "sales.business_report_key", "REPORT-CHANGED").status_code == 200
    current = imp[0][5].get("/api/v1/imports/" + ident + "?include_preview=true").json()["data"]
    assert not current["confirmation_usable"] and "commit" not in current["allowed_actions"]
    rejected = commit(imp, ident, read, current["import_revision"])
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] in {"PREVIEW_BLOCKED", "PREVIEW_STALE"}
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportPreview)) == 1
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


@pytest.mark.parametrize("invalid", ["unit", "dates"])
def test_recipe_invalid_unit_or_dates_block_before_commit(imp, invalid):
    from app.models import Ingredient, Recipe
    iid = uuid4()
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=iid, store_id=imp[1].store_id, name="Milk", base_unit="ml", expiry_tracking=False, active=True)); s.commit()
    value = dict(product_id=imp[4], version=1, effective_from="2026-10-11", effective_to=None,
        quantity_basis="WHOLE_BATCH", yield_quantity="1", yield_unit="cup", process_loss_rate="0", ingredient_id=iid, quantity="100", unit="ml")
    if invalid == "unit":
        value["unit"] = "L"
    else:
        value["effective_to"] = "2026-10-10"
    ident = analyzed(imp, csv_source("recipes", [value]))
    if invalid == "unit":
        from tests.integration.test_import_classification import listing
        assert any(i["code"] == "UNIT_CONVERSION_REQUIRED" for i in listing(imp, ident))
        state = imp[0][5].get("/api/v1/imports/" + ident + "/mapping-summary").json()["data"]
        current = imp[0][5].get("/api/v1/imports/" + ident).json()["data"]
        assert not state["can_preview"]
        blocked = post(imp, "/imports/" + ident + "/process", dict(phase="preview",
            mapping_revision=state["mapping_revision"]), match=current["import_revision"])
        assert blocked.status_code == 409  # Do not invent/approve a conversion to make the test pass.
        with Session(imp[0][1]) as fresh:
            assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0
        return
    approved(imp, ident, report="invalid-recipe")
    read = previewed(imp, ident)
    assert read["preview"]["summary"]["blockers"] and confirm(imp, ident, read).status_code == 409
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0
