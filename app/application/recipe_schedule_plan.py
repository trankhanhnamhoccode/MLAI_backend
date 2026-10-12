"""CAT12 retained proposal construction; no canonical writes or computation engine."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from app.application.contracts import recipe_schedule as dto
from app.application.contracts.auth import AuthError
from app.domain.recipe_calendar import Period, history_unchanged, overlaps, gaps, changed_ranges
from app.application.import_identity import content_digest

READS = ("menu.read", "recipe.read", "ingredient.read")


def exact(value: str) -> str:
    # format/strip, never Decimal.normalize or context-sensitive arithmetic.
    text = format(Decimal(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def state(assignment: dto.Assignment | None, today: date) -> str:
    if assignment is None:
        return "unassigned"
    if assignment.effective_from > today:
        return "scheduled"
    if assignment.effective_to is not None and assignment.effective_to < today:
        return "past"
    return "in_effect"


def item_order(item: dto.ScheduleItem):
    return (item.assignment is None, item.assignment.effective_from if item.assignment else date.max,
            item.content.version, str(item.content.recipe_id))


def periods(items):
    return tuple(Period(i.content.recipe_id, i.assignment.effective_from, i.assignment.effective_to)
                 for i in items if i.assignment is not None)


def notice(code, product, *, field="assignment", ranges=(), ingredient=None):
    return dto.Notification(code=code, message=code, details=dto.NoticeDetails(
        entity="ingredient" if ingredient else "product", entity_id=ingredient or product,
        field=field, affected_dates=tuple(dict.fromkeys(d for a,b in ranges for d in (a,b) if d is not None)),
        affected_ranges=tuple(dto.DateRange(from_date=a, to_date=b) for a,b in ranges)))


def normalized_request(body: dto.PreviewRequest | dto.CommitRequest):
    data = body.model_dump(mode="json")
    if isinstance(body, dto.PreviewRequest):
        for r in data["new_recipes"]:
            for key in ("yield_quantity", "process_loss_rate"):
                r[key] = exact(r[key])
            for line in r["ingredients"]:
                line["quantity"] = exact(line["quantity"])
            r["ingredients"].sort(key=lambda l:l["ingredient_id"])
        data["new_recipes"].sort(key=lambda r:r["client_reference"])
        data["operations"].sort(key=lambda o:content_digest(o["recipe_ref"]))
    else:
        data["acknowledged_warning_codes"].sort()
    return data


def propose(body: dto.PreviewRequest, *, store: UUID, product: UUID, today: date, now,
            before: tuple[dto.ScheduleItem, ...], selling_unit: str, ingredients,
            schedule_version: str, catalog_version: str) -> dto.Preview:
    if today == date.max:
        raise AuthError("INVALID_DATE_RANGE", 422)
    minimum = today + timedelta(days=1)
    next_version = max((i.content.version for i in before), default=0) + 1
    new = {}
    warnings = []
    blockers = []
    for value in sorted(body.new_recipes, key=lambda r:r.client_reference):
        if value.client_reference in new:
            raise AuthError("INVALID_RECIPE_REFERENCE", 422)
        if value.yield_unit != selling_unit:
            raise AuthError("INVALID_UNIT", 422)
        lines = []
        for line in sorted(value.ingredients, key=lambda l:str(l.ingredient_id)):
            ingredient = ingredients.get(line.ingredient_id)
            if ingredient is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            if line.unit != ingredient["base_unit"]:
                raise AuthError("INVALID_UNIT", 422)
            if not ingredient["active"]:
                warnings.append(notice("INGREDIENT_INACTIVE", product, ingredient=line.ingredient_id, field="ingredient_id"))
            lines.append(dto.ContentLine(recipe_line_id=uuid4(), ingredient_id=line.ingredient_id,
                quantity=exact(line.quantity), unit=line.unit))
        if next_version > 2147483647:
            raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
        new[value.client_reference] = dto.Content(recipe_id=uuid4(), version=next_version,
            yield_quantity=exact(value.yield_quantity), yield_unit=value.yield_unit,
            process_loss_rate=exact(value.process_loss_rate), ingredients=tuple(lines))
        next_version += 1
    after = {i.content.recipe_id: i for i in before}
    used = set()
    used_new = set()
    for op in body.operations:
        if isinstance(op.recipe_ref, dto.NewRef):
            content = new.get(op.recipe_ref.new_recipe_reference)
            if content is None:
                raise AuthError("INVALID_RECIPE_REFERENCE", 422)
            rid = content.recipe_id
            used_new.add(op.recipe_ref.new_recipe_reference)
            previous = None
        else:
            rid = op.recipe_ref.recipe_id
            previous = after.get(rid)
            if previous is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            content = previous.content
        if rid in used:
            raise AuthError("INVALID_RECIPE_REFERENCE", 422)
        used.add(rid)
        if isinstance(op, dto.Withdraw):
            if previous.assignment is None or previous.assignment.effective_from <= today:
                blockers.append(notice("HISTORY_CHANGE_NOT_ALLOWED", product))
            assignment = None
        else:
            if op.effective_to is not None and op.effective_to < op.effective_from:
                raise AuthError("INVALID_DATE_RANGE", 422)
            assignment = dto.Assignment(effective_from=op.effective_from, effective_to=op.effective_to)
            if previous and previous.state == "past" and assignment != previous.assignment:
                blockers.append(notice("HISTORY_CHANGE_NOT_ALLOWED", product))
            if (previous is None or previous.assignment is None) and op.effective_from <= today:
                blockers.append(notice("HISTORY_CHANGE_NOT_ALLOWED", product))
        after[rid] = dto.ScheduleItem(content=content, assignment=assignment, state=state(assignment,today))
    if set(new) != used_new:
        raise AuthError("INVALID_RECIPE_REFERENCE", 422)
    outcome = tuple(sorted(after.values(), key=item_order))
    if sum(i.state == "scheduled" for i in outcome) > 1000:
        raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
    if not history_unchanged(periods(before), periods(outcome), today):
        blockers.append(notice("HISTORY_CHANGE_NOT_ALLOWED", product))
    if overlaps(periods(outcome)):
        blockers.append(notice("RECIPE_PERIOD_OVERLAP", product))
    uncovered = gaps(periods(outcome), minimum)
    # A no-op needs no new gap acknowledgment; changed calendar's uncovered ranges do.
    if outcome != before and uncovered:
        warnings.append(notice("RECIPE_GAP_WARNING", product, ranges=uncovered))
    differences = tuple(dto.DateRange(from_date=a,to_date=b) for a,b in
                        changed_ranges(periods(before),periods(outcome),minimum))
    dedup_blockers = tuple({n.code:n for n in blockers}.values())
    required = (*READS, "recipe.manage_effectivity", *(("recipe.create_version",) if new else ()))
    preview = dto.Preview(change_id=uuid4(),status="blocked" if dedup_blockers else "preview_ready",
        preview_digest="pending", store_id=store, product_id=product, evaluated_at=now,
        as_of_date=today, minimum_change_date=minimum, schedule_version=schedule_version,
        catalog_version=catalog_version, before=before, after=outcome,
        changed_ranges=differences,new_contents=tuple(new.values()),required_permissions=tuple(sorted(required)),
        blockers=dedup_blockers,warnings=tuple(warnings),
        required_warning_acknowledgements=tuple(sorted({n.code for n in warnings})),can_commit=not dedup_blockers)
    return preview.model_copy(update={"preview_digest":content_digest(preview.model_dump(mode="json",exclude={"preview_digest"}))})
