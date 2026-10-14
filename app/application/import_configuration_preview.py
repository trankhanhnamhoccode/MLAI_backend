"""Pure typed configuration identity/coverage/period preview over frozen facts."""
from datetime import date, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from app.application.contracts import import_domains as domains, import_mapping as dto
from app.application.import_identity import content_digest
from app.application.operational_import_facts import latest_source, current_fees, declaration_dependency

def semantic_configuration(value):
    """Decimal spelling does not create a new business revision."""
    from decimal import Decimal
    def decimal_text(number):
        text = format(number, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, dict):
        return {key: decimal_text(Decimal(item)) if key in {"amount", "maximum_quantity"} and item is not None
                else semantic_configuration(item) for key,item in value.items()}
    if isinstance(value, (tuple,list)):
        return [semantic_configuration(item) for item in value]
    return value

def changes_declaration_dependency(rows, declaration):
    """Same-batch explicit canonical writes invalidate a previous declaration hash."""
    for row in rows:
        if row.blockers or row.after is None or row.proposed_action in {"NO_OP","REUSE_RECEIPT"}:continue
        value=row.after
        if declaration.kind=="INVENTORY":
            if value.domain in {"inventory_count", "opening_stock", "inventory_receipts"} and value.ingredient_id==declaration.ingredient_id:return True
            if value.domain=="ingredients" and any(r.canonical_id==declaration.ingredient_id for r in row.entity_refs):return True
        elif declaration.kind=="SALES_COVERAGE":
            if value.domain=="sales" and value.product_id in declaration.product_ids and declaration.from_date<=value.sales_date<=declaration.to_date:return True
            if value.domain=="products" and any(r.canonical_id in declaration.product_ids for r in row.entity_refs):return True
        elif value.domain in {"ingredients","suppliers"} and row.proposed_action.startswith("CREATE_"):return True
    return False


def finish_configurations(rows, specs, snapshot, normalized, now, store_timezone):
    from app.application.import_preview import notice
    today = now.astimezone(ZoneInfo(store_timezone)).date()
    result, amendments = [], []
    supplier_refs = {(r["source_system_key"],r["source_record_key"]):r["supplier_id"]
                     for r in snapshot.get("supplier_source_records",())}
    for row in rows:
        if not row.after:
            continue
        spec = specs[str(row.source_location.sheet_id)]
        system = spec.scope.source_system_key
        if row.after.domain == "suppliers":
            ident=next((r.canonical_id for r in row.entity_refs if r.entity=="supplier"),None)
            if ident:supplier_refs[system,row.after.source_supplier_key]=str(ident)
    for row in rows:
        value=row.after
        if value is None:
            result.append(row);continue
        spec=specs[str(row.source_location.sheet_id)];system=spec.scope.source_system_key
        blockers=list(row.blockers);nested=list(row.nested_references);proofs=list(row.nested_provenance)
        changes={}
        def block(code):blockers.append(notice(code,row.source_location))
        if isinstance(value,domains.SupplierSource):
            old=next((r for r in snapshot.get("supplier_source_records",()) if
                (r["source_system_key"],r["source_record_key"])==(system,value.source_supplier_key)),None)
            ident=next((r.canonical_id for r in row.entity_refs if r.entity=="supplier"),None)
            if old and str(ident)!=old["supplier_id"]:block("SOURCE_IDENTITY_CONFLICT")
        elif isinstance(value,domains.FeeSource):
            # Resolve dated canonical offer versions, not the first registry UUID.
            fee_terms={}
            closing={str(r.target_reserved_or_existing_id):r.after.effective_to for r in rows
                     if r.after and r.proposed_action=="AMEND_TERM_PERIOD"}
            for record in snapshot.get("term_source_records",()):
                term=next((r for r in snapshot["supplier_terms"] if r["id"]==record["id"]),None)
                if not term:continue
                end=closing.get(term["id"],date.fromisoformat(term["effective_to"]) if term["effective_to"] else date.max)
                if date.fromisoformat(term["effective_from"])<=(value.effective_to or date.max) and value.effective_from<=end:
                    fee_terms.setdefault((record["source_system_key"],record["source_record_key"]),set()).add(term["id"])
            for candidate in rows:
                if candidate.after and candidate.after.domain=="supplier_terms" and candidate.proposed_action!="AMEND_TERM_PERIOD":
                    term=candidate.after
                    if term.effective_from<=(value.effective_to or date.max) and value.effective_from<=(term.effective_to or date.max):
                        namespace=specs[str(candidate.source_location.sheet_id)].scope.source_system_key,term.source_term_key
                        fee_terms.setdefault(namespace,set()).add(str(candidate.target_reserved_or_existing_id))
            # Every component must bind typed canonical identities even when coverage UNKNOWN.
            for index,key in enumerate(value.covered_source_term_keys):
                identifiers=fee_terms.get((system,key),())
                if identifiers:nested.extend(dto.EntityRef(entity="supplier_term",canonical_id=UUID(ident),path=f"covered_source_term_keys[{index}]") for ident in sorted(identifiers))
                else:block("UNKNOWN_TERM_SOURCE")
            for index,key in enumerate(value.covered_source_supplier_keys):
                ident=supplier_refs.get((system,key))
                if ident:nested.append(dto.EntityRef(entity="supplier",canonical_id=UUID(ident),path=f"covered_source_supplier_keys[{index}]"))
                else:block("UNKNOWN_SUPPLIER_SOURCE")
            for index,c in enumerate(value.components):
                identifiers=fee_terms.get((system,c.source_term_key),()) if c.source_term_key else (supplier_refs.get((system,c.source_supplier_key)),)
                if not identifiers or any(i is None for i in identifiers):block("INVALID_FEE_REFERENCE")
                else:nested.extend(dto.EntityRef(entity="supplier_term" if c.source_term_key else "supplier",canonical_id=UUID(ident),
                    path=f"components[{index}]."+("source_term_key" if c.source_term_key else "source_supplier_key")) for ident in sorted(identifiers))
                origin=next(p for p in row.provenance if p.field=="components")
                proofs.append(dto.NestedRecordProvenance(path=f"components[{index}]",source_location=row.source_location,
                    provenance={k:dto.ProvenanceValue(**origin.model_dump(exclude={"field"})) for k in type(c).model_fields}))
            eligible={r["id"] for r in snapshot["supplier_terms"] if r["active"]
                and r["effective_from"] <= str(value.effective_to or date.max)
                and (r["effective_to"] is None or str(value.effective_from)<=r["effective_to"])}
            # Explicit reviewed amendments supply the effective end in this preview.
            for amended in rows:
                if amended.proposed_action=="AMEND_TERM_PERIOD" and amended.after.effective_to < value.effective_from:
                    eligible.discard(str(amended.target_reserved_or_existing_id))
            planned={str(r.target_reserved_or_existing_id) for r in rows if
                r.after and r.after.domain=="supplier_terms" and r.proposed_action!="AMEND_TERM_PERIOD"
                and r.after.active and r.after.effective_from <= (value.effective_to or date.max)
                and value.effective_from <= (r.after.effective_to or date.max)}
            covered={ident for key in value.covered_source_term_keys for ident in fee_terms.get((system,key),())}
            if value.coverage=="COMPLETE" and not (eligible | planned) <= covered:block("FEE_COVERAGE_INCOMPLETE")
            needed={r["supplier_id"] for r in snapshot["supplier_terms"] if r["id"] in eligible} | {
                str(r.after.supplier_id) for r in rows if r.after and r.after.domain=="supplier_terms"
                and str(r.target_reserved_or_existing_id) in planned}
            bound={supplier_refs[system,k] for k in value.covered_source_supplier_keys if (system,k) in supplier_refs}
            if value.coverage=="COMPLETE" and not needed<=bound:block("FEE_COVERAGE_INCOMPLETE")
            old=latest_source(snapshot,"payable_fee_records",system,value.source_fee_key)
            equal=old and content_digest(semantic_configuration(old["payload"]))==content_digest(semantic_configuration(value.model_dump(mode="json")))
            if equal:
                changes.update(before=domains.FeeSource.model_validate(old["payload"], context={"retained_evidence": True}),classification="UNCHANGED",
                    proposed_action="NO_OP",target_reserved_or_existing_id=UUID(old["id"]),expected_version=old["_row_version"])
            else:
                if old:
                    changes.update(before=domains.FeeSource.model_validate(old["payload"], context={"retained_evidence": True}),classification="CHANGED",confirmation_required=True,
                        required_permissions=("supplier.fees.manage",))
                    if value.effective_from<=today or value.effective_from<=date.fromisoformat(old["payload"]["effective_from"]):block("HISTORICAL_FEE_CORRECTION")
                for existing in current_fees(snapshot):
                    p=existing["payload"]
                    if p["effective_from"] > str(value.effective_to or date.max) or (p["effective_to"] and str(value.effective_from)>p["effective_to"]):continue
                    amendment=next((a for a in spec.fee_period_amendments if str(a.fee_id)==existing["id"]),None)
                    if value.effective_from<=today or value.effective_from<=date.fromisoformat(p["effective_from"]):block("HISTORICAL_FEE_CORRECTION")
                    elif amendment is None:block("FEE_PERIOD_OVERLAP")
                    elif amendment.expected_version!=existing["_row_version"] or p["effective_to"] is not None or amendment.effective_to!=value.effective_from-timedelta(days=1):block("FEE_AMENDMENT_CONFLICT")
                    else:
                        previous=domains.FeeSource.model_validate(p, context={"retained_evidence": True})
                        amendments.append(dto.PreviewRow(row_id=uuid4(),source_location=row.source_location,
                            classification="CHANGED",proposed_action="AMEND_FEE_PERIOD",before=previous,
                            after=previous.model_copy(update={"effective_to":amendment.effective_to}),
                            entity_refs=(dto.EntityRef(entity="fee",canonical_id=UUID(existing["id"])),),
                            target_reserved_or_existing_id=uuid4(),expected_version=existing["_row_version"],
                            required_permissions=("supplier.fees.manage",),confirmation_required=True,
                            provenance=(dto.FieldProvenance(field="effective_to",origin="DETERMINISTIC_DERIVED",applied_rule_ids=("owner_reviewed_fee_period_amendment",)),)))
            duplicate=[r for r in rows if r is not row and r.after and r.after.domain=="payable_fees" and
                r.after.effective_from<= (value.effective_to or date.max) and value.effective_from <= (r.after.effective_to or date.max)]
            if duplicate:block("FEE_PERIOD_OVERLAP")
        elif isinstance(value,domains.DeclarationSource):
            d=value.declaration
            if isinstance(d,domains.InventoryDeclaration):
                counts={str(r.after.lot_id):r.after for r in rows if r.after and r.after.domain=="inventory_count" and not r.blockers}
                openings={str(r.after.lot_id):r.after for r in rows if r.after and r.after.domain=="opening_stock" and not r.blockers}
                openings.update({str(r.receipt_effect.lot_id):r.after for r in rows if r.after and r.after.domain=='inventory_receipts'
                    and r.receipt_effect and not r.blockers})
                from decimal import Decimal
                actual={r["id"] for r in snapshot["inventory_lots"] if r["ingredient_id"]==str(d.ingredient_id)} | {
                    key for key,value in openings.items() if value.ingredient_id==d.ingredient_id}
                if d.state=="COMPLETE_CURRENT_LOTS":
                    blockers=[n for n in blockers if n.code!="INVENTORY_COVERAGE_INCOMPLETE"]
                    if set(map(str,d.covered_lot_ids))!=actual:block("INVENTORY_COVERAGE_INCOMPLETE")
                empty=not d.covered_lot_ids and not any(value.ingredient_id==d.ingredient_id for value in openings.values()) and all(Decimal(counts[r["id"]].on_hand if r["id"] in counts else r["on_hand_quantity"])==0
                    for r in snapshot["inventory_lots"] if r["ingredient_id"]==str(d.ingredient_id))
                if d.state=="CONFIRMED_EMPTY" and not empty and not any(n.code=="INVENTORY_NOT_EMPTY" for n in blockers):block("INVENTORY_NOT_EMPTY")
                if d.state=="CONFIRMED_EMPTY" and empty and any(n.code=="INVENTORY_NOT_EMPTY" for n in blockers):
                    blockers=[n for n in blockers if n.code!="INVENTORY_NOT_EMPTY"]
                    changes.update(classification="NEW",proposed_action="SET_SCOPE_DECLARATION")
                if any(count.observed_at>d.observed_at for count in (*counts.values(), *openings.values()) if count.ingredient_id==d.ingredient_id):block("STALE_STOCK_OBSERVATION")
            old=latest_source(snapshot,"scope_declaration_records",system,value.source_declaration_key)
            dependency=declaration_dependency(snapshot,value.declaration)
            if old:
                previous=domains.DeclarationSource.model_validate(old["payload"])
                if previous.declaration.kind!=value.declaration.kind:block("DECLARATION_IDENTITY_CONFLICT")
                elif isinstance(value.declaration, domains.InventoryDeclaration) and previous.declaration.ingredient_id != value.declaration.ingredient_id:
                    block("DECLARATION_IDENTITY_CONFLICT")
                equal=content_digest(semantic_configuration(old["payload"]))==content_digest(semantic_configuration(value.model_dump(mode="json"))) and old["dependency_digest"]==dependency and not changes_declaration_dependency(rows,d)
                changes.update(before=previous,classification="UNCHANGED" if equal else "CHANGED",
                    proposed_action="NO_OP" if equal else "SET_SCOPE_DECLARATION",confirmation_required=not equal,
                    expected_version=old["_row_version"])
                if equal:changes["target_reserved_or_existing_id"]=UUID(old["id"])
            origin=next(p for p in row.provenance if p.field=="declaration")
            d=value.declaration
            if isinstance(d,domains.InventoryDeclaration):nested.extend(dto.EntityRef(entity="lot",canonical_id=i,path=f"declaration.covered_lot_ids[{index}]") for index,i in enumerate(d.covered_lot_ids))
            elif isinstance(d,domains.SalesDeclaration):nested.extend(dto.EntityRef(entity="product",canonical_id=i,path=f"declaration.product_ids[{index}]") for index,i in enumerate(d.product_ids))
            else:
                for collection in ("capacities","supplier_limits"):
                    for index,item in enumerate(getattr(d,collection)):
                        nested.append(dto.EntityRef(entity="ingredient",canonical_id=item.ingredient_id,path=f"declaration.{collection}[{index}].ingredient_id"))
                        if isinstance(item,domains.SupplierLimit):nested.append(dto.EntityRef(entity="supplier",canonical_id=item.supplier_id,path=f"declaration.{collection}[{index}].supplier_id"))
                        proofs.append(dto.NestedRecordProvenance(path=f"declaration.{collection}[{index}]",source_location=row.source_location,
                            provenance={k:dto.ProvenanceValue(**origin.model_dump(exclude={"field"})) for k in type(item).model_fields}))
        changes.update(nested_references=tuple(nested),nested_provenance=tuple(proofs),blockers=tuple(blockers))
        if blockers:changes.update(classification="CONFLICT",proposed_action="BLOCKED")
        result.append(row.model_copy(update=changes))
    # Duplicate external source keys in the same batch are conflicts, never last-row wins.
    seen=set()
    for index,row in enumerate(result):
        if not row.after or row.proposed_action.startswith("AMEND_"):continue
        value=row.after
        key=(getattr(value,"source_fee_key",None) or getattr(value,"source_declaration_key",None)
             or getattr(value,"source_supplier_key",None) or getattr(value,"source_term_key",None))
        if not key:continue
        namespace=(value.domain,specs[str(row.source_location.sheet_id)].scope.source_system_key,key)
        if namespace in seen:
            result[index]=row.model_copy(update={"classification":"CONFLICT","proposed_action":"BLOCKED",
                "blockers":row.blockers+(notice("SOURCE_IDENTITY_CONFLICT",row.source_location),)})
        seen.add(namespace)
    return tuple(amendments+result)
