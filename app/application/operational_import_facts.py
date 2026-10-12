"""Deterministic operational source identity and declaration dependency evidence."""
from app.application.import_identity import content_digest


def latest_source(snapshot, table, system, key):
    matches = [r for r in snapshot.get(table, ()) if r["source_system_key"] == system and r["source_record_key"] == key]
    versions = {r["id"]:r["version"] for r in snapshot.get("supplier_terms",())} if table == "term_source_records" else {}
    return max(matches, key=lambda r: versions.get(r.get("id"),r.get("version",0)), default=None)


def current_fees(snapshot):
    values = {}
    for record in snapshot.get("payable_fee_records", ()):
        key = (record["source_system_key"], record["source_record_key"], record["payload"]["effective_from"])
        if key not in values or values[key]["version"] < record["version"]:
            values[key] = record
    return tuple(values.values())


def inventory_dependency(snapshot, ingredient):
    ident = str(ingredient)
    return content_digest(dict(
        ingredient=[r for r in snapshot["ingredients"] if r["id"] == ident],
        lots=[{key:value for key,value in r.items() if key != "unit_cost"}
              for r in snapshot["inventory_lots"] if r["ingredient_id"] == ident],
    ))


def declaration_dependency(snapshot, declaration):
    if declaration.kind == "INVENTORY":
        return inventory_dependency(snapshot, declaration.ingredient_id)
    if declaration.kind == "SALES_COVERAGE":
        ids = set(map(str, declaration.product_ids))
        return content_digest(dict(products=[r for r in snapshot["products"] if r["id"] in ids],
            sales=[r for r in snapshot["sales_daily"] if r["product_id"] in ids
                and str(declaration.from_date) <= r["sales_date"] <= str(declaration.to_date)]))
    return content_digest(dict(ingredients=snapshot["ingredients"], suppliers=snapshot["suppliers"]))
