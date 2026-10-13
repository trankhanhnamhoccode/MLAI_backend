from app.config import Settings
from app.main import create_app


def test_s42_eight_operations_exact_contract_headers_dtos_and_auth():
    schema=create_app(Settings(_env_file=None)).openapi()
    expected={
        "N12":("/api/v1/stores/{store_id}/memberships","get","200"),
        "N13":("/api/v1/stores/{store_id}/memberships/{membership_id}/permissions","put","200"),
        "N14":("/api/v1/stores/{store_id}/permission-events","get","200"),
        "N15":("/api/v1/stores/{store_id}/staff-invitations","post","201"),
        "N16":("/api/v1/stores/{store_id}/staff-invitations","get","200"),
        "N17":("/api/v1/stores/{store_id}/staff-invitations/{invitation_id}/actions","post","200"),
        "N18":("/api/v1/staff-invitations/{invitation_id}","get","200"),
        "N19":("/api/v1/staff-invitations/{invitation_id}/accept","post","201"),
    }
    for identity,(path,method,status) in expected.items():
        op=schema["paths"][path][method]
        assert op["operationId"]==identity and status in op["responses"]
        assert op["security"]==[{"APIKeyCookie":[]}]
        assert op["responses"]["422"]["content"]["application/json"]["schema"]=={"$ref":"#/components/schemas/ErrorEnvelope"}
        headers={p["name"] for p in op.get("parameters",[]) if p["in"]=="header"}
        if method!="get":assert {"Origin","X-CSRF-Token","Idempotency-Key"}<=headers
        if identity in {"N13","N17","N19"}:assert "If-Match" in headers and "428" in op["responses"]
        if identity in {"N13","N17","N18"}:assert "ETag" in op["responses"]["200"]["headers"]
        if identity=="N18":assert "X-Invitation-Token" in headers and "requestBody" not in op
    models=schema["components"]["schemas"]
    assert set(models["GrantsRequest"]["properties"])=={"grants","reason"}
    assert models["CreateInvitation"]["additionalProperties"] is False
    assert set(models["AcceptInvitation"]["properties"])=={"token","accept"}
    assert models["AcceptInvitation"]["properties"]["token"]["writeOnly"]
    assert models["AcceptInvitation"]["properties"]["accept"]["const"] is True
    assert models["GrantsRequest"]["properties"]["grants"]["maxItems"] == 43
    assert "token" not in models["Invitation"]["properties"]
    assert set(models["AcceptanceReceipt"]["properties"])=={"invitation_id","invitation_version_at_acceptance","store_id","membership_id","role","accepted_grants","authorization_version_at_acceptance","accepted_at","event_id","next_action"}
