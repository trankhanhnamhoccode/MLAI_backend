from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.application._validation import load_ingredient, require_idle_session, require_store
from app.application.contracts.catalog import CreateIngredientInput, GetIngredientInput, IngredientResult, CreateProductInput, GetProductInput, ProductResult
from app.application.errors import ApplicationError, ErrorCategory, known_conflict
from app.models import Ingredient, Product
from app.repositories.catalog import CatalogRepository


class ProductUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.catalog = CatalogRepository(session)

    def create(self, data: CreateProductInput) -> ProductResult:
        data = CreateProductInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            require_store(self.session, data.store_id)
            row = Product(**data.model_dump())
            self.catalog.add_product(data.store_id, row)
            self.session.flush()
            result = ProductResult.model_validate(row)
            self.session.commit()
            return result
        except IntegrityError as error:
            self.session.rollback()
            mapped = known_conflict(error, 'uq_products_store_sku')
            if mapped is not None:
                raise mapped from error
            raise
        except Exception:
            self.session.rollback()
            raise

    def get(self, data: GetProductInput) -> ProductResult:
        data = GetProductInput.model_validate(data)
        with self.session.no_autoflush:
            row = self.catalog.get_product(data.store_id, data.product_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'Product not found in Store')
            return ProductResult.model_validate(row)


class IngredientUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.catalog = CatalogRepository(session)

    def create(self, data: CreateIngredientInput) -> IngredientResult:
        data = CreateIngredientInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            require_store(self.session, data.store_id)
            row = Ingredient(**data.model_dump())
            self.catalog.add_ingredient(data.store_id, row)
            self.session.flush()
            result = IngredientResult.model_validate(row)
            self.session.commit()
            return result
        except IntegrityError as error:
            self.session.rollback()
            mapped = known_conflict(error, 'uq_ingredients_store_sku')
            if mapped is not None:
                raise mapped from error
            raise
        except Exception:
            self.session.rollback()
            raise

    def get(self, data: GetIngredientInput) -> IngredientResult:
        data = GetIngredientInput.model_validate(data)
        with self.session.no_autoflush:
            return IngredientResult.model_validate(load_ingredient(self.session, data.store_id, data.ingredient_id))
