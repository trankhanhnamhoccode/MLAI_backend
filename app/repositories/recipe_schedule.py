"""Product-scoped calendar snapshot; persistence primitives only."""
from dataclasses import dataclass
from datetime import date
from uuid import UUID
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models import Product, Ingredient, Recipe, RecipeLine, Store
from app.application.contracts import recipe_schedule as dto
from app.application.contracts.auth import AuthError
from app.application.recipe_schedule_plan import state, item_order, exact, periods
from app.application.import_identity import content_digest
from app.domain.recipe_calendar import overlaps
from app.models.recipe_schedule import RecipeScheduleChange


@dataclass(frozen=True)
class CalendarSnapshot:
    items: tuple[dto.ScheduleItem, ...]
    schedule_version: str
    catalog_version: str
    selling_unit: str
    ingredients: dict[UUID, dict]


def fence_calendar(session: Session) -> None:
    # Same canonical ordering as Import S4.5/S4.6; fences cover absent rows too.
    for name in ("ingredients", "products", "recipe_lines", "recipes"):
        session.execute(text('LOCK TABLE "' + name + '" IN SHARE ROW EXCLUSIVE MODE'))


def change_row(session: Session, store: UUID, product: UUID, ident: UUID) -> RecipeScheduleChange:
    row = session.scalar(select(RecipeScheduleChange).where(RecipeScheduleChange.id == ident,
        RecipeScheduleChange.store_id == store,RecipeScheduleChange.product_id == product))
    if row is None:
        raise AuthError("RESOURCE_NOT_FOUND",404)
    return row


def capture_calendar(session: Session, store: UUID, product: UUID, today: date) -> CalendarSnapshot:
    p = session.scalar(select(Product).where(Product.id == product,Product.store_id == store))
    if p is None:
        raise AuthError("RESOURCE_NOT_FOUND",404)
    store_row = session.get(Store,store)
    ingredients = {i.id:dict(id=str(i.id),base_unit=i.base_unit,active=i.active,name=i.name,sku=i.sku,
                           store_id=str(i.store_id)) for i in session.scalars(select(Ingredient).where(Ingredient.store_id == store))}
    recipes = session.execute(select(Recipe,text("xmin::text")).where(
        Recipe.store_id == store,Recipe.product_id == product).order_by(Recipe.version,Recipe.id).limit(100001)).all()
    if len(recipes) > 100000:
        raise AuthError("RESOURCE_LIMIT_EXCEEDED",413)
    ids = [r.id for r,_ in recipes]
    lines = session.execute(select(RecipeLine,text("xmin::text")).where(
        RecipeLine.recipe_id.in_(ids)).order_by(RecipeLine.ingredient_id,RecipeLine.id)).all() if ids else []
    if len(lines) > 100000:
        raise AuthError("RESOURCE_LIMIT_EXCEEDED",413)
    items, evidence = [], []
    try:
        for r,xmin in recipes:
            own = [(l,v) for l,v in lines if l.recipe_id == r.id]
            if len({l.ingredient_id for l,_ in own}) != len(own):
                raise ValueError("duplicate Ingredient")
            for l,_ in own:
                ingredient = ingredients.get(l.ingredient_id)
                if ingredient is None or l.store_id != store or ingredient["base_unit"] != l.unit:
                    raise ValueError("invalid scoped recipe line")
            content = dto.Content(recipe_id=r.id,version=r.version,yield_quantity=exact(str(r.yield_quantity)),
                yield_unit=p.selling_unit,process_loss_rate=exact(str(r.process_loss_rate)),ingredients=tuple(
                    dto.ContentLine(recipe_line_id=l.id,ingredient_id=l.ingredient_id,quantity=exact(str(l.quantity)),unit=l.unit) for l,_ in own))
            if r.effective_to is not None and r.effective_to < r.effective_from:
                raise ValueError("invalid period")
            assignment = dto.Assignment(effective_from=r.effective_from,effective_to=r.effective_to) if r.assigned else None
            items.append(dto.ScheduleItem(content=content,assignment=assignment,state=state(assignment,today)))
            evidence.append(dict(content=content.model_dump(mode="json"),from_date=str(r.effective_from),
                to_date=str(r.effective_to),assigned=r.assigned,row_version=xmin,line_versions=[v for _,v in own]))
        if overlaps(periods(items)):
            raise ValueError("overlapping canonical calendar")
    except (ValueError,ValidationError,ArithmeticError):
        raise AuthError("CATALOG_INTEGRITY_UNAVAILABLE",503) from None
    catalog = dict(product=dict(id=str(p.id),selling_unit=p.selling_unit,name=p.name,sku=p.sku,active=p.active),
        timezone=store_row.timezone,ingredients=sorted(ingredients.values(),key=lambda i:i["id"]))
    return CalendarSnapshot(tuple(sorted(items,key=item_order)),"schedule-"+content_digest(evidence),
        "catalog-"+content_digest(catalog),p.selling_unit,ingredients)
