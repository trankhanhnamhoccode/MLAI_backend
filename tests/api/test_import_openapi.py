"""Wire inventory and public contract variants; no DB required."""

from app.config import Settings
from app.main import create_app


def test_import_operations_and_typed_variants_preserve_boundaries():
    spec = create_app(Settings(_env_file=None)).openapi()
    wanted = {
        "I01": ("post", "/stores/{store_id}/imports", 201),
        "I02": ("post", "/imports/{import_id}/files", 200),
        "I03": ("post", "/imports/{import_id}/analyze", 202),
        "I04": ("get", "/imports/{import_id}", 200),
        "I06": ("get", "/imports/{import_id}/completion", 200),
        "M01": ("get", "/imports/{import_id}/mapping-summary", 200),
        "M02": ("get", "/imports/{import_id}/mappings", 200),
        "M03": ("get", "/imports/{import_id}/sheets/{sheet_id}/field-options", 200),
        "M04": ("patch", "/imports/{import_id}/mappings/{mapping_id}", 200),
        "N5": (
            "post",
            "/stores/{store_id}/mapping-profiles/{profile_id}/decisions",
            200,
        ),
        "I05": ("post", "/imports/{import_id}/process", 202),
        "J01": ("get", "/jobs/{job_id}", 200),
    }
    for ident, (method, path, status) in wanted.items():
        operation = spec["paths"]["/api/v1" + path][method]
        assert (
            operation["operationId"] == ident and str(status) in operation["responses"]
        )
        assert "401" in operation["responses"] and "403" in operation["responses"]
        if ident in {"I01", "I02", "I03", "I04", "M01", "M04", "N5", "I05"}:
            assert "ETag" in operation["responses"][str(status)]["headers"]
    schemas = spec["components"]["schemas"]
    # C1 adds NF01--03; C2 adds PR01--04/MQ01--03 and extends N5.
    assert len([1 for path in spec['paths'].values() for method in path if method in {'get','post','put','patch','delete'}])==73
    assert 'history_corrections' in schemas['app__application__contracts__import_mapping__CommitRequest']['properties']
    assert 'history_record' in schemas['CommitRowReference']['properties']
    assert schemas['HistoryCorrectionConfirmation']['required']==['row_id','expected_version','reason']
    assert 'calendar_events' in schemas['SheetTypeResolution']['properties']['sheet_type']['anyOf'][0]['enum']
    assert schemas['StoreContext']['properties']['permission_catalog_version']['const']=='permissions-v3'
    assert schemas['PurchaseHistorySource']['properties']['price_basis']['enum']==['PER_QUANTITY','LINE_TOTAL','UNKNOWN']
    line = schemas["RecipeLineProvenance"]["properties"]
    assert line["quantity_basis"]["anyOf"][0]["enum"] == ["PER_SERVING", "WHOLE_BATCH"]
    assert "source_value" in schemas["ProvenanceValue"]["properties"]
    semantics = schemas["SupplierTermSemantics"]["properties"]
    assert semantics["price_basis"]["enum"] == ["PER_PACK", "PER_QUANTITY"]
    assert semantics["moq_basis"]["enum"] == ["PACKS", "PHYSICAL_QUANTITY"]
    assert "supplier_term_semantics" in schemas["PreviewRow"]["properties"]
    assert "supplier_term_semantics" in schemas["CommitRowReference"]["properties"]
    assert "inventory_effect" in schemas["PreviewRow"]["properties"]
    assert 'sales_contributions' in schemas['PreviewRow']['properties']
    assert 'sales_contributions' in schemas['CommitRowReference']['properties']
    stockout = schemas['SalesSource']['properties']['is_stockout']
    assert {p['type'] for p in stockout['anyOf']} == {'boolean', 'null'}
    assert schemas['SourceContext']['properties']['missing_stockout']['anyOf'][0]['enum'] == ['quantity_only', 'not_provided']
    assert 'stockout_aliases' in schemas['SourceContext']['properties']
    assert "inventory_effect" in schemas["CommitRowReference"]["properties"]
    assert schemas["OpeningValue"]["properties"]["domain"]["const"] == "opening_stock"
    assert "lot_id" in schemas["OpeningValue"]["required"]
    assert "opening_stock" in schemas["SheetTypeResolution"]["properties"]["sheet_type"]["anyOf"][0]["enum"]
    assert "price_basis" not in schemas["TermValue"]["properties"]
    context = schemas["SourceContext"]
    assert set(context["required"]) == {
        "kind",
        "source_system_key",
        "report_type",
        "evidence_reference",
    }
    assert (
        context["properties"]["source_system_key"]["pattern"]
        == "^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    assert (
        schemas["SourceProvenance"]["properties"]["verification"]["const"]
        == "USER_DECLARED"
    )
    assert schemas["PreviewSummary"]["properties"]["can_commit"]["type"] == "boolean"
    assert (
        schemas["JobView"]["properties"]["result"]["anyOf"][0]["discriminator"][
            "propertyName"
        ]
        == "resource_type"
    )
    assert spec["paths"]["/api/v1/imports/{import_id}/completion"]["get"]["operationId"] == "I06"
    process = spec["paths"]["/api/v1/imports/{import_id}/process"]["post"]
    accepted = process["responses"]["202"]["content"]["application/json"]["schema"]["anyOf"]
    assert {r["$ref"].split("/")[-1] for r in accepted} == {"ImportEnvelope_PreviewAccepted_", "ImportEnvelope_CommitAccepted_"}
    assert process["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("ImportEnvelope_ConfirmationResult_")
    assert "ETag" in process["responses"]["200"]["headers"]
    assert (
        schemas["ConfirmReviewRequest"]["properties"]["phase"]["const"]
        == "confirm_review"
    )
    assert schemas["ConfirmationResult"]["properties"]["canonical_commit_supported"]["type"] == "boolean"
    assert (
        "classification" in schemas["MappingIssue"]["properties"]["issue_type"]["enum"]
    )
    assert "schemas" in schemas["FieldOptions"]["properties"]
    assert "confirmation_usable" in schemas["ImportRead"]["properties"]
    assert "quota" in schemas["ImportRead"]["required"]
    assert schemas["ImportRead"]["properties"]["quota"]["$ref"].endswith("/ImportQuota")
    assert set(schemas["ImportQuota"]["required"]) == {
        "accepted_file_count", "accepted_total_bytes", "remaining_file_slots", "remaining_bytes"
    }
    assert all(field["type"] == "integer" and field["minimum"] == 0
               for field in schemas["ImportQuota"]["properties"].values())
    assert not any("/confirm" in path for path in spec["paths"])
