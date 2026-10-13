from app.main import create_app
from app.config import Settings

READS = {
    "/products": "P01",
    "/products/{product_id}": "P02",
    "/inventory": "V01",
    "/inventory/{ingredient_id}": "V02",
    "/inventory/{ingredient_id}/lots": "V03",
    "/inventory/{ingredient_id}/movements": "V04",
}


def test_s43_exact_operations_typed_outputs_and_errors():
    schema = create_app(Settings(_env_file=None)).openapi()
    for suffix, identity in READS.items():
        path = "/api/v1/stores/{store_id}" + suffix
        assert set(schema["paths"][path]) == {"get"}
        operation = schema["paths"][path]["get"]
        assert operation["operationId"] == identity and operation["security"] == [
            {"APIKeyCookie": []}
        ]
        assert "requestBody" not in operation
        for status in ("200", "401", "403", "409", "422", "503"):
            headers = operation["responses"][status]["headers"]
            assert headers["Cache-Control"]["schema"]["enum"] == ["private, no-store"]
            assert headers["X-Request-ID"]["schema"]["format"] == "uuid"
        assert (
            "Envelope"
            in operation["responses"]["200"]["content"]["application/json"]["schema"][
                "$ref"
            ]
        )
        assert operation["responses"]["422"]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/ReadErrorEnvelope"}
    quantity = schema["components"]["schemas"]["IngredientStock"]["properties"][
        "on_hand_quantity"
    ]
    assert quantity["type"] == "string" and quantity["pattern"]
    assert schema["components"]["schemas"]["LotRead"]["properties"]["cost"][
        "$ref"
    ].endswith("/LotCost")
