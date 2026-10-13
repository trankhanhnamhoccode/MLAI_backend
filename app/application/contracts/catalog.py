from uuid import UUID
from app.application.contracts.common import Contract, Name, NonnegativeDecimal, MoneyDecimal, Sku, Unit


class CreateProductInput(Contract):
    store_id: UUID
    name: Name
    selling_unit: Unit
    sku: Sku | None = None
    price: MoneyDecimal | None = None
    active: bool = True  # Accepted catalog lifecycle metadata default.


class GetProductInput(Contract):
    store_id: UUID
    product_id: UUID


class ProductResult(CreateProductInput):
    id: UUID
    # Already recorded evidence is readable without silently rewriting old money.
    price: NonnegativeDecimal | None = None


class CreateIngredientInput(Contract):
    store_id: UUID
    name: Name
    base_unit: Unit
    sku: Sku | None = None
    expiry_tracking: bool = False
    active: bool = True


class GetIngredientInput(Contract):
    store_id: UUID
    ingredient_id: UUID


class IngredientResult(CreateIngredientInput):
    id: UUID
