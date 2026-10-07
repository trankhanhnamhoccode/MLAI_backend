"""Explicit persistence model registration; imports do not connect to the DB."""
from app.models.store import Store
from app.models.store_membership import StoreMembership
from app.models.user import User
from app.models.product import Product
from app.models.ingredient import Ingredient
from app.models.recipe import Recipe
from app.models.recipe_line import RecipeLine
from app.models.supplier import Supplier
from app.models.supplier_term import SupplierTerm
from app.models.sales_daily import SalesDaily
from app.models.inventory_lot import InventoryLot
from app.models.inventory_movement import InventoryMovement
from app.models.business_constraint import BusinessConstraint
from app.models.forecast_run import ForecastRun
from app.models.forecast_prediction import ForecastPrediction
from app.models.decision_run import DecisionRun
from app.models.forecast_run_input import ForecastRunInput
from app.models.forecast_execution_metadata import ForecastExecutionMetadata

__all__ = [
    "User", "Store", "StoreMembership", "Product", "Ingredient", "Recipe", "RecipeLine",
    "Supplier", "SupplierTerm", "SalesDaily", "InventoryLot", "InventoryMovement", "BusinessConstraint",
    "ForecastRun", "ForecastPrediction", "DecisionRun", "ForecastRunInput", "ForecastExecutionMetadata",
]
