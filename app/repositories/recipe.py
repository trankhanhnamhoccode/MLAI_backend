"""Dated recipe definitions and their lines; no BOM expansion."""
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Recipe, RecipeLine
from app.repositories._guards import require_new, require_store


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_recipe(self, store_id: UUID, recipe: Recipe) -> None:
        require_store(store_id, recipe.store_id)
        require_new(recipe)
        self._session.add(recipe)

    def get_recipe(self, store_id: UUID, recipe_id: UUID) -> Recipe | None:
        return self._session.scalar(select(Recipe).where(Recipe.store_id == store_id, Recipe.id == recipe_id))

    def list_recipe_versions(self, store_id: UUID, product_id: UUID) -> list[Recipe]:
        return list(self._session.scalars(select(Recipe).where(Recipe.store_id == store_id, Recipe.product_id == product_id).order_by(Recipe.version, Recipe.id)))

    def get_active_recipe(self, store_id: UUID, product_id: UUID, day: date) -> Recipe | None:
        return self._session.scalars(select(Recipe).where(
            Recipe.store_id == store_id, Recipe.product_id == product_id,
            Recipe.effective_from <= day,
            Recipe.effective_to.is_(None) | (Recipe.effective_to >= day),
        )).one_or_none()

    def add_recipe_line(self, store_id: UUID, line: RecipeLine) -> None:
        require_store(store_id, line.store_id)
        require_new(line)
        self._session.add(line)

    def get_line(self, store_id: UUID, line_id: UUID) -> RecipeLine | None:
        return self._session.scalar(select(RecipeLine).where(RecipeLine.store_id == store_id, RecipeLine.id == line_id))

    def list_recipe_lines(self, store_id: UUID, recipe_id: UUID) -> list[RecipeLine]:
        return list(self._session.scalars(select(RecipeLine).where(RecipeLine.store_id == store_id, RecipeLine.recipe_id == recipe_id).order_by(RecipeLine.ingredient_id, RecipeLine.id)))
