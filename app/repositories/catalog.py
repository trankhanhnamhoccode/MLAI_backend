"""Store catalog persistence; no normalization, pricing or unit conversion."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ingredient, Product
from app.repositories._guards import require_new, require_store


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_product(self, store_id: UUID, product: Product) -> None:
        require_store(store_id, product.store_id)
        require_new(product)
        self._session.add(product)

    def get_product(self, store_id: UUID, product_id: UUID) -> Product | None:
        return self._session.scalar(select(Product).where(Product.store_id == store_id, Product.id == product_id))

    def get_product_by_sku(self, store_id: UUID, sku: str) -> Product | None:
        return self._session.scalars(select(Product).where(Product.store_id == store_id, Product.sku == sku)).one_or_none()

    def list_products(self, store_id: UUID) -> list[Product]:
        return list(self._session.scalars(select(Product).where(Product.store_id == store_id).order_by(Product.name, Product.id)))

    def add_ingredient(self, store_id: UUID, ingredient: Ingredient) -> None:
        require_store(store_id, ingredient.store_id)
        require_new(ingredient)
        self._session.add(ingredient)

    def get_ingredient(self, store_id: UUID, ingredient_id: UUID) -> Ingredient | None:
        return self._session.scalar(select(Ingredient).where(Ingredient.store_id == store_id, Ingredient.id == ingredient_id))

    def get_ingredient_by_sku(self, store_id: UUID, sku: str) -> Ingredient | None:
        return self._session.scalars(select(Ingredient).where(Ingredient.store_id == store_id, Ingredient.sku == sku)).one_or_none()

    def list_ingredients(self, store_id: UUID) -> list[Ingredient]:
        return list(self._session.scalars(select(Ingredient).where(Ingredient.store_id == store_id).order_by(Ingredient.name, Ingredient.id)))
