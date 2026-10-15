"""IMP14 canonical readiness and retained Import projections."""
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,ConfigDict,model_serializer
from app.application.contracts.auth import DTO
from app.application.contracts.planning_setup import Version

Action=Literal['import','menu','inventory','forecast','planning']


class CompletionReadinessDetails(DTO):
    pass


class ReadinessIssueDetails(DTO):
    field: str | None=None
    impact: str | None=None
    entity_id: UUID | None=None
    reference: str | None=None
    version: int | None=None
    classification: str | None=None
    proof_scope: str | None=None
    suggested_action: str | None=None

    @model_serializer(mode='wrap')
    def present(self,handler):
        return {k:v for k,v in handler(self).items() if v is not None}


class CompletionReadinessIssue(DTO):
    code: str
    source: Literal['authorization','catalog','recipe','sales','inventory','supplier','fees','constraints','forecast','configuration','runtime']
    scope: Literal['STORE','PRODUCT','INGREDIENT']
    entity_id: UUID | None
    affected_dates: tuple[date,...]
    details: CompletionReadinessDetails


IssueDetails=ReadinessIssueDetails


class Issue(CompletionReadinessIssue):
    details: ReadinessIssueDetails


class ActionReadiness(DTO):
    action: Action
    availability: Literal['ready','blocked','unknown']
    can_execute: bool
    data_status: Literal['valid','invalid','incomplete','unknown']
    execution_status: Literal['available','unavailable','unknown']
    blockers: tuple[Issue,...]
    warnings: tuple[Issue,...]
    result_assessment: Literal['NOT_ASSESSED']='NOT_ASSESSED'


class SourceVersions(DTO):
    model_config=ConfigDict(extra='forbid',frozen=True,serialize_by_alias=True,populate_by_name=True)
    catalog: Version | None
    recipes: Version | None
    inventory: Version | None
    sales: Version | None
    suppliers: Version | None
    fees: Version | None
    declarations: Version | None
    planning_config: Version | None
    model_configuration: Version | None=Field(alias='model_config')


class Exclusion(DTO):
    product_id: UUID
    reason_codes: tuple[str,...]
    affected_dates: tuple[date,...]


class ScopeEstimate(DTO):
    menu_product_count: int
    estimated_computable_product_count: int
    excluded_products: tuple[Exclusion,...]


class ForecastAssessment(DTO):
    requested_mode: Literal['BASELINE','TRAINED']
    actual_model_type: str | None
    actual_model_version: str | None
    selection_reason: str | None
    quality_status: Literal['not_evaluated']='not_evaluated'


class PlanningAssessment(DTO):
    semantics_version: Literal['planning_readiness/1']='planning_readiness/1'
    input_scope: Literal['DEFAULT_CONFIGURATION','SUPPLIED_REQUEST']
    requirements_mode: Literal['default','custom','saved']
    configuration_status: Literal['RESOLVED','INVALID','UNKNOWN']
    blockers: tuple[Issue,...]
    warnings: tuple[Issue,...]


class Readiness(DTO):
    store_id: UUID
    as_of_date: date
    evaluated_at: AwareDatetime
    data_version: Version
    evaluated_forecast_start_date: date
    cutoff_date: date
    actions: tuple[ActionReadiness,...]
    source_versions: SourceVersions
    scope_estimate: ScopeEstimate | None
    history_watermark: date | None
    planning_assessment: PlanningAssessment | None=None
    forecast_assessment: ForecastAssessment | None=None
