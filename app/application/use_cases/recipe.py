from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.application._validation import load_ingredient, require_idle_session, require_product, require_unit
from app.application.contracts.recipe import CreateRecipeVersionInput, GetActiveRecipeInput, RecipeLineResult, RecipeResult
from app.application.errors import known_conflict
from app.models import Recipe, RecipeLine
from app.repositories.recipe import RecipeRepository


class RecipeUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.recipes = RecipeRepository(session)

    def _result(self, row: Recipe) -> RecipeResult:
        return RecipeResult(
            id=row.id, store_id=row.store_id, product_id=row.product_id, version=row.version,
            effective_from=row.effective_from, effective_to=row.effective_to,
            yield_quantity=row.yield_quantity, process_loss_rate=row.process_loss_rate,
            lines=tuple(RecipeLineResult.model_validate(line) for line in
                        self.recipes.list_recipe_lines(row.store_id, row.id)))

    def create_version(self, data: CreateRecipeVersionInput) -> RecipeResult:
        data = CreateRecipeVersionInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            require_product(self.session, data.store_id, data.product_id)
            for line in data.lines:
                ingredient = load_ingredient(self.session, data.store_id, line.ingredient_id)
                require_unit(ingredient.base_unit, line.unit)
            row = Recipe(**data.model_dump(exclude={'lines'}))
            self.recipes.add_recipe(data.store_id, row)
            self.session.flush()
            for line in data.lines:
                self.recipes.add_recipe_line(data.store_id, RecipeLine(**line.model_dump(),
                    store_id=data.store_id, recipe_id=row.id))
            self.session.flush()
            result = self._result(row)
            self.session.commit()
            return result
        except IntegrityError as error:
            self.session.rollback()
            for constraint, state in [('uq_recipes_product_version', '23505'), ('ex_recipes_product_period', '23P01')]:
                mapped = known_conflict(error, constraint, sqlstate=state)
                if mapped is not None:
                    raise mapped from error
            raise
        except Exception:
            self.session.rollback()
            raise

    def get_active(self, data: GetActiveRecipeInput) -> RecipeResult | None:
        data = GetActiveRecipeInput.model_validate(data)
        with self.session.no_autoflush:
            require_product(self.session, data.store_id, data.product_id)
            row = self.recipes.get_active_recipe(data.store_id, data.product_id, data.effective_date)
            if row is None:
                return None
            return self._result(row)
