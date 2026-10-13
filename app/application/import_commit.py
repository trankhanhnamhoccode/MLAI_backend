"""S4.5 frozen commit plan and explicit transaction-owned canonical writer adapters."""

from decimal import Decimal
from uuid import UUID
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from app.application.contracts import import_mapping as dto
from app.application.contracts.catalog import CreateProductInput, CreateIngredientInput
from app.application.contracts.recipe import CreateRecipeVersionInput
from app.application.contracts.sales import RecordDailySalesInput
from app.application.contracts.auth import AuthError
from app.application.errors import ApplicationError
from app.application.use_cases.catalog import ProductUseCases, IngredientUseCases
from app.application.use_cases.recipe import RecipeUseCases
from app.application.use_cases.sales import SalesUseCases
from app.application.use_cases.inventory import InventoryUseCases
from app.application.contracts.inventory import AdjustInventoryInput
from app.application.import_preview import exact_text
from fractions import Fraction
from app.application.use_cases.operational_configuration import OperationalConfiguration
from app.application.operational_import_facts import declaration_dependency
from app.repositories.import_staging import read_set_in_session
from app.models.operational_import import SupplierSourceRecord, TermSourceRecord, PayableFeeRecord, ScopeDeclarationRecord, InventoryAudit
from uuid import uuid4
from datetime import datetime, timezone
from app.application.import_identity import content_digest
from app.application.import_sales_sources import sources_for, latest_source

SUPPORTED = frozenset({"products", "ingredients", "sales", "recipes", "inventory_count", "opening_stock", "suppliers", "supplier_terms", "payable_fees", "scope_declarations"})


def commit_rows(preview, body):
    try:
        rows = tuple(dto.PreviewRow.model_validate(r) for r in preview.content_json["rows"])
    except ValidationError as error:
        if any(any(key in issue["loc"] for key in ("price","pack_cost","amount")) for issue in error.errors(include_input=False)):
            raise AuthError("LEGACY_MONEY_REVIEW_REQUIRED",409) from None
        raise AuthError("SOURCE_INTEGRITY_ERROR",409) from None
    if any((r.canonical_domain or (r.after.domain if r.after else None)) not in SUPPORTED for r in rows):
        raise AuthError("SCHEMA_BLOCKED", 409)
    if preview.content_json["summary"]["blockers"] or any(r.blockers or not r.after for r in rows):
        raise AuthError("PREVIEW_BLOCKED", 409)
    # Validate the retained effective plan, not client-declared intent. Source/action
    # reasons remain separate evidence; review confirmation does not replace this.
    reason_actions = {"REPLACE_DAILY_TOTAL", "MERGE_DISJOINT_SALES", "COUNT_CORRECTION",
                      "AMEND_TERM_PERIOD", "AMEND_FEE_PERIOD"}
    if any(r.proposed_action in reason_actions for r in rows) and not body.reason:
        raise AuthError("COMMIT_REASON_REQUIRED", 422)
    required = {r.row_id: r for r in rows if r.confirmation_required and r.after.domain == "sales"}
    resolutions = {r.row_id: r for r in body.resolutions}
    if len(resolutions) != len(body.resolutions) or set(resolutions) != set(required):
        raise AuthError("INVALID_IMPORT_CONFIGURATION", 422)
    for ident, row in required.items():
        resolution = resolutions[ident]
        expected = "confirm_disjoint_merge" if row.proposed_action == "MERGE_DISJOINT_SALES" else "replace_daily_total"
        if (resolution.action != expected or resolution.report_business_key != row.after.business_report_key
                or (expected == "confirm_disjoint_merge" and resolution.disjoint_assertion is not True)
                or (expected == "replace_daily_total" and resolution.disjoint_assertion is True)):
            raise AuthError("SALES_OVERLAP_UNRESOLVED", 409)
    required_supplier = {r.row_id for r in rows if r.confirmation_required and r.after.domain in {"supplier_terms","payable_fees"}}
    confirmed_supplier = {r.action_id for r in body.supplier_changes}
    if len(confirmed_supplier) != len(body.supplier_changes) or confirmed_supplier != required_supplier:
        raise AuthError("INVALID_IMPORT_CONFIGURATION",422)
    return rows


def effective_digest(preview, body, confirmation):
    return content_digest(dict(preview_id=str(preview.id), preview_digest=preview.digest,
                               confirmation_digest=confirmation.content_digest,
                               request=body.model_dump(mode="json")))


def write_rows(session, store_id, rows, specs, snapshot, body, *, actor_id=None, recorded_at=None):
    """No commit/rollback here. Caller fences read-set and persists atomic receipts."""
    from app.application.import_dependencies import order_dependencies
    ordered = order_dependencies(rows)
    completed = set()
    sources, references = [], []
    inserted = changed = noops = products = ingredients = added_sales = changed_sales = recipes = 0
    affected_products = set()
    affected_ingredients = set()
    inventory_changes = 0
    configuration_impacts = {k:dict(created=0,changed=0) for k in ("suppliers","terms","fees","declarations")}
    configuration = OperationalConfiguration(session,store_id)
    for row in ordered:
        if not set(row.dependencies) <= completed:
            raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
        value = row.after
        data = value.model_dump(exclude={"domain", "source_business_key"})
        canonical_id = None
        movement_ids = ()
        canonical_version = None
        try:
            if value.domain in {"products", "ingredients"}:
                kind = "product" if value.domain == "products" else "ingredient"
                refs = [r.canonical_id for r in row.entity_refs if r.entity == kind]
                if len(refs) != 1:
                    raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
                canonical_id = refs[0]
                if row.proposed_action != "NO_OP":
                    if row.proposed_action != "CREATE_" + kind.upper():
                        raise AuthError("PREVIEW_BLOCKED", 409)
                    writer, contract = ((ProductUseCases(session), CreateProductInput)
                                        if kind == "product" else (IngredientUseCases(session), CreateIngredientInput))
                    writer.create_in_transaction(contract(store_id=store_id, **data), reserved_id=canonical_id)
                    products += kind == "product"
                    ingredients += kind == "ingredient"
                    inserted += 1
                    if kind == "product":
                        affected_products.add(canonical_id)
            elif value.domain == "recipes":
                if row.proposed_action == "NO_OP":
                    from app.repositories.recipe import RecipeRepository
                    old = [r for r in RecipeRepository(session).list_recipe_versions(store_id, value.product_id)
                           if r.version == value.version]
                    if len(old) != 1:
                        raise AuthError("PREVIEW_STALE", 409)
                    canonical_id = old[0].id
                else:
                    if row.proposed_action != "CREATE_RECIPE_VERSION":
                        raise AuthError("PREVIEW_BLOCKED", 409)
                    data.pop("yield_unit")
                    result = RecipeUseCases(session).create_in_transaction(CreateRecipeVersionInput(store_id=store_id, **data))
                    canonical_id = result.id
                    recipes += 1
                    inserted += 1
                    affected_products.add(value.product_id)
            elif value.domain == "suppliers":
                canonical_id = next(r.canonical_id for r in row.entity_refs if r.entity=="supplier")
                create=row.proposed_action=="CREATE_SUPPLIER"
                if row.proposed_action not in {"CREATE_SUPPLIER","NO_OP"}:raise AuthError("PREVIEW_BLOCKED",409)
                configuration.supplier(value,canonical_id,specs[str(row.source_location.sheet_id)].scope.source_system_key,
                    dict(row=row.model_dump(mode="json"),spec=specs[str(row.source_location.sheet_id)].model_dump(mode="json")),create=create)
                if create:inserted+=1;configuration_impacts["suppliers"]["created"]+=1
            elif value.domain == "supplier_terms":
                canonical_id=row.target_reserved_or_existing_id
                system=specs[str(row.source_location.sheet_id)].scope.source_system_key
                provenance=dict(row=row.model_dump(mode="json"),spec=specs[str(row.source_location.sheet_id)].model_dump(mode="json"))
                if row.proposed_action=="AMEND_TERM_PERIOD":
                    configuration.close_term(canonical_id,value.effective_to)
                    changed+=1;configuration_impacts["terms"]["changed"]+=1
                elif row.proposed_action=="CREATE_SUPPLIER_TERM":
                    result=configuration.term(value,canonical_id,system,provenance)
                    canonical_version=str(result.version)
                    inserted+=1;configuration_impacts["terms"]["created"]+=1
                elif row.proposed_action=="REGISTER_TERM_SOURCE":
                    session.add(TermSourceRecord(id=canonical_id,store_id=store_id,source_system_key=system,
                        source_record_key=value.source_term_key,payload=value.model_dump(mode="json"),provenance=provenance));session.flush()
                    inserted+=1;configuration_impacts["terms"]["created"]+=1
                elif row.proposed_action!="NO_OP":raise AuthError("PREVIEW_BLOCKED",409)
                if canonical_version is None:
                    from app.models import SupplierTerm
                    canonical_version=str(session.get(SupplierTerm,canonical_id).version)
            elif value.domain == "payable_fees":
                canonical_id=row.target_reserved_or_existing_id
                system=specs[str(row.source_location.sheet_id)].scope.source_system_key
                refs=dict(terms=[str(r.canonical_id) for r in row.nested_references if r.entity=="supplier_term"],
                          suppliers=[str(r.canonical_id) for r in row.nested_references if r.entity=="supplier"],
                          bindings=[r.model_dump(mode="json") for r in row.nested_references])
                if row.proposed_action=="AMEND_FEE_PERIOD":
                    previous_id=next(r.canonical_id for r in row.entity_refs if r.entity=="fee")
                    previous=session.get(PayableFeeRecord,previous_id)
                    if previous is None or previous.store_id!=store_id:raise AuthError("PREVIEW_STALE",409)
                    refs=previous.resolved_references
                elif row.proposed_action not in {"CREATE_FEE_DECLARATION","NO_OP"}:raise AuthError("PREVIEW_BLOCKED",409)
                if row.proposed_action!="NO_OP":
                    configuration.fee(value,canonical_id,system,dict(row=row.model_dump(mode="json"),spec=specs[str(row.source_location.sheet_id)].model_dump(mode="json")),refs)
                    if row.proposed_action=="AMEND_FEE_PERIOD":changed+=1;configuration_impacts["fees"]["changed"]+=1
                    else:inserted+=1;configuration_impacts["fees"]["created"]+=1
                canonical_version=str(session.get(PayableFeeRecord,canonical_id).version)
            elif value.domain == "scope_declarations":
                canonical_id=row.target_reserved_or_existing_id
                if row.proposed_action=="SET_SCOPE_DECLARATION":
                    post,_=read_set_in_session(session,store_id,snapshot["_captured_schemas"])
                    dependency=declaration_dependency(post,value.declaration)
                    configuration.declaration(value,canonical_id,specs[str(row.source_location.sheet_id)].scope.source_system_key,
                        dict(row=row.model_dump(mode="json"),spec=specs[str(row.source_location.sheet_id)].model_dump(mode="json")),dependency)
                    if row.classification=="CHANGED":changed+=1;configuration_impacts["declarations"]["changed"]+=1
                    else:inserted+=1;configuration_impacts["declarations"]["created"]+=1
                elif row.proposed_action!="NO_OP":raise AuthError("PREVIEW_BLOCKED",409)
                canonical_version=str(session.get(ScopeDeclarationRecord,canonical_id).version)
            elif value.domain == "opening_stock":
                canonical_id = value.lot_id
                if row.proposed_action == "CREATE_OPENING_STOCK":
                    from app.application.import_opening_stock import write_opening
                    from zoneinfo import ZoneInfo
                    now = recorded_at or datetime.now(timezone.utc)
                    today = now.astimezone(ZoneInfo(snapshot["stores"][0]["timezone"])).date()
                    result = write_opening(session, store_id, row,
                        specs[str(row.source_location.sheet_id)].scope.source_system_key, actor_id, now, today)
                    movement_ids = (result.movement.id,)
                    inserted += 1
                    inventory_changes += 1
                    affected_ingredients.add(value.ingredient_id)
                elif row.proposed_action != "NO_OP":
                    raise AuthError("PREVIEW_BLOCKED", 409)
            elif value.domain == "inventory_count":
                canonical_id = value.lot_id
                if row.proposed_action == "COUNT_CORRECTION":
                    delta = exact_text(Fraction(Decimal(value.on_hand)) - Fraction(Decimal(row.before.on_hand)))
                    result = InventoryUseCases(session).adjust_in_transaction(AdjustInventoryInput(
                        store_id=store_id, lot_id=value.lot_id, quantity_delta=Decimal(delta), unit=value.unit,
                        movement_type="COUNT_CORRECTION", occurred_at=value.observed_at,
                        reference_type="IMPORT_COUNT", reference_id=str(row.row_id), note=value.reason))
                    movement_ids = (result.movement.id,)
                    if actor_id is not None:
                        session.add(InventoryAudit(id=uuid4(),store_id=store_id,actor_id=actor_id,
                            movement_id=result.movement.id,occurred_at=recorded_at or datetime.now(timezone.utc),
                            record_json=dict(origin="IMPORT_COUNT",before=row.before.model_dump(mode="json"),
                                after=value.model_dump(mode="json"),row_id=str(row.row_id))))
                    changed += 1
                    inventory_changes += 1
                    affected_ingredients.add(value.ingredient_id)
                elif row.proposed_action != "NO_OP":
                    raise AuthError("PREVIEW_BLOCKED", 409)
            elif value.domain == "sales":
                spec = specs[str(row.source_location.sheet_id)]
                source_quantity = row.normalized_source_quantity
                if source_quantity is None:
                    raise AuthError("PREVIEW_STALE", 409)
                data = RecordDailySalesInput(store_id=store_id, product_id=value.product_id,
                                            sales_date=value.sales_date, quantity=Decimal(value.quantity))
                writer = SalesUseCases(session)
                if row.proposed_action == "INSERT":
                    result = writer.record_in_transaction(data)
                    inserted += 1
                    added_sales += 1
                elif row.proposed_action in {"REPLACE_DAILY_TOTAL", "MERGE_DISJOINT_SALES"}:
                    result = writer.replace_in_transaction(data)
                    changed += 1
                    changed_sales += 1
                elif row.proposed_action == "NO_OP":
                    old = writer.sales.get_daily_sale(store_id, value.product_id, value.sales_date)
                    if old is None:
                        raise AuthError("PREVIEW_STALE", 409)
                    result = old
                else:
                    raise AuthError("PREVIEW_BLOCKED", 409)
                canonical_id = result.id
                history = sources_for(snapshot, value.product_id, value.sales_date)
                old_source = latest_source(history, spec.scope.source_system_key, value.business_report_key)
                if not old_source or Decimal(old_source["source_quantity"]) != Decimal(source_quantity):
                    resolution = next((r for r in body.resolutions if r.row_id == row.row_id), None)
                    sources.append(dict(
                        source_system_key=spec.scope.source_system_key, business_report_key=value.business_report_key,
                        product_id=str(value.product_id), sales_date=str(value.sales_date), semantics=spec.sales_semantics,
                        source_quantity=source_quantity, canonical_quantity=value.quantity, canonical_id=str(canonical_id),
                        source_revision=old_source["source_revision"] + 1 if old_source else 1,
                        canonical_revision=max((r["canonical_revision"] for r in history), default=0) + 1,
                        resolution=resolution.model_dump(mode="json") if resolution else None,
                        baseline=(dict(quantity=row.before.quantity,
                                       canonical_id=str(canonical_id),
                                       expected_version=next(r["_row_version"] for r in snapshot["sales_daily"]
                                                             if r["id"] == str(canonical_id)),
                                       evidence_reference=resolution.evidence_reference)
                                  if row.proposed_action == "MERGE_DISJOINT_SALES" and not history and resolution else None),
                    ))
            else:
                raise AuthError("SCHEMA_BLOCKED", 409)
        except AuthError as error:
            error.blockers = (dto.Notice(code=error.code, severity="ERROR", message=error.code,
                                        source_location=row.source_location),)
            raise
        except (ApplicationError, ValidationError) as error:
            failure = AuthError("PREVIEW_BLOCKED", 409)
            failure.blockers = (dto.Notice(code=failure.code, severity="ERROR", message=failure.code,
                                          source_location=row.source_location),)
            raise failure from error
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) in {"23505", "23P01", "23503", "23514"}:
                failure = AuthError("PREVIEW_STALE", 409)
                failure.blockers = (dto.Notice(code=failure.code, severity="ERROR", message=failure.code,
                                              source_location=row.source_location),)
                raise failure from error
            raise
        if row.proposed_action == "NO_OP":
            noops += 1
        completed.add(row.row_id)
        references.append(dto.CommitRowReference(
            row_id=row.row_id, canonical_domain=value.domain, canonical_id=canonical_id,
            source_location=row.source_location, source_locations=row.source_locations,
            line_provenance=row.line_provenance, movement_ids=movement_ids,
            supplier_term_semantics=row.supplier_term_semantics,
            inventory_effect=row.inventory_effect,
            nested_references=row.nested_references,nested_provenance=row.nested_provenance,canonical_version=canonical_version,
            provenance=row.model_dump(mode="json")["provenance"],
        ))
    return dict(inserted=inserted, changed=changed, noops=noops, products=products,
                ingredients=ingredients, added_sales=added_sales, changed_sales=changed_sales,
                recipes=recipes, affected_products=len(affected_products), inventory_changes=inventory_changes, affected_ingredients=len(affected_ingredients), configurations=configuration_impacts), tuple(references), sources
