"""Public recipe source review -> guarded PG -> dated BOM and recipe readiness."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_import_commit import env, imp, ready, commit, finished, no_live_provider
from tests.integration.test_import_staging import analyzed, approved, previewed, csv_source
from tests.integration.test_import_classification import confirm
from tests.integration.test_import_field_value_bindings import review, shared, activate, summary
from app.models import Ingredient, Recipe, RecipeLine
from app.application.readiness_evaluation import recipe_dependencies
from app.domain.demand.bom import DemandPoint, DatedRecipe, RecipeLine as BOMLine, expand_dated_bom


def ingredient(imp, unit):
    ident = uuid4()
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=ident, store_id=imp[1].store_id, name="Synthetic ingredient",
            base_unit=unit, expiry_tracking=False, active=True)); s.commit()
    return ident


def source(imp, iid, **overrides):
    data = dict(product_id=imp[4], ingredient_id=iid, version=1,
        effective_from="2026-01-01", effective_to=None, quantity_basis="WHOLE_BATCH",
        yield_quantity="10", yield_unit="cup", quantity="1000", unit="g", process_loss_rate="0")
    data.update(overrides)
    return data


@pytest.mark.parametrize("reverse", [False, True])
def test_two_recipe_reports_same_version_never_union_distinct_ingredients(imp, reverse):
    from tests.integration.test_import_commit import analyzed_files
    from tests.integration.test_import_setup_stock import review_batch
    from tests.integration.test_import_classification import confirm
    a, b = ingredient(imp, "g"), ingredient(imp, "g")
    files = [("full-a.csv", csv_source("recipes", [source(imp, a)])),
        ("full-b.csv", csv_source("recipes", [source(imp, b)]))]
    ident = analyzed_files(imp, list(reversed(files)) if reverse else files)
    review_batch(imp, ident)
    read = previewed(imp, ident)
    row = next(r for r in read["preview"]["rows"] if r["after"]["domain"] == "recipes")
    assert row["proposed_action"] == "BLOCKED"
    scoped = [n for n in row["blockers"] if n["code"] == "RECIPE_SOURCE_SCOPE_AMBIGUOUS"]
    assert len({n["source_location"]["file_id"] for n in scoped}) == 2
    rejected = confirm(imp, ident, read)
    assert rejected.status_code == 409
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0
        assert fresh.scalar(select(func.count()).select_from(RecipeLine)) == 0


@pytest.mark.parametrize("basis,quantity,loss,unit,expected", [
    ("PER_SERVING", "100", "0", "g", "4000"),
    ("WHOLE_BATCH", "1000", "0", "g", "4000"),
    ("WHOLE_BATCH", "1000", "0.2", "ml", "5000"),
])
def test_public_flow_fresh_recipe_bom_readiness_retry(imp, basis, quantity, loss, unit, expected):
    iid = ingredient(imp, unit)
    data = source(imp, iid, quantity_basis=basis, quantity=quantity, unit=unit, process_loss_rate=loss)
    ident, preview, revision = ready(imp, csv_source("recipes", [data]), report="recipe-basis")
    row = preview["preview"]["rows"][0]
    assert row["after"]["lines"][0]["quantity"] == "1000"
    assert row["line_provenance"][0]["quantity_basis"] == basis
    assert row["line_provenance"][0]["provenance"]["quantity"]["source_value"] == quantity
    key = str(uuid4())
    accepted = commit(imp, ident, preview, revision, key=key)
    result = finished(imp, ident, accepted)
    ref = next(r for r in result["canonical_references"] if r["canonical_domain"] == "recipes")
    assert ref["line_provenance"][0]["quantity_basis"] == basis
    with Session(imp[0][1]) as fresh:
        r = fresh.scalar(select(Recipe))
        lines = fresh.scalars(select(RecipeLine).where(RecipeLine.recipe_id == r.id)).all()
        assert r.effective_from == date(2026,1,1) and r.yield_quantity == 10
        assert r.process_loss_rate == Decimal(loss) and lines[0].quantity == 1000
        saved = DatedRecipe(r.id, r.product_id, r.effective_from, r.effective_to,
            r.yield_quantity, r.process_loss_rate,
            tuple(BOMLine(l.ingredient_id, l.unit, l.quantity) for l in lines))
        snap = dict(ingredients=[dict(id=str(iid), base_unit=unit)],
            recipes=[dict(id=str(r.id), product_id=str(r.product_id), assigned=r.assigned,
                effective_from=str(r.effective_from), effective_to=None,
                yield_quantity=str(r.yield_quantity), process_loss_rate=str(r.process_loss_rate))],
            recipe_lines=[dict(recipe_id=str(r.id), ingredient_id=str(l.ingredient_id),
                quantity=str(l.quantity), unit=l.unit) for l in lines])
    day = date(2026,10,11)
    bom = expand_dated_bom((DemandPoint("BASE", imp[4], day, Decimal(40)),), (saved,))
    assert not bom.gaps and bom.totals[0].quantity == Decimal(expected)
    days = tuple(day + timedelta(days=i) for i in range(7))
    assert recipe_dependencies(snap, dict(id=str(imp[4])), days) == ((str(iid),), (), ())
    empty = {**snap, "recipes": [], "recipe_lines": []}
    assert recipe_dependencies(empty, dict(id=str(imp[4])), days)[1] == ("RECIPE_PERIOD_GAP",)
    assert result["readiness"]["evaluated_actions"] == ["import", "menu", "inventory"]
    replay = commit(imp, ident, preview, revision, key=key)
    assert replay.status_code == 202 and replay.json()["data"] == accepted.json()["data"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 1


def test_shared_basis_requires_review_and_reuse_requires_fresh_batch_facts(imp):
    iid = ingredient(imp, "g")
    content = csv_source("recipes", [dict(product_id=imp[4], ingredient_id=iid, quantity="100", unit="g")])
    ident = analyzed(imp, content)
    review(imp, ident, schema="recipes")
    assert "recipes.quantity_basis" in summary(imp, ident)["profile_proposals"][0]["missing_fields"]
    for field, value, scope in [
        ("quantity_basis", "PER_SERVING", "IMPORT_VALUE"),
        ("yield_quantity", "10", "PROFILE_CONSTANT"), ("yield_unit", "cup", "PROFILE_CONSTANT"),
        ("process_loss_rate", "0", "PROFILE_CONSTANT"), ("version", 1, "IMPORT_VALUE"),
        ("effective_from", "2026-01-01", "IMPORT_VALUE"), ("effective_to", None, "IMPORT_VALUE"),
    ]:
        response = shared(imp, ident, "recipes." + field, value, scope)
        assert response.status_code == 200, response.text
    activate(imp, ident)
    read = previewed(imp, ident)
    assert read["preview"]["rows"][0]["after"]["lines"][0]["quantity"] == "1000"
    second = analyzed(imp, content)
    review(imp, second, schema="recipes")
    state = summary(imp, second)
    assert not state["can_preview"]  # Profile has requirements, never old batch facts.
    for field, value in [("quantity_basis", "WHOLE_BATCH"), ("version", 1),
        ("effective_from", "2026-01-01"), ("effective_to", None)]:
        response = shared(imp, second, "recipes." + field, value)
        assert response.status_code == 200, response.text
    assert summary(imp, second)["can_preview"]
    changed = previewed(imp, second)
    row = changed["preview"]["rows"][0]
    assert row["after"]["lines"][0]["quantity"] == "100"
    assert row["line_provenance"][0]["quantity_basis"] == "WHOLE_BATCH"


def test_one_invalid_line_prevents_all_recipe_writes(imp):
    iid = ingredient(imp, "g")
    other = ingredient(imp, "g")
    valid = source(imp, iid)
    invalid = source(imp, other, yield_quantity="0")
    ident = analyzed(imp, csv_source("recipes", [valid, invalid]))
    approved(imp, ident, report="atomic-recipe")
    read = previewed(imp, ident)
    assert read["preview"]["summary"]["blockers"]
    assert confirm(imp, ident, read).status_code == 409
    response = commit(imp, ident, read, read["import_revision"])
    assert response.status_code == 409
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0
        assert fresh.scalar(select(func.count()).select_from(RecipeLine)) == 0


def test_source_basis_reuse_reads_current_rows_and_unit_change_blocks(imp):
    iid = ingredient(imp, "g")
    data = source(imp, iid)
    ident = analyzed(imp, csv_source("recipes", [data]))
    approved(imp, ident)
    first = previewed(imp, ident)
    assert first["preview"]["rows"][0]["after"]["lines"][0]["quantity"] == "1000"
    # Same indexed headers, new explicit source semantics: never retain old row facts.
    second = analyzed(imp, csv_source("recipes", [{**data, "quantity_basis": "PER_SERVING", "quantity": "100"}]))
    review(imp, second, schema="recipes")
    assert summary(imp, second)["can_preview"]
    reused = previewed(imp, second)
    line = reused["preview"]["rows"][0]["line_provenance"][0]
    assert line["quantity_basis"] == "PER_SERVING"
    assert line["provenance"]["quantity"]["source_value"] == "100"
    third = analyzed(imp, csv_source("recipes", [{**data, "unit": "ml"}]))
    from tests.integration.test_import_classification import listing
    assert any(i["code"] == "UNIT_CONVERSION_REQUIRED" for i in listing(imp, third))
    assert not summary(imp, third)["can_preview"]


def test_new_xlsx_source_other_headers_reorder_and_physical_header_row(imp):
    from xml.sax.saxutils import escape
    from tests.unit.test_import_parser import workbook
    from tests.integration.test_import_commit import analyzed_files
    from tests.integration.test_import_classification import listing, mapping
    iid = ingredient(imp, "g")
    data = source(imp, iid, quantity_basis="PER_SERVING", quantity="100")
    fields = list(reversed(list(data)))
    headers = {f: "recipes." + f for f in fields}
    headers["quantity"] = "Dose declared by source"
    headers["quantity_basis"] = "How dose is measured"
    def cells(values, row):
        return '<row r="'+str(row)+'">'+''.join(
            '<c r="'+chr(65+i)+str(row)+'" t="inlineStr"><is><t>'+escape(str(v) if v is not None else '')+'</t></is></c>'
            for i,v in enumerate(values))+'</row>'
    content = workbook(cells(["Synthetic worksheet, unrelated to POS"], 1)
        + cells([headers[f] for f in fields], 3) + cells([data[f] for f in fields], 4))
    ident = analyzed_files(imp, [("unrelated-recipe-layout.xlsx", content)])
    for item in listing(imp, ident):
        if item["issue_type"] == "column" and item["source_header"] in {headers["quantity"], headers["quantity_basis"]}:
            target = next(f for f in fields if headers[f] == item["source_header"])
            response = mapping(imp, ident, item, {"target_field": "recipes." + target})
            assert response.status_code == 200, response.text
    review(imp, ident, schema="recipes")
    activate(imp, ident)
    read = previewed(imp, ident)
    row = read["preview"]["rows"][0]
    assert row["source_locations"][0]["row_number"] == 4
    assert row["after"]["lines"][0]["quantity"] == "1000"
    response = confirm(imp, ident, read)
    assert response.status_code == 200, response.text
    finished(imp, ident, commit(imp, ident, read, response.json()["data"]["import_revision"]))
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(RecipeLine)).quantity == 1000


def test_historical_profile_without_basis_requires_owner_review(imp):
    from app.models.import_staging import ImportProfileVersion, ImportProfile
    from app.application.import_identity import content_digest
    iid = ingredient(imp, "g")
    content = csv_source("recipes", [source(imp, iid)])
    ident = analyzed(imp, content)
    approved(imp, ident)
    # Simulate retained pre-extension spec; keep its original profile readable.
    with Session(imp[0][1]) as s:
        version = s.scalar(select(ImportProfileVersion))
        payload = dict(version.spec_json)
        payload["field_bindings"] = [b for b in payload["field_bindings"]
            if b["target_field"] != "recipes.quantity_basis"]
        historical = ImportProfileVersion(**{c.name: getattr(version, c.name)
            for c in ImportProfileVersion.__table__.columns
            if c.name not in {"version", "spec_json", "content_digest"}},
            version=str(uuid4()), spec_json=payload, content_digest=content_digest(payload))
        s.add(historical); s.flush()
        s.get(ImportProfile, version.profile_id).active_version = historical.version
        s.commit()
    second = analyzed(imp, content)
    assert not summary(imp, second)["can_preview"]
    # Current columns can be reviewed anew, but the historical profile is not auto-pinned.
    assert summary(imp, second)["sheets"][0]["classification_origin"] != "REUSED"


@pytest.mark.parametrize("foreign", [False, True])
def test_missing_or_cross_store_ingredient_cannot_bind_or_write(imp, foreign):
    from tests.integration.test_auth_public import provision
    from tests.integration.test_import_classification import listing, mapping
    iid = uuid4()
    if foreign:
        other = provision(imp[0], email="other-recipe-owner@example.test")
        with Session(imp[0][1]) as s:
            s.add(Ingredient(id=iid, store_id=other.store_id, name="Foreign ingredient",
                base_unit="g", expiry_tracking=False, active=True)); s.commit()
    ident = analyzed(imp, csv_source("recipes", [source(imp, iid)]))
    issue = next(i for i in listing(imp, ident) if i["code"] == "UNKNOWN_INGREDIENT")
    response = mapping(imp, ident, issue, {"resolution":dict(kind="identity_binding", canonical_id=str(iid))})
    assert response.status_code == 404, response.text
    assert not summary(imp, ident)["can_preview"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0


def test_recipe_commit_rechecks_staff_rights_after_acceptance(imp):
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    from app.models.import_staging import ImportJob
    from app.domain.permissions import PERMISSIONS
    iid = ingredient(imp, "g")
    ident, read, revision = ready(imp, csv_source("recipes", [source(imp, iid)]))
    accepted = commit(imp, ident, read, revision)
    assert accepted.status_code == 202, accepted.text
    with Session(imp[0][1]) as s:
        member = s.scalar(select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id))
        member.role = "STAFF"
        for key in sorted(PERMISSIONS - {"recipe.create_version"}):
            s.add(MembershipGrant(membership_id=member.id, permission=key))
        s.commit()
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        job = fresh.get(ImportJob, UUID(accepted.json()["data"]["job_id"]))
        assert job.status == "failed" and job.error_json["code"] == "PERMISSION_DENIED"
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0
        assert fresh.scalar(select(func.count()).select_from(RecipeLine)) == 0


def test_recipe_dependency_change_invalidates_reviewed_preview(imp):
    iid = ingredient(imp, "g")
    ident, read, revision = ready(imp, csv_source("recipes", [source(imp, iid)]))
    with Session(imp[0][1]) as s:
        s.get(Ingredient, iid).active = False
        s.commit()
    response = commit(imp, ident, read, revision)
    assert response.status_code == 409, response.text
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0


def test_public_readiness_removes_recipe_gap_but_preserves_other_missing_facts(imp):
    from app.application.use_cases.readiness import ReadinessReads
    imp[0][5].app.state.readiness = ReadinessReads(imp[0][2], None)
    path = "/api/v1/stores/" + str(imp[1].store_id) + "/readiness"
    before = imp[0][5].get(path, params={"actions":"planning"})
    assert before.status_code == 200, before.text
    before = before.json()["data"]
    assert "RECIPE_PERIOD_GAP" in before["scope_estimate"]["excluded_products"][0]["reason_codes"]
    iid = ingredient(imp, "g")
    ident, read, revision = ready(imp, csv_source("recipes", [source(imp, iid,
        quantity_basis="PER_SERVING", quantity="100")]))
    finished(imp, ident, commit(imp, ident, read, revision))
    after = imp[0][5].get(path, params={"actions":"planning"})
    assert after.status_code == 200, after.text
    after = after.json()["data"]
    codes = after["scope_estimate"]["excluded_products"][0]["reason_codes"]
    assert "RECIPE_PERIOD_GAP" not in codes
    assert "PRODUCT_HISTORY_MISSING" in codes and "INVENTORY_SCOPE_UNKNOWN" in codes
    assert after["actions"][0]["availability"] != "ready"
    assert after["source_versions"]["recipes"] != before["source_versions"]["recipes"]


def test_public_reviewed_mass_conversion_and_serving_normalization_commit_once(imp):
    iid = ingredient(imp, "g")
    ident, read, revision = ready(imp, csv_source("recipes", [source(imp, iid,
        quantity_basis="PER_SERVING", quantity="0.1", unit="kg")]), resolutions={
        "UNIT_CONVERSION_REQUIRED": dict(kind="declared_conversion", from_unit="kg", to_unit="g",
            factor=dict(numerator="1000", denominator="1"), evidence_reference="Explicit kg to g")})
    row = read["preview"]["rows"][0]
    assert row["after"]["lines"][0]["quantity"] == "1000"
    assert row["line_provenance"][0]["provenance"]["quantity"]["source_value"] == "0.1"
    finished(imp, ident, commit(imp, ident, read, revision))
    with Session(imp[0][1]) as fresh:
        line = fresh.scalar(select(RecipeLine))
        assert line.quantity == 1000 and line.unit == "g"
