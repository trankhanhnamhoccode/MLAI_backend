"""S4.9 acceptance dependency: caller-owned atomic config resolution, no Run writes."""
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from app.application.contracts.planning_setup import PlanningConfiguration,SavedRequirementsRecord,PlanningRequest,PlanningResolutionOutcome
from app.application.contracts.procurement_v2 import ProcurementPolicyV2
from app.application.contracts.decision_capture_v2 import MenuProduct
from app.application.contracts import planning_configuration as dto
from app.application.planning_configuration_values import field_error
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.import_identity import content_digest
from app.repositories.planning_configuration import configuration_rows,default_record,saved_row,fence_save_products
from app.repositories.identity import StoreRepository
from app.application.contracts.planning_setup import BudgetCeilingRecord


def resolve_configuration_in_transaction(
    session: Session,store: UUID,request: PlanningRequest | dict,
    policy: ProcurementPolicyV2,now: datetime,
) -> PlanningResolutionOutcome:
    """Composition must already hold the current authorized Store lock.

    Shared config mutations/operator use that same lock. Product fence covers
    active references until the caller's acceptance commit. No compute/commit here.
    """
    request=PlanningRequest.model_validate(request)
    fence_save_products(session)
    row=StoreRepository(session).get_store_by_id(store)
    default,cap,products=configuration_rows(session,store)
    saved=saved_row(session,store,request.saved_requirement_id) if request.requirements_mode=='saved' else None
    if saved and saved.state=='archived':
        raise dto.ConfigurationError('INVALID_PLANNING_CONFIGURATION',field_errors=(field_error('SAVED_REQUIREMENTS_ARCHIVED','saved_requirement_id'),))
    configuration=PlanningConfiguration(store_id=store,currency=row.currency,timezone=row.timezone,read_at=now,
        configuration_version=content_digest(dict(default=default.version if default else None,cap=cap.version if cap else None,saved=saved.version if saved else None)),
        provenance='Store-authorized config transaction; current Store lock and Product fence',consistency='SINGLE_SNAPSHOT_DECLARED',
        defaults=default_record(default),budget_ceiling=BudgetCeilingRecord(amount=cap.amount,currency=row.currency,version=cap.version,updated_at=cap.updated_at,provenance='Store cap configuration') if cap else None,
        saved=SavedRequirementsRecord(store_id=store,saved_requirement_id=saved.id,name=saved.name,version=saved.version,
            updated_at=saved.updated_at,requirements=saved.requirements_json) if saved else None,
        products=tuple(MenuProduct(store_id=store,product_id=p.id,name=p.name,selling_unit=p.selling_unit,active=p.active) for p in products),policy=policy)
    return resolve_planning_setup(request,configuration)
