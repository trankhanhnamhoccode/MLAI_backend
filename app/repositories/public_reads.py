"""Bounded scoped projections and SQL aggregates; caller owns snapshot Session."""

from decimal import Decimal
import unicodedata
from sqlalchemy.orm import Session
from sqlalchemy import select, func, case, and_, or_, literal, literal_column
from app.models import (
    Store,
    Product,
    Ingredient,
    Recipe,
    RecipeLine,
    InventoryLot,
    InventoryMovement,
    PublicReadRevision,
)
from app.models.operational_import import InventoryThreshold, InventoryReceiptRecord, InventoryAudit, ScopeDeclarationRecord

_ACCENTS = (
    "".join(
        chr(i)
        for i in (*range(0xC0, 0x250), *range(0x1E00, 0x1F00))
        if unicodedata.normalize("NFD", chr(i)) != chr(i)
        and all(
            ord(c) < 128 or unicodedata.combining(c)
            for c in unicodedata.normalize("NFD", chr(i))
        )
    )
    + "Đđ"
)
_PLAIN = (
    "".join(
        "".join(
            c for c in unicodedata.normalize("NFD", x) if not unicodedata.combining(c)
        )
        for x in _ACCENTS[:-2]
    )
    + "Dd"
)


def folded(column):
    return func.lower(
        func.regexp_replace(
            func.translate(column, _ACCENTS, _PLAIN), "[\u0300-\u036f]", "", "g"
        )
    ).collate("C")


def after_key(column, identifier, last, descending):
    if last is None:
        return literal(True)
    key, uid = last
    if key is None:
        return and_(column.is_(None), identifier > uid)
    return or_(
        column.is_(None),
        column < key if descending else column > key,
        and_(column == key, identifier > uid),
    )


class PublicReadRepository:
    def __init__(self, session: Session):
        self.session = session

    def basis(self, store):
        return (
            self.session.execute(
                select(
                    Store.id,
                    Store.name,
                    Store.timezone,
                    Store.currency,
                    Store.active,
                    Store.updated_at,
                    PublicReadRevision.menu_revision,
                    PublicReadRevision.recipe_revision,
                    PublicReadRevision.inventory_revision,
                )
                .outerjoin(PublicReadRevision, PublicReadRevision.store_id == Store.id)
                .where(Store.id == store)
            )
            .mappings()
            .one_or_none()
        )

    def updated(self, store, *, catalog, recipes=False):
        sources = [select(Store.updated_at.label("at")).where(Store.id == store)]
        if catalog:
            sources.append(
                select(Product.updated_at.label("at")).where(Product.store_id == store)
            )
            if recipes:
                sources.extend(
                    [
                        select(Ingredient.updated_at.label("at")).where(
                            Ingredient.store_id == store
                        ),
                        select(Recipe.updated_at.label("at")).where(
                            Recipe.store_id == store
                        ),
                        select(RecipeLine.created_at.label("at")).where(
                            RecipeLine.store_id == store
                        ),
                    ]
                )
        else:
            sources.extend(
                [
                    select(Ingredient.updated_at.label("at")).where(
                        Ingredient.store_id == store
                    ),
                    select(InventoryLot.updated_at.label("at")).where(
                        InventoryLot.store_id == store
                    ),
                    select(InventoryMovement.created_at.label("at")).where(
                        InventoryMovement.store_id == store
                    ),
                    select(InventoryThreshold.updated_at.label("at")).where(InventoryThreshold.store_id==store),
                    select(InventoryAudit.occurred_at.label("at")).where(InventoryAudit.store_id==store),
                ]
            )
        union = sources[0].union_all(*sources[1:]).subquery()
        return self.session.scalar(select(func.max(union.c.at)))

    def product(self, store, identifier):
        return (
            self.session.execute(
                select(*Product.__table__.columns).where(
                    Product.store_id == store, Product.id == identifier
                )
            )
            .mappings()
            .one_or_none()
        )

    def products(self, store, q, status, sort, last, limit):
        predicate = [Product.store_id == store]
        if q is not None:
            predicate.append(folded(Product.name).contains(q, autoescape=True))
        if status:
            predicate.append(Product.active == (status == "active"))
        total = self.session.scalar(
            select(func.count()).select_from(Product).where(*predicate)
        )
        summary = (
            self.session.execute(
                select(
                    func.count().label("product_count"),
                    func.count().filter(Product.active).label("active_count"),
                    func.count().filter(~Product.active).label("paused_count"),
                ).where(Product.store_id == store)
            )
            .mappings()
            .one()
        )
        key = Product.price if "selling_price" in sort else folded(Product.name)
        descending = sort.startswith("-")
        rows = (
            self.session.execute(
                select(*Product.__table__.columns, key.label("sort_key"))
                .where(*predicate, after_key(key, Product.id, last, descending))
                .order_by(
                    (key.desc() if descending else key.asc()).nulls_last(), Product.id
                )
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        return rows, total, summary

    def recipes(self, store, products, today):
        # Count/validate page recipes without fetching every ingredient line.
        invalid = or_(
            RecipeLine.store_id != store,
            Ingredient.id.is_(None),
            Ingredient.store_id != store,
            RecipeLine.unit != Ingredient.base_unit,
            RecipeLine.quantity <= 0,
            RecipeLine.quantity.in_(
                [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
            ),
        )
        return (
            self.session.execute(
                select(
                    Recipe.id,
                    Recipe.product_id,
                    Recipe.version,
                    Recipe.effective_from,
                    Recipe.effective_to,
                    Recipe.yield_quantity,
                    Recipe.process_loss_rate,
                    func.count(RecipeLine.id).label("line_count"),
                    func.count(RecipeLine.id).filter(invalid).label("invalid_lines"),
                    (
                        func.count(RecipeLine.id)
                        - func.count(func.distinct(RecipeLine.ingredient_id))
                    ).label("duplicate_lines"),
                )
                .outerjoin(RecipeLine, RecipeLine.recipe_id == Recipe.id)
                .outerjoin(Ingredient, Ingredient.id == RecipeLine.ingredient_id)
                .where(
                    Recipe.store_id == store,
                    Recipe.product_id.in_(products),
                    Recipe.assigned.is_(True),
                    Recipe.effective_from <= today,
                    or_(Recipe.effective_to.is_(None), Recipe.effective_to >= today),
                )
                .group_by(Recipe.id)
            )
            .mappings()
            .all()
        )

    def lines(self, store, recipe):
        return (
            self.session.execute(
                select(
                    RecipeLine.id,
                    RecipeLine.store_id.label("line_store"),
                    RecipeLine.ingredient_id,
                    RecipeLine.quantity,
                    RecipeLine.unit,
                    Ingredient.name,
                    Ingredient.sku,
                    Ingredient.active,
                    Ingredient.expiry_tracking,
                    Ingredient.base_unit,
                    Ingredient.store_id.label("ingredient_store"),
                )
                .outerjoin(Ingredient, Ingredient.id == RecipeLine.ingredient_id)
                .where(RecipeLine.recipe_id == recipe)
                .order_by(RecipeLine.ingredient_id)
                .limit(10486)
            )
            .mappings()
            .all()
        )

    def ingredient(self, store, identifier):
        return (
            self.session.execute(
                select(*Ingredient.__table__.columns).where(
                    Ingredient.store_id == store, Ingredient.id == identifier
                )
            )
            .mappings()
            .one_or_none()
        )

    def stock(self, store, today, one=None):
        l, i = InventoryLot, Ingredient
        threshold = InventoryThreshold
        confirmed_ids = self.confirmed_stock(store)
        confirmed = i.id.in_(confirmed_ids)
        positive = l.on_hand_quantity > 0
        future = l.received_date > today
        eligible = and_(
            positive,
            or_(l.received_date.is_(None), l.received_date <= today),
            or_(
                l.expiry_date >= today,
                and_(l.expiry_date.is_(None), ~i.expiry_tracking),
            ),
        )
        expired = and_(positive, l.expiry_date < today)
        near = and_(eligible, l.expiry_date - today <= 7)

        def count(condition):
            return func.count(l.id).filter(condition)

        def total(condition):
            return func.coalesce(
                func.sum(case((condition, l.on_hand_quantity), else_=0)), 0
            )

        usable_known = and_(count(and_(positive, i.expiry_tracking, l.expiry_date.is_(None))) == 0, count(future) == 0)
        assessed = and_(confirmed, usable_known, threshold.minimum_usable_quantity.is_not(None))
        low = and_(assessed, total(eligible) <= threshold.minimum_usable_quantity)

        return (
            select(
                i.id,
                i.name,
                i.sku,
                i.active,
                i.base_unit,
                i.expiry_tracking,
                func.coalesce(func.sum(l.on_hand_quantity), 0).label("physical"),
                total(eligible).label("usable"),
                total(expired).label("expired"),
                count(positive).label("positive_count"),
                func.count(l.id).label("lot_count"),
                count(near).label("near_count"),
                count(expired).label("expired_count"),
                func.min(l.expiry_date).filter(eligible).label("nearest_expiry"),
                count(and_(positive, i.expiry_tracking, l.expiry_date.is_(None))).label(
                    "missing_required_expiry"
                ),
                count(future).label("future_receipt"),
                count(l.received_date.is_(None)).label("missing_receipt"),
                count(and_(~i.expiry_tracking, l.expiry_date.is_(None))).label(
                    "missing_optional_expiry"
                ),
                count(
                    or_(
                        l.unit != i.base_unit,
                        l.on_hand_quantity.in_(
                            [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
                        ),
                        l.on_hand_quantity < 0,
                    )
                ).label("invalid_lots"),
                confirmed.label("confirmed"), threshold.minimum_usable_quantity.label("threshold"), threshold.version.label("threshold_version"),
                assessed.label("assessed"), low.label("low"),
                case((and_(confirmed, total(positive)>0, total(positive)==total(expired)), "expired"),
                    (and_(confirmed, usable_known, total(eligible)==0), "empty"), (low, "low_stock"),
                    (count(near)>0, "near_expiry"),
                    (or_(~assessed,count(l.received_date.is_(None))>0,count(and_(~i.expiry_tracking,l.expiry_date.is_(None)))>0),"watch"),
                    else_="stable").label("status"),
            )
            .outerjoin(l, and_(l.ingredient_id == i.id, l.store_id == store))
            .outerjoin(threshold, and_(threshold.store_id==store,threshold.ingredient_id==i.id))
            .where(i.store_id == store, *([i.id == one] if one is not None else []))
            .group_by(i.id, threshold.minimum_usable_quantity, threshold.version)
        )

    def confirmed_stock(self, store):
        """A declaration is evidence for its exact unchanged scoped lot dependency."""
        from app.repositories.import_staging import json_value
        from app.domain.inventory.read_rules import ReadFactError
        from app.application.operational_import_facts import inventory_dependency
        rows = self.session.scalars(select(ScopeDeclarationRecord).where(ScopeDeclarationRecord.store_id==store,
            ScopeDeclarationRecord.payload["declaration"]["kind"].astext=="INVENTORY").limit(100001)).all()
        if len(rows)>100000:raise ReadFactError(True)
        if not rows:
            return ()
        snapshot={}
        count=0
        for model in (Ingredient,InventoryLot):
            columns=[c for c in model.__table__.columns if c.name != "unit_cost"]
            records=self.session.execute(select(*columns,literal_column("xmin::text").label("_row_version")).where(model.store_id==store)
                .order_by(model.id).limit(100001)).mappings().all()
            count+=len(records)
            if count>100000:raise ReadFactError(True)
            snapshot[model.__tablename__]=[{key:json_value(value) for key,value in record.items()} for record in records]
        latest={}
        for row in rows:
            key=(row.source_system_key,row.source_record_key)
            if key not in latest or latest[key].version<row.version:latest[key]=row
        evidence={}
        for row in latest.values():
            value=row.payload["declaration"]
            if value["kind"]!="INVENTORY":continue
            ident=value["ingredient_id"]
            if row.dependency_digest==inventory_dependency(snapshot,ident):
                evidence.setdefault(ident,set()).add(value["state"])
        return tuple(ident for ident,states in evidence.items() if states and "UNKNOWN" not in states)

    def inventory(
        self, store, today, q, statuses, identifiers, sort, last, limit, one=None
    ):
        stocks = self.stock(store, today, one).cte("stock")
        c = stocks.c
        summary = (
            self.session.execute(
                select(
                    func.count().label("ingredient_count"),
                    func.coalesce(func.sum(c.positive_count), 0).label(
                        "positive_lot_count"
                    ),
                    func.coalesce(func.sum(c.near_count), 0).label(
                        "near_expiry_lot_count"
                    ),
                    func.count()
                    .filter(c.near_count > 0)
                    .label("near_expiry_ingredient_count"),
                    func.coalesce(func.sum(c.expired_count), 0).label(
                        "expired_lot_count"
                    ),
                    case((func.count().filter(~c.assessed)>0,None),else_=func.count().filter(c.low)).label("low_stock_ingredient_count"),
                    func.count().filter(~c.assessed).label("unknown_assessment_ingredient_count"),
                )
            )
            .mappings()
            .one()
        )
        predicate = []
        if one is not None:
            predicate.append(c.id == one)
        if identifiers:
            predicate.append(c.id.in_(identifiers))
        if q is not None:
            predicate.append(
                or_(
                    folded(c.name).contains(q, autoescape=True),
                    folded(c.sku).contains(q, autoescape=True),
                )
            )
        if statuses:
            predicate.append(c.status.in_(statuses))
        total = self.session.scalar(
            select(func.count()).select_from(stocks).where(*predicate)
        )
        key = c.nearest_expiry if sort == "nearest_expiry" else folded(c.name)
        desc = sort.startswith("-")
        rows = (
            self.session.execute(
                select(stocks, key.label("sort_key"))
                .where(*predicate, after_key(key, c.id, last, desc))
                .order_by((key.desc() if desc else key.asc()).nulls_last(), c.id)
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        found = (
            set(
                self.session.scalars(
                    select(Ingredient.id).where(
                        Ingredient.store_id == store, Ingredient.id.in_(identifiers)
                    )
                )
            )
            if identifiers
            else set()
        )
        return rows, total, summary, tuple(sorted(set(identifiers) - found))

    def lots(self, store, ingredient, today, last, limit, cost):
        l = InventoryLot
        columns = [
            column
            for column in l.__table__.columns
            if cost or column.name != "unit_cost"
        ]
        condition = [l.store_id == store, l.ingredient_id == ingredient["id"]]
        eligible = and_(
            l.on_hand_quantity > 0,
            or_(l.received_date.is_(None), l.received_date <= today),
            or_(
                l.expiry_date >= today,
                and_(l.expiry_date.is_(None), not ingredient["expiry_tracking"]),
            ),
        )
        first = self.session.scalar(
            select(l.id)
            .where(*condition, eligible)
            .order_by(
                l.expiry_date.asc().nulls_last(),
                l.received_date.asc().nulls_last(),
                l.id,
            )
            .limit(1)
        )
        total = self.session.scalar(
            select(func.count()).select_from(l).where(*condition)
        )
        if last:
            expiry, batch, uid = last
            same = (
                l.expiry_date.is_(None) if expiry is None else l.expiry_date == expiry
            )
            batch_after = after_key(l.lot_code.collate("C"), l.id, (batch, uid), False)
            greater = and_(
                l.expiry_date > expiry if expiry is not None else literal(False),
                literal(True),
            )
            conditions = [
                or_(
                    and_(same, batch_after),
                    greater,
                    and_(l.expiry_date.is_(None), literal(expiry is not None)),
                )
            ]
        else:
            conditions = []
        rows = (
            self.session.execute(
                select(*columns)
                .add_columns(InventoryReceiptRecord.origin.label("origin"))
                .outerjoin(InventoryReceiptRecord,and_(InventoryReceiptRecord.lot_id==l.id,InventoryReceiptRecord.store_id==store))
                .where(*condition, *conditions)
                .order_by(
                    l.expiry_date.asc().nulls_last(),
                    l.lot_code.collate("C").asc().nulls_last(),
                    l.id,
                )
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        return rows, total, first

    def movements(self, store, ingredient, last, limit):
        m, l = InventoryMovement, InventoryLot
        condition = [m.store_id == store, m.ingredient_id == ingredient]
        total = self.session.scalar(
            select(func.count()).select_from(m).where(*condition)
        )
        rows = (
            self.session.execute(
                select(
                    *m.__table__.columns,
                    l.lot_code,
                    l.unit,
                    l.store_id.label("lot_store"),
                    l.ingredient_id.label("lot_ingredient")
                    ,InventoryAudit.actor_id.label("actor_user_id"), InventoryAudit.record_json["origin"].astext.label("movement_origin")
                )
                .outerjoin(l, l.id == m.lot_id)
                .outerjoin(InventoryAudit,and_(InventoryAudit.movement_id==m.id,InventoryAudit.store_id==store))
                .where(*condition, after_key(m.occurred_at, m.id, last, True))
                .order_by(m.occurred_at.desc(), m.id)
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        return rows, total
