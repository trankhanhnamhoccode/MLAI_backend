from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.application._validation import load_ingredient, require_idle_session, require_supplier, require_unit
from app.application.contracts.supplier import CreateSupplierTermInput, GetSupplierTermInput, SupplierTermResult
from app.application.errors import ApplicationError, ErrorCategory, known_conflict
from app.models import SupplierTerm
from app.repositories.supplier import SupplierRepository


class SupplierTermUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.suppliers = SupplierRepository(session)

    def create(self, data: CreateSupplierTermInput) -> SupplierTermResult:
        data = CreateSupplierTermInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            require_supplier(self.session, data.store_id, data.supplier_id)
            ingredient = load_ingredient(self.session, data.store_id, data.ingredient_id)
            require_unit(ingredient.base_unit, data.unit)
            row = SupplierTerm(**data.model_dump())
            self.suppliers.add_supplier_term(data.store_id, row)
            self.session.flush()
            result = SupplierTermResult.model_validate(row)
            self.session.commit()
            return result
        except IntegrityError as error:
            self.session.rollback()
            for constraint, state in [('uq_supplier_terms_pair_version', '23505'), ('ex_supplier_terms_pair_period', '23P01')]:
                mapped = known_conflict(error, constraint, sqlstate=state)
                if mapped is not None:
                    raise mapped from error
            raise
        except Exception:
            self.session.rollback()
            raise

    def get(self, data: GetSupplierTermInput) -> SupplierTermResult:
        data = GetSupplierTermInput.model_validate(data)
        with self.session.no_autoflush:
            row = self.suppliers.get_supplier_term(data.store_id, data.supplier_term_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'SupplierTerm not found in Store')
            return SupplierTermResult.model_validate(row)
