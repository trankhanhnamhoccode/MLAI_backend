from app.main import create_app
from app.config import Settings

def test_n6_n8_accepted_paths_typed_auth_and_cas_boundaries():
    schema=create_app(Settings(_env_file=None,import_worker_enabled=False)).openapi()
    for suffix,method,identity in (("/inventory/receipts","post","N6"),("/inventory/{ingredient_id}/threshold","put","N8")):
        operation=schema["paths"]["/api/v1/stores/{store_id}"+suffix][method]
        assert operation["operationId"]==identity and operation["security"]==[{"APIKeyCookie":[]}]
        assert "requestBody" in operation
        assert {"412","428","403","409"}<=set(operation["responses"])
        assert "Idempotency-Key" in {p["name"] for p in operation["parameters"]}
    request=schema["components"]["schemas"]["StockReceiptRequest"]
    assert request["additionalProperties"] is False
    assert "expected_inventory_version" in request["required"]
    assert request["properties"]["quantity"]["type"]=="string"
    assert request["properties"]["origin"]["enum"]==["OPENING_STOCK","ACTUAL_RECEIPT"]
