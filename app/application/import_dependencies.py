"""Resolve explicit approved identities over the complete frozen batch plan."""
from collections import defaultdict

from app.application.contracts import import_mapping as dto


def finalize_dependencies(rows: tuple[dto.PreviewRow, ...]) -> tuple[dto.PreviewRow, ...]:
    masters = {"products": "product", "ingredients": "ingredient", "suppliers": "supplier", "opening_stock": "lot", "inventory_receipts": "lot"}
    candidates = defaultdict(list)
    skus = defaultdict(set)
    for row in rows:
        if row.after is None or row.after.domain not in masters:
            continue
        kind = masters[row.after.domain]
        sku = getattr(row.after, "sku", None)
        for ref in row.entity_refs:
            if ref.entity == kind:
                candidates[kind, ref.canonical_id].append(row)
                if sku:
                    skus[kind, sku].add(ref.canonical_id)
    result = []
    for row in rows:
        if row.after is None:
            result.append(row)
            continue
        blockers = list(row.blockers)
        dependencies = set(row.dependencies)
        own_kind = masters.get(row.after.domain) if row.after else None
        for ref in row.entity_refs + row.nested_references:
            targets = candidates.get((ref.entity, ref.canonical_id), ())
            if not targets:
                continue
            if len(targets) != 1:
                code = "AMBIGUOUS_BATCH_IDENTITY"
            elif any(len(skus[ref.entity, getattr(t.after, "sku", None)]) > 1 for t in targets if getattr(t.after, "sku", None)):
                code = "ENTITY_IDENTITY_CONFLICT"
            elif targets[0].blockers:
                if targets[0].row_id == row.row_id:
                    continue
                code = "BLOCKED_ENTITY_DEPENDENCY"
            else:
                if ref.entity != own_kind and targets[0].proposed_action != "NO_OP":
                    dependencies.add(targets[0].row_id)
                continue
            blockers.append(dto.Notice(code=code, severity="ERROR", entity=ref.entity,
                field=ref.path, message=code,
                impact="Review one canonical entity creation/binding; resolve its source facts before commit.",
                source_location=row.source_location))
        changes = dict(dependencies=tuple(sorted(dependencies, key=str)), blockers=tuple(blockers))
        if blockers:
            changes.update(classification="CONFLICT", proposed_action="BLOCKED")
        result.append(row.model_copy(update=changes))
    return tuple(result)


def order_dependencies(rows: tuple[dto.PreviewRow, ...]) -> tuple[dto.PreviewRow, ...]:
    """Stable domain priority among ready effects; dependencies take precedence."""
    from app.application.contracts.auth import AuthError
    from heapq import heappush, heappop
    rank = {"ingredients":0, "products":1, "suppliers":1, "supplier_terms":3,
        "recipes":4, "sales":5, "opening_stock":6, "inventory_receipts":6, "inventory_count":6,
        "payable_fees":7, "scope_declarations":8, "calendar_events":9,
        "promotion_observations":9, "usage_history":9, "purchase_history":9}
    indexed = {r.row_id:r for r in rows}
    if len(indexed) != len(rows) or any(not set(r.dependencies) <= indexed.keys() for r in rows):
        raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
    remaining = {r.row_id:len(set(r.dependencies)) for r in rows}
    consumers = defaultdict(list)
    ready = []
    def enqueue(row):
        heappush(ready, (2 if row.proposed_action.startswith("AMEND_") else rank[row.after.domain], str(row.row_id), row.row_id))
    for row in rows:
        for dependency in set(row.dependencies):
            consumers[dependency].append(row.row_id)
        if not remaining[row.row_id]:
            enqueue(row)
    ordered = []
    while ready:
        chosen = indexed[heappop(ready)[2]]
        ordered.append(chosen)
        for identity in consumers[chosen.row_id]:
            remaining[identity] -= 1
            if not remaining[identity]:
                enqueue(indexed[identity])
    if len(ordered) != len(rows):
        raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
    return tuple(ordered)
