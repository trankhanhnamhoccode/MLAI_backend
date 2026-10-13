"""Real guarded PG HTTP import values: no canonical write or live provider."""

from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, analyzed, post, previewed
from tests.integration.test_import_classification import mapping, listing, confirm
from app.models import Product, SalesDaily
from app.models.import_staging import (
    ImportProfileVersion,
    ImportPreview,
    ImportBatch,
    ImportAudit,
)


def summary(imp, ident):
    return (
        imp[0][5]
        .get(
            "/api/v1/imports/" + ident + "/mapping-summary?include_profile_details=true"
        )
        .json()["data"]
    )


def shared(imp, ident, target, value, scope="IMPORT_VALUE", **extra):
    issue = listing(imp, ident)[0]
    return mapping(
        imp,
        ident,
        issue,
        {
            "resolution": dict(
                kind="shared_value",
                target_field=target,
                scope=scope,
                value=value,
                evidence_reference="Synthetic explicit value",
                **extra,
            )
        },
    )


def review(imp, ident, identities=None, context=None, schema="sales"):
    for item in sorted(listing(imp, ident), key=lambda i: i["issue_type"] != "source_context"):
        item = next((i for i in listing(imp, ident) if i["mapping_id"] == item["mapping_id"]), None)
        if item is None:
            continue  # Approved alias resolved this discovery-only issue.
        if item["status"] in ("auto_mapped", "resolved"):
            continue
        if item["issue_type"] == "classification":
            body = {
                "resolution": dict(
                    kind="sheet_type", sheet_type=schema, reason="Reviewed sheet"
                )
            }
        elif item["issue_type"] == "source_context":
            body = {
                "resolution": dict(
                    kind="source_context",
                    source_system_key="POS-A",
                    report_type="DAILY",
                    evidence_reference="Explicit report source",
                    sales_semantics="daily_total",
                    **(context or {}),
                )
            }
        elif item["issue_type"] == "column" and item["target_field"]:
            body = {"target_field": item["target_field"]}
        elif item["issue_type"] == "identity":
            body = {
                "resolution": dict(
                    kind="identity_binding",
                    canonical_id=str(identities[item["source_header"]]),
                )
            }
        else:
            raise AssertionError(item)
        r = mapping(imp, ident, item, body)
        assert r.status_code == 200, r.text


def activate(imp, ident):
    p = summary(imp, ident)["profile_proposals"][0]
    assert not p["missing_fields"], p
    r = post(
        imp,
        "/stores/"
        + str(imp[1].store_id)
        + "/mapping-profiles/"
        + p["profile_id"]
        + "/decisions",
        dict(
            decision="approve_activate",
            proposal_revision=p["proposal_revision"],
            expected_active_version=p["active_version"],
            reason="Owner reviewed source rules",
        ),
        match=p["lifecycle_revision"],
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_first_sales_then_reuse_requires_new_import_report_key(imp, monkeypatch):
    from app.infrastructure import import_suggestions
    from app.application.use_cases import import_staging

    original_compute = import_staging.make_preview
    checked = []

    def compute(*args, **kwargs):
        assert imp[0][1].pool.checkedout() == 0
        checked.append(True)
        return original_compute(*args, **kwargs)

    monkeypatch.setattr(import_staging, "make_preview", compute)
    ids = {"Trà đào L": imp[4], "Latte đá": uuid4()}
    with Session(imp[0][1]) as s:
        p = s.get(Product, imp[4])
        p.name = "Trà đào L"
        p.selling_unit = "ly"
        s.add(
            Product(
                id=ids["Latte đá"],
                store_id=imp[1].store_id,
                name="Latte đá",
                selling_unit="ly",
                active=True,
            )
        )
        s.commit()
    content = "Ngày,Món,SL\n10/10/2026,Trà đào L,12\n10/10/2026,Latte đá,0\n".encode()
    ident = analyzed(imp, content)
    review(imp, ident, ids, {"date_format": "DMY_SLASH"})
    assert shared(imp, ident, "sales.unit", "ly", "PROFILE_CONSTANT").status_code == 200
    assert (
        shared(imp, ident, "sales.business_report_key", "POS-A-20261010").status_code
        == 200
    )
    decision = activate(imp, ident)
    read = previewed(imp, ident)
    rows = read["preview"]["rows"]
    assert [r["after"]["quantity"] for r in rows] == ["12", "0"]
    assert all(
        r["after"]["unit"] == "ly" and r["after"]["sales_date"] == "2026-10-10"
        for r in rows
    )
    assert all(
        r["provenance"]["unit"]["value_source"] == "PROFILE_CONSTANT"
        and r["provenance"]["business_report_key"]["value_source"] == "IMPORT_VALUE"
        and r["provenance"]["product_id"]["value_source"] == "IDENTITY_BINDING"
        for r in rows
    )
    assert all(
        r["provenance"]["unit"]["declaration_id"]
        and r["provenance"]["product_id"]["source_column_index"] == 1
        for r in rows
    )
    first = confirm(imp, ident, read)
    assert first.status_code == 200, first.text
    with Session(imp[0][1]) as fresh:
        v = fresh.get(
            ImportProfileVersion,
            (UUID(decision["profile_id"]), decision["approved_version"]),
        )
        original = v.spec_json.copy()
        assert "POS-A-20261010" not in str(v.spec_json)
        assert {r["scope"] for r in v.spec_json["shared_field_bindings"]} == {
            "PROFILE_CONSTANT",
            "IMPORT_VALUE",
        }
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        preview = fresh.scalar(
            select(ImportPreview).where(ImportPreview.import_id == UUID(ident))
        )
        assert (
            preview.content_json["reviewed_sheets"][0]["import_values"][0]["value"]
            == "POS-A-20261010"
        )
    monkeypatch.setattr(
        import_suggestions,
        "suggest_sheet",
        lambda *a, **kw: (None, "LLM_UNAVAILABLE"),
    )
    second = analyzed(imp, content)
    assert not summary(imp, second)["binding_refs"]
    monkeypatch.setattr(import_suggestions, "suggest_sheet", lambda *a, **kw: pytest.fail("source-selected reuse called Qwen"))
    review(imp, second, ids, {"date_format": "DMY_SLASH"})
    m = summary(imp, second)
    assert m["binding_refs"] and not m["can_preview"]
    assert any(x["code"] == "MISSING_IMPORT_VALUE" for x in m["blockers"])
    assert not m["sheets"][0]["import_values"]
    changed = shared(imp, second, "sales.business_report_key", "POS-A-20261011")
    assert (
        changed.status_code == 200 and not changed.json()["data"]["approval_required"]
    ), changed.text
    secondread = previewed(imp, second)
    assert all(
        r["after"]["business_report_key"] == "POS-A-20261011"
        for r in secondread["preview"]["rows"]
    )
    assert not secondread["confirmation_usable"]
    assert confirm(imp, second, secondread).status_code == 200
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.get(
                ImportProfileVersion,
                (UUID(decision["profile_id"]), decision["approved_version"]),
            ).spec_json
            == original
        )
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    assert len(checked) == 2


def test_import_value_current_permissions_cas_type_invalidation_and_store_scope(imp):
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    from app.domain.permissions import PERMISSIONS
    from tests.integration.test_auth_public import setup, login, ORIGIN, provision

    ident = analyzed(imp)
    review(imp, ident)
    r = shared(
        imp,
        ident,
        "sales.business_report_key",
        "PRIVATE-A",
        replace_source_column_index=4,
        acknowledgment=True,
    )
    assert r.status_code == 200
    activate(imp, ident)
    other = provision(imp[0], existing=imp[1].user_id)
    other_import = analyzed((imp[0], other, imp[2], imp[3], imp[4]))
    assert not summary(imp, other_import)["binding_refs"]
    assert not summary(imp, other_import)["sheets"][0]["import_values"]
    other_revision = summary(imp, other_import)["mapping_revision"]
    other_issue = listing(imp, other_import)[0]["mapping_id"]
    staff = setup(imp[0], email="scalar-staff@example.test", store=False)
    mid = uuid4()
    with Session(imp[0][1]) as s:
        s.add(
            StoreMembership(
                id=mid,
                store_id=imp[1].store_id,
                user_id=staff.user_id,
                role="STAFF",
                active=True,
            )
        )
        s.flush()
        for permission in PERMISSIONS:
            s.add(MembershipGrant(membership_id=mid, permission=permission))
        s.commit()
    wire = login(imp[0], email="scalar-staff@example.test").json()["data"]
    imp_staff = (
        imp[0],
        imp[1],
        imp[2],
        {"Origin": ORIGIN, "X-CSRF-Token": wire["session"]["csrf_token"]},
        imp[4],
    )
    item = listing(imp_staff, ident)[0]
    before = summary(imp_staff, ident)
    body = {
        "resolution": dict(
            kind="shared_value",
            target_field="sales.business_report_key",
            scope="IMPORT_VALUE",
            value="PRIVATE-B",
            evidence_reference="batch",
        )
    }
    path = "/api/v1/imports/" + ident + "/mappings/" + item["mapping_id"]
    headers = {
        **imp_staff[3],
        "Idempotency-Key": str(uuid4()),
        "If-Match": '"' + before["mapping_revision"] + '"',
    }
    accepted = imp[0][5].patch(path, json=body, headers=headers)
    assert (
        accepted.status_code == 200 and not accepted.json()["data"]["approval_required"]
    )
    stale = imp[0][5].patch(
        path,
        json={**body, "resolution": {**body["resolution"], "value": "PRIVATE-C"}},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert stale.status_code == 412
    denied_other = imp[0][5].patch(
        "/api/v1/imports/" + other_import + "/mappings/" + other_issue,
        json=body,
        headers={
            **headers,
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + other_revision + '"',
        },
    )
    assert denied_other.status_code == 404
    with Session(imp[0][1]) as s:
        s.delete(s.get(MembershipGrant, (mid, "mapping.propose")))
        s.commit()
    denied = imp[0][5].patch(path, json=body, headers=headers)
    assert denied.status_code == 403
    with Session(imp[0][1]) as s:
        assert (
            s.get(ImportBatch, UUID(ident)).analysis_json["sheets"][0]["import_values"][
                0
            ]["value"]
            == "PRIVATE-B"
        )
    # Renew Owner session and explicitly change type; old shared rules/declarations vanish.
    owner = login(imp[0]).json()["data"]
    imp_owner = (
        imp[0],
        imp[1],
        imp[2],
        {"Origin": ORIGIN, "X-CSRF-Token": owner["session"]["csrf_token"]},
        imp[4],
    )
    classification = next(
        i for i in listing(imp_owner, ident) if i["issue_type"] == "classification"
    )
    changed = mapping(
        imp_owner,
        ident,
        classification,
        {
            "resolution": dict(
                kind="sheet_type", sheet_type="products", reason="explicit correction"
            )
        },
    )
    assert changed.status_code == 200
    sheet = summary(imp_owner, ident)["sheets"][0]
    assert not sheet["shared_field_bindings"] and not sheet["import_values"]


def test_explicit_switch_conflicts_profile_change_and_value_invalidates_review(imp):
    ident = analyzed(imp)
    review(imp, ident)
    conflict = shared(imp, ident, "sales.unit", "cup", "PROFILE_CONSTANT")
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "FIELD_SOURCE_CONFLICT"
    )
    col = next(i for i in listing(imp, ident) if i["target_field"] == "sales.unit")
    r = shared(
        imp,
        ident,
        "sales.unit",
        "cup",
        "PROFILE_CONSTANT",
        replace_source_column_index=col["source_location"]["source_column_index"],
        acknowledgment=True,
    )
    assert r.status_code == 200, r.text
    keycol = next(
        i
        for i in listing(imp, ident)
        if i["target_field"] == "sales.business_report_key"
    )
    r = shared(
        imp,
        ident,
        "sales.business_report_key",
        "R-1",
        replace_source_column_index=keycol["source_location"]["source_column_index"],
        acknowledgment=True,
    )
    assert r.status_code == 200, r.text
    decision = activate(imp, ident)
    read = previewed(imp, ident)
    assert confirm(imp, ident, read).status_code == 200
    r = shared(imp, ident, "sales.business_report_key", "R-2")
    assert r.status_code == 200 and not r.json()["data"]["approval_required"]
    current = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "?include_preview=true")
        .json()["data"]
    )
    assert not current["confirmation_usable"]
    new = previewed(imp, ident)
    assert new["preview"]["rows"][0]["after"]["business_report_key"] == "R-2"
    r = shared(imp, ident, "sales.unit", "wrong", "PROFILE_CONSTANT")
    assert r.status_code == 200 and r.json()["data"]["approval_required"]
    assert not summary(imp, ident)["can_preview"]
    activate(imp, ident)
    bad = previewed(imp, ident)
    assert any(
        i["code"] == "UNIT_MISMATCH" for i in bad["preview"]["rows"][0]["blockers"]
    )
    with Session(imp[0][1]) as fresh:
        v = fresh.get(
            ImportProfileVersion,
            (UUID(decision["profile_id"]), decision["approved_version"]),
        )
        assert (
            next(
                x
                for x in v.spec_json["shared_field_bindings"]
                if x["target_field"] == "sales.unit"
            )["value"]
            == "cup"
        )


def test_shared_mutation_rollback_and_same_key_retry_do_not_duplicate_audit(
    imp, monkeypatch
):
    ident = analyzed(imp)
    review(imp, ident)
    item = listing(imp, ident)[0]
    m = summary(imp, ident)
    body = {
        "resolution": dict(
            kind="shared_value",
            target_field="sales.business_report_key",
            scope="IMPORT_VALUE",
            value="R",
            evidence_reference="explicit",
            replace_source_column_index=4,
            acknowledgment=True,
        )
    }
    base = "/api/v1/imports/" + ident + "/mappings/" + item["mapping_id"]
    key = str(uuid4())
    headers = {
        **imp[3],
        "Idempotency-Key": key,
        "If-Match": '"' + m["mapping_revision"] + '"',
    }
    original = imp[2]._audit

    def broken(s, *args, **kwargs):
        original(s, *args, **kwargs)
        s.flush()
        raise ValueError("injected after flush")

    monkeypatch.setattr(imp[2], "_audit", broken)
    r = imp[0][5].patch(base, json=body, headers=headers)
    assert r.status_code == 503
    with Session(imp[0][1]) as fresh:
        assert not fresh.get(ImportBatch, UUID(ident)).analysis_json["sheets"][0][
            "import_values"
        ]
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "SHARED_VALUE_DECLARED")
            )
            == 0
        )
    monkeypatch.setattr(imp[2], "_audit", original)
    r = imp[0][5].patch(base, json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert (
        imp[0][5].patch(base, json=body, headers=headers).json()["data"]
        == r.json()["data"]
    )
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "SHARED_VALUE_DECLARED")
            )
            == 1
        )


def test_recipe_missing_columns_need_explicit_sources_and_preserve_null(imp):
    from app.models import Ingredient, Recipe, RecipeLine

    ingredient = uuid4()
    with Session(imp[0][1]) as s:
        s.add(
            Ingredient(
                id=ingredient,
                store_id=imp[1].store_id,
                name="Milk",
                base_unit="ml",
                expiry_tracking=False,
                active=True,
            )
        )
        s.commit()
    content = (
        "recipes.product_id,recipes.ingredient_id,recipes.quantity,recipes.unit\n"
        + str(imp[4])
        + ","
        + str(ingredient)
        + ",1000,ml\n"
    ).encode()
    ident = analyzed(imp, content)
    review(imp, ident, schema="recipes")
    m = summary(imp, ident)
    assert not m["can_preview"]
    assert "recipes.yield_quantity" in m["profile_proposals"][0]["missing_fields"]
    for field, value, scope in [
        ("quantity_basis", "WHOLE_BATCH", "PROFILE_CONSTANT"),
        ("yield_quantity", "10", "PROFILE_CONSTANT"),
        ("yield_unit", "cup", "PROFILE_CONSTANT"),
        ("process_loss_rate", "0.2", "PROFILE_CONSTANT"),
        ("version", 1, "IMPORT_VALUE"),
        ("effective_from", "2026-10-10", "IMPORT_VALUE"),
        ("effective_to", None, "IMPORT_VALUE"),
    ]:
        r = shared(imp, ident, "recipes." + field, value, scope)
        assert r.status_code == 200, r.text
    activate(imp, ident)
    read = previewed(imp, ident)
    row = read["preview"]["rows"][0]
    assert not row["blockers"], row
    assert (
        row["after"]["yield_quantity"] == "10"
        and row["after"]["process_loss_rate"] == "0.2"
        and row["after"]["effective_to"] is None
    )
    assert row["after"]["lines"][0]["quantity"] == "1000"
    # Restoring a source column explicitly removes its shared rule, no silent precedence.
    column = next(i for i in listing(imp, ident) if i["target_field"] == "recipes.unit")
    r = shared(
        imp,
        ident,
        "recipes.unit",
        "ml",
        "PROFILE_CONSTANT",
        replace_source_column_index=column["source_location"]["source_column_index"],
        acknowledgment=True,
    )
    assert r.status_code == 200
    ignored = next(
        i for i in listing(imp, ident) if i["source_header"] == "recipes.unit"
    )
    r = mapping(imp, ident, ignored, {"target_field": "recipes.unit"})
    assert r.status_code == 200, r.text
    assert all(
        x["target_field"] != "recipes.unit"
        for x in summary(imp, ident)["profile_proposals"][0]["spec"][
            "shared_field_bindings"
        ]
    )
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Recipe)) == 0
        assert fresh.scalar(select(func.count()).select_from(RecipeLine)) == 0
