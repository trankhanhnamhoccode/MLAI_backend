"""CAT12 paths/typed phases and audit-remediation wire, generated without runtime."""
from app.config import Settings
from app.main import create_app


def test_exact_cat12_routes_and_conditional_import_reason_schema():
    schema=create_app(Settings(_env_file=None,import_worker_enabled=False)).openapi()
    base="/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule"
    for suffix,method,identity in (("","get","N20"),("/changes","post","N21"),("/changes/{change_id}","get","N22")):
        op=schema["paths"][base+suffix][method]
        assert op["operationId"]==identity and op["security"]==[{"APIKeyCookie":[]}]
        assert "200" in op["responses"] and {"401","403","404"}<=set(op["responses"])
        if identity=="N21":
            assert {"If-Match","Idempotency-Key","X-CSRF-Token"} <= {p["name"] for p in op["parameters"]}
            assert op["requestBody"]["content"]["application/json"]["schema"]["discriminator"]["propertyName"]=="phase"
    # Module-qualified schemas are expected when Import and Recipe both name CommitRequest.
    requests=[s for s in schema["components"]["schemas"].values() if s.get("title")=="CommitRequest"]
    imp=next(s for s in requests if "resolutions" in s["properties"])
    assert "reason" not in imp["required"] and "reason" in imp["properties"]
    recipe=next(s for s in requests if "change_id" in s["properties"])
    assert recipe["properties"]["confirm"]["const"] is True and "reason" not in recipe["properties"]
    assert recipe["additionalProperties"] is False
