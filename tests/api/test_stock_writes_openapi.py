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


def test_excel_receipt_uses_existing_operations_and_typed_inventory_effect():
    from app.application.import_descriptors import SCHEMAS, options
    schema = create_app(Settings(_env_file=None)).openapi()
    operations = {value['operationId'] for methods in schema['paths'].values()
                  for method, value in methods.items() if method in ('get','post','put','patch','delete')}
    assert len(operations) == 73 and len(schema['paths']) == 66
    assert len(SCHEMAS) == 15 and 'inventory_receipts' in SCHEMAS
    components = schema['components']['schemas']
    assert components['ActualReceiptValue']['properties']['origin']['const'] == 'ACTUAL_RECEIPT'
    assert {'receipt_effect'} <= components['PreviewRow']['properties'].keys()
    assert {'receipt_effect','receipt_reference'} <= components['CommitRowReference']['properties'].keys()
    assert {'receipt_id','lot_id','movement_id','audit_reference','action','source_identity'} <= set(components['ReceiptCommitReference']['required'])
    assert set(components['ReceiptEffect']['properties']['action']['enum']) == {'CREATE_RECEIPT','REUSE_RECEIPT','BLOCKED'}
    fields = {field.key: field for field in options('inventory_receipts')}
    assert fields['inventory_receipts.source_record_id'].label == 'Mã dòng nhận hàng ở nguồn'
    assert fields['inventory_receipts.quantity'].allowed_shared_scopes == ()
    assert fields['inventory_receipts.observed_at'].allowed_shared_scopes == ('IMPORT_VALUE',)
