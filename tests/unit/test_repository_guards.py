"""Boundary failures require no database connection and stage no rows."""
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models import (
    BusinessConstraint, DecisionRun, ForecastRun, Ingredient, InventoryLot,
    InventoryMovement, Product, Recipe, RecipeLine, SalesDaily, StoreMembership,
    Supplier, SupplierTerm,
)
from app.repositories.catalog import CatalogRepository
from app.repositories.constraints import ConstraintsRepository
from app.repositories.decision import DecisionRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.identity import IdentityRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.recipe import RecipeRepository
from app.repositories.sales import SalesRepository
from app.repositories.supplier import SupplierRepository


@pytest.mark.parametrize("repository,method,model", [
    (IdentityRepository, "add_membership", StoreMembership),
    (CatalogRepository, "add_product", Product),
    (CatalogRepository, "add_ingredient", Ingredient),
    (RecipeRepository, "add_recipe", Recipe),
    (RecipeRepository, "add_recipe_line", RecipeLine),
    (SupplierRepository, "add_supplier", Supplier),
    (SupplierRepository, "add_supplier_term", SupplierTerm),
    (SalesRepository, "add_sales_record", SalesDaily),
    (InventoryRepository, "add_lot", InventoryLot),
    (InventoryRepository, "append_movement", InventoryMovement),
    (ConstraintsRepository, "add_constraint", BusinessConstraint),
    (ForecastRepository, "add_forecast_run", ForecastRun),
    (DecisionRepository, "add_decision_run", DecisionRun),
])
def test_wrong_store_insert_rejected_before_staging(repository, method, model):
    with Session() as session:
        with pytest.raises(ValueError, match="Store"):
            getattr(repository(session), method)(UUID(int=1), model(store_id=UUID(int=2)))
        assert not session.new
