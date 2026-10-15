"""S4.4 public and retained staging contracts. No canonical writes."""

from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from decimal import Decimal
import re
from pydantic import (
    Field,
    ConfigDict,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
    field_serializer,
)
from app.application.contracts.auth import Pagination
from app.application.contracts.import_scalars import ImportDTO as DTO, Text
from app.application.contracts.planning_export import ExportJobContext,ExportJobResult
from app.application.contracts.import_history import HistoryValue

Code = Annotated[
    StrictStr,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Version = Annotated[StrictStr, Field(min_length=1, max_length=128)]
Schema = Literal[
    "sales",
    "recipes",
    "inventory_count",
    "opening_stock",
    "inventory_receipts",
    "products",
    "ingredients",
    "suppliers",
    "supplier_terms",
    "payable_fees",
    "scope_declarations",
    "calendar_events",
    "promotion_observations",
    "usage_history",
    "purchase_history",
]
Quantity = Annotated[
    StrictStr, Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$", max_length=200)
]


class SourceLocation(DTO):
    file_id: UUID
    sheet_id: UUID
    row_number: int | None = None
    source_column_index: int | None = None
    record_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None


class Notice(DTO):
    code: str
    severity: Literal["WARNING", "ERROR"]
    field: str | None = None
    entity: str | None = None
    impact: str | None = None
    message: str
    source_location: SourceLocation | None = None


class ImportMeta(DTO):
    request_id: str
    warnings: tuple[Notice, ...] = ()
    poll_after_ms: int | None = None
    pagination: Pagination | None = None


T = TypeVar("T")


class ImportEnvelope(DTO, Generic[T]):
    data: T
    meta: ImportMeta
    error: None


class DraftRequest(DTO):
    data_date: date


class AnalyzeRequest(DTO):
    file_set_version: Version
    accepted_file_ids: tuple[UUID, ...] = Field(min_length=1, max_length=20)
    acknowledged_rejected_client_file_ids: tuple[UUID, ...]

    @model_validator(mode="after")
    def unique(self):
        for v in (self.accepted_file_ids, self.acknowledged_rejected_client_file_ids):
            if len(v) != len(set(v)):
                raise ValueError("DUPLICATE_FILE_ID")
        return self


class PreviewRequest(DTO):
    phase: Literal["preview"]
    mapping_revision: Version


class ConfirmReviewRequest(DTO):
    phase: Literal["confirm_review"]
    preview_id: UUID
    preview_digest: Version
    mapping_revision: Version
    confirm: Literal[True]
    reason: Text

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("EXPLICIT_TRUE_REQUIRED")
        return value


class ReviewConfirmation(DTO):
    version: Literal["import_review/1"] = "import_review/1"
    confirmation_id: UUID
    import_id: UUID
    preview_id: UUID
    preview_digest: str
    file_set_version: str
    source_digest: str
    mapping_revision: str
    binding_digest: str
    reviewed_import_revision: str
    read_set_digest: str
    confirmed_by: UUID
    confirmed_at: datetime
    reason: Text
    content_digest: str

    @field_validator("confirmed_at")
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return value


class ConfirmationResult(DTO):
    phase: Literal["confirm_review"] = "confirm_review"
    import_revision: str
    confirmation: ReviewConfirmation
    canonical_commit_supported: bool = False


class SheetTypeResolution(DTO):
    kind: Literal["sheet_type"]
    sheet_type: Schema | None
    ignored: StrictBool = False
    acknowledgment: StrictBool = False
    reason: Text

    @model_validator(mode="after")
    def selection(self):
        if self.ignored != (self.sheet_type is None):
            raise ValueError("SELECT_TYPE_OR_IGNORE")
        if self.ignored and not self.acknowledgment:
            raise ValueError("IGNORE_ACKNOWLEDGMENT_REQUIRED")
        return self


class SalesResolution(DTO):
    row_id: UUID
    action: Literal["replace_daily_total", "confirm_disjoint_merge"]
    report_business_key: Text
    evidence_reference: Text
    reason: Text
    disjoint_assertion: StrictBool | None


class SupplierConfirmation(DTO):
    action_id: UUID
    reason: Text


class HistoryCorrectionConfirmation(DTO):
    row_id: UUID
    expected_version: Version
    reason: Text


class CommitRequest(DTO):
    phase: Literal["commit"]
    preview_id: UUID
    preview_digest: str
    confirm: Literal[True]
    reason: Text | None = None
    resolutions: tuple[SalesResolution, ...]
    supplier_changes: tuple[SupplierConfirmation, ...] = ()
    history_corrections: tuple[HistoryCorrectionConfirmation, ...] = ()

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("EXPLICIT_TRUE_REQUIRED")
        return value


class PlannedArrivalExpiryRule(DTO):
    basis: Literal["ARRIVAL_PLUS_DECLARED_SHELF_LIFE_DAYS"]
    evidence_reference: Text


class TermPeriodAmendment(DTO):
    supplier_term_id: UUID
    expected_version: Version
    effective_to: date
    reason: Text


class FeePeriodAmendment(DTO):
    fee_id: UUID
    expected_version: Version
    effective_to: date
    reason: Text


class StockoutAlias(DTO):
    token: Text
    value: StrictBool | None


class SourceContext(DTO):
    kind: Literal["source_context"]
    source_system_key: Code
    report_type: Code
    evidence_reference: Text
    missing_stockout: Literal['quantity_only', 'not_provided'] | None = None
    stockout_aliases: tuple[StockoutAlias, ...] = Field(default=(), max_length=32)
    sales_semantics: Literal["daily_total", "disjoint_contribution"] | None = None
    inventory_semantics: Literal["lot_stock_count", "actual_receipt"] | None = None
    decimal_locale: Literal["dot", "comma"] | None = None
    date_format: Literal["ISO", "DMY_SLASH", "MDY_SLASH", "EXCEL_SERIAL"] | None = None
    pack_cost_basis: Literal["PER_PACK", "PER_SOURCE_UNIT"] | None = Field(
        default=None, json_schema_extra={"deprecated": True},
        description="Historical readability only; new proposals require supplier price_basis/price_quantity/price_unit declarations.")
    planned_arrival_expiry_rule: PlannedArrivalExpiryRule | None = None
    term_period_amendments: tuple[TermPeriodAmendment, ...] = ()
    fee_period_amendments: tuple[FeePeriodAmendment, ...] = ()

    @model_validator(mode="after")
    def unique_amendments(self):
        if len({a.token for a in self.stockout_aliases}) != len(self.stockout_aliases):
            raise ValueError('DUPLICATE_STOCKOUT_ALIAS')
        if len({a.supplier_term_id for a in self.term_period_amendments}) != len(
            self.term_period_amendments
        ):
            raise ValueError("DUPLICATE_TERM_AMENDMENT")
        if len({a.fee_id for a in self.fee_period_amendments}) != len(self.fee_period_amendments):
            raise ValueError("DUPLICATE_FEE_AMENDMENT")
        return self


class IdentityBinding(DTO):
    kind: Literal["identity_binding"]
    canonical_id: UUID


class Factor(DTO):
    numerator: Quantity
    denominator: Quantity

    @model_validator(mode="after")
    def positive(self):
        if Decimal(self.numerator) <= 0 or Decimal(self.denominator) <= 0:
            raise ValueError("POSITIVE_FACTOR_REQUIRED")
        return self


class Conversion(DTO):
    kind: Literal["declared_conversion"]
    from_unit: Annotated[StrictStr, Field(min_length=1, max_length=32)]
    to_unit: Annotated[StrictStr, Field(min_length=1, max_length=32)]
    factor: Factor
    evidence_reference: Text


class Ignored(DTO):
    kind: Literal["ignored_optional_field"]
    evidence_reference: Text


from app.application.contracts.import_scalars import (
    ProductMetadata,
    IngredientMetadata,
    SupplierMetadata,
)


class NewEntity(DTO):
    kind: Literal["new_entity_proposal"]
    entity: Literal["product", "ingredient", "supplier"]
    source_business_key: Text
    metadata: ProductMetadata | IngredientMetadata | SupplierMetadata
    evidence_reference: Text

    @model_validator(mode="after")
    def variant(self):
        expected = {
            "product": ProductMetadata,
            "ingredient": IngredientMetadata,
            "supplier": SupplierMetadata,
        }[self.entity]
        if not isinstance(self.metadata, expected):
            raise ValueError("INVALID_ENTITY_METADATA")
        return self


from app.application.contracts.import_field_values import (
    SharedRule,
    ImportValue,
    SharedValueResolution,
)

Resolution = Annotated[
    SourceContext
    | IdentityBinding
    | Conversion
    | Ignored
    | NewEntity
    | SheetTypeResolution
    | SharedValueResolution,
    # Shared source declarations remain separate from identity bindings.
    Field(discriminator="kind"),
]


class ResolveRequest(DTO):
    resolution: Resolution


class TargetRequest(DTO):
    target_field: Annotated[StrictStr, Field(min_length=1, max_length=128)]


from app.application.contracts.mapping_submissions import QueueReference, MappingSubmission
from app.application.contracts.collaboration import NotificationDelivery


class Approve(QueueReference, DTO):
    decision: Literal["approve_activate"]
    proposal_revision: Version
    expected_active_version: Version | None
    reason: Text


class Reject(QueueReference, DTO):
    decision: Literal["reject"]
    proposal_revision: Version
    reason: Text


class Retire(DTO):
    decision: Literal["retire"]
    active_version: Version
    reason: Text


class RequestChanges(QueueReference, DTO):
    decision: Literal['request_changes']
    proposal_revision: Version
    reason: Text


class FieldBinding(DTO):
    source_column_index: int
    source_header: str
    target_field: str | None
    requiredness: Literal["required", "optional"]
    ignored: bool
    evidence_reference: str | None = None
    origin: Literal["RULE", "QWEN", "REUSED", "MANUAL", "NONE"] = "NONE"
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None


class ProfileScope(DTO):
    source_system_key: Code
    report_type: Code
    schema_version: Literal["import_schema/1"] = "import_schema/1"


class Structure(DTO):
    sheet_roles: tuple[str, ...]
    header_rules: tuple[str, ...]
    schema_signature: str


class IdentityRule(DTO):
    entity: Literal["product", "ingredient", "lot", "supplier"]
    source_token: str
    canonical_id: UUID
    reference_state: Literal["existing", "reserved"] = "existing"


class EntityReservation(DTO):
    proposal_id: UUID
    entity: Literal["product", "ingredient", "supplier"]
    source_business_key: str
    reserved_canonical_id: UUID
    metadata: ProductMetadata | IngredientMetadata | SupplierMetadata
    evidence_reference: str
    approval_revision: str


class Normalization(DTO):
    rule_id: str
    kind: Literal["decimal_locale", "date_format", "unit_label_alias", "exact_scale", "stockout_alias"]
    fields: tuple[str, ...]
    parameter: str
    evidence_reference: str


class SourceProvenance(DTO):
    declared_by: UUID
    evidence_references: tuple[str, ...]
    verification: Literal["USER_DECLARED"] = "USER_DECLARED"
    owner_reviewed: bool = False


class ProfileSpec(DTO):
    scope: ProfileScope
    schema: Schema
    structure: Structure
    field_bindings: tuple[FieldBinding, ...]
    identity_rules: tuple[IdentityRule, ...] = ()
    entity_proposals: tuple[EntityReservation, ...] = ()
    aliases: tuple[IdentityRule, ...] = ()
    normalizations: tuple[Normalization, ...] = ()
    conversions: tuple[Conversion, ...] = ()
    sales_semantics: Literal["daily_total", "disjoint_contribution"] | None = None
    inventory_semantics: Literal["lot_stock_count", "actual_receipt"] | None = None
    planned_arrival_expiry_rule: PlannedArrivalExpiryRule | None = None
    term_period_amendments: tuple[TermPeriodAmendment, ...] = ()
    fee_period_amendments: tuple[FeePeriodAmendment, ...] = ()
    source_provenance: SourceProvenance
    shared_field_bindings: tuple[SharedRule, ...] = Field(default=(), max_length=64)

    def supports_recipe_basis(self) -> bool:
        """Historical profiles remain readable, but cannot execute implicit basis."""
        return self.schema != "recipes" or any(
            b.target_field == "recipes.quantity_basis" and not b.ignored
            for b in self.field_bindings
        ) or any(r.target_field == "recipes.quantity_basis" for r in self.shared_field_bindings)

    def supports_supplier_basis(self) -> bool:
        if self.schema != "supplier_terms":
            return True
        if any(r.parameter == "PACK_COST_FROM_SOURCE_UNIT_PRICE" for r in self.normalizations):
            return False
        targets = {b.target_field for b in self.field_bindings if not b.ignored}
        targets.update(r.target_field for r in self.shared_field_bindings)
        return {"supplier_terms." + f for f in (
            "price_basis", "price_quantity", "price_unit", "moq_basis",
            "minimum_order_quantity", "moq_unit")} <= targets

    @model_validator(mode="after")
    def shared_sources(self):
        if self.schema == 'inventory_receipts' and self.inventory_semantics != 'actual_receipt':
            raise ValueError('ACTUAL_RECEIPT_SEMANTICS_REQUIRED')
        shared = [r.target_field for r in self.shared_field_bindings]
        columns = [
            b.target_field
            for b in self.field_bindings
            if not b.ignored and b.target_field
        ]
        if (
            len(set(shared)) != len(shared)
            or len(set(columns)) != len(columns)
            or set(shared) & set(columns)
        ):
            raise ValueError("FIELD_SOURCE_CONFLICT")
        if any(not f.startswith(self.schema + ".") for f in shared):
            raise ValueError("INVALID_SHARED_SCHEMA")
        return self


class FileError(DTO):
    code: str
    message: str
    approval_request_allowed: Literal[False] = False


class FileReceipt(DTO):
    client_file_id: UUID
    file_id: UUID | None
    filename: str
    type: Literal["csv", "xlsx", "unknown"]
    size_bytes: int
    content_digest: str | None
    upload_status: Literal["uploaded", "rejected"]
    error: FileError | None


class FileView(FileReceipt):
    parse_status: Literal["not_started", "parsed", "failed"]


class Draft(DTO):
    import_id: UUID
    display_number: str
    store_id: UUID
    data_date: date
    status: str
    import_revision: str
    created_at: datetime
    imported_at: datetime | None
    file_count: int
    file_set_version: str


class UploadResult(DTO):
    import_id: UUID
    import_revision: str
    file_set_version: str
    items: tuple[FileReceipt, ...]
    warnings: tuple[Notice, ...] = ()


class UploadFailureDetails(DTO):
    items: tuple[FileReceipt, ...]
    import_revision: str
    file_set_version: str
    approval_request_allowed: Literal[False] = False


class UploadFailureInfo(DTO):
    code: Literal["UPLOAD_REJECTED"] = "UPLOAD_REJECTED"
    message: Literal["UPLOAD_REJECTED"] = "UPLOAD_REJECTED"
    details: UploadFailureDetails


class UploadFailure(DTO):
    data: None = None
    meta: ImportMeta
    error: UploadFailureInfo


class AnalysisAccepted(DTO):
    import_id: UUID
    analysis_id: UUID
    job_id: UUID
    status: Literal["analyzing"]
    import_revision: str


class PreviewAccepted(DTO):
    import_id: UUID
    status: Literal["previewing"]
    phase: Literal["preview"]
    job_id: UUID
    job_status: Literal["queued"]
    import_revision: str


class CommitAccepted(DTO):
    import_id: UUID
    status: Literal["committing"] = "committing"
    phase: Literal["commit"] = "commit"
    job_id: UUID
    job_status: Literal["queued"] = "queued"
    commit_id: UUID
    preview_id: UUID
    effective_plan_digest: str
    import_revision: str


class BindingRef(DTO):
    sheet_id: UUID
    profile_id: UUID
    version: str
    content_digest: str


class MappingIssue(DTO):
    mapping_id: UUID
    sheet_id: UUID
    issue_type: Literal[
        "source_context",
        "column",
        "identity",
        "conversion",
        "schema_blocker",
        "classification",
    ]
    code: str
    status: Literal[
        "auto_mapped", "resolved", "needs_confirmation", "ambiguous", "unmatched"
    ]
    source_location: SourceLocation
    source_header: str | None = None
    target_field: str | None = None
    samples: tuple[str, ...] = ()
    resolution_origin: Literal["APPROVED_PROFILE", "USER_PROPOSAL", "UNRESOLVED"]
    profile_ref: BindingRef | None = None
    resolution: ResolveRequest | None = None
    resolved_by: UUID | None = None
    suggested_target_field: str | None = None
    suggestion_origin: Literal["RULE", "QWEN", "REUSED", "MANUAL", "NONE"] = "NONE"
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    ignored: bool = False

    suggestion_reason: str | None = None
    candidate_targets: tuple[str, ...] = ()
    model_reason: Annotated[str, Field(max_length=200)] | None = None
    field_category: Literal["A", "B", "C", "D"] | None = None
    suggested_ignore: bool = False


class SuggestionDiagnostic(DTO):
    status: Literal["disabled", "unavailable", "invalid", "proposed"]
    model: str
    prompt_version: str = "mapping_prompt/2"
    schema_version: str = "sheet_suggestion/1"
    input_digest: str | None = None
    attempts: int = 0
    failure_code: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    http_status: int | None = None
    failure_stage: Literal["configuration", "input", "transport", "validation"] | None = None


class SheetInfo(DTO):
    file_id: UUID
    sheet_id: UUID
    name: str
    schema_signature: str
    row_count: int
    headers: tuple[str, ...]
    header_row: int = 1
    preamble_rows: tuple[int, ...] = ()
    preamble_samples: tuple[str, ...] = ()
    excel_date_system: Literal["1900", "1904"] | None = None
    suggestion_diagnostic: SuggestionDiagnostic | None = None
    profile_id: UUID | None
    selected_type: Schema | None = None
    suggested_type: Schema | None = None
    classification_origin: Literal["RULE", "QWEN", "REUSED", "MANUAL", "NONE"] = "NONE"
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    ignored: bool = False
    ignore_reason: str | None = None
    shared_field_bindings: tuple[SharedRule, ...] = Field(default=(), max_length=64)
    import_values: tuple[ImportValue, ...] = Field(default=(), max_length=64)

    @field_validator("name", mode="before")
    @classmethod
    def dates_and_content(cls, value, info):
        # Physical display hint may be unnamed. This is not a canonical entity name.
        return value


class Progress(DTO):
    total_fields: int
    completed_fields: int
    unresolved: int


class ProfileProposal(DTO):
    profile_id: UUID
    proposal_revision: str
    lifecycle_revision: str
    active_version: str | None
    spec: ProfileSpec | None
    missing_fields: tuple[str, ...]


class ApprovedContext(DTO):
    source_system_key: str
    report_type: str
    evidence_reference: str
    approved_by: UUID
    approved_at: datetime


class InspectedProfile(DTO):
    binding: BindingRef
    spec: ProfileSpec


class MappingCounterScope(DTO):
    file_id: UUID | None = None
    sheet_id: UUID | None = None
    review_only: bool = True
    status: Literal['auto_mapped','resolved','needs_confirmation','ambiguous','unmatched'] | None = None
    origin: Literal['RULE','QWEN','REUSED','MANUAL','NONE'] | None = None


class MappingStatusCounts(DTO):
    auto_mapped: int = 0
    resolved: int = 0
    needs_confirmation: int = 0
    ambiguous: int = 0
    unmatched: int = 0


class MappingOriginCounts(DTO):
    RULE: int = 0
    QWEN: int = 0
    REUSED: int = 0
    MANUAL: int = 0
    NONE: int = 0


class MappingIssueCounts(DTO):
    total: int
    by_status: MappingStatusCounts
    by_origin: MappingOriginCounts


class MappingCounters(DTO):
    batch: MappingIssueCounts
    filtered: MappingIssueCounts


class MappingSummary(DTO):
    import_id: UUID
    analysis_id: UUID
    mapping_revision: str
    progress: Progress
    files: tuple[FileView, ...]
    sheets: tuple[SheetInfo, ...]
    binding_refs: tuple[BindingRef, ...]
    profile_proposals: tuple[ProfileProposal, ...]
    can_preview: bool
    blockers: tuple[Notice, ...]
    allowed_actions: tuple[str, ...]
    approved_contexts: tuple[ApprovedContext, ...] = ()
    approved_profiles: tuple[InspectedProfile, ...] = ()
    warnings: tuple[Notice, ...] = ()
    counter_scope: MappingCounterScope | None = None
    counters: MappingCounters | None = None


class MappingList(DTO):
    items: tuple[MappingIssue, ...]
    counts: Progress
    mapping_revision: str = ''
    counter_scope: MappingCounterScope | None = None
    counters: MappingCounters | None = None


class FieldOption(DTO):
    key: str
    type: str
    requiredness: Literal["required", "optional"]
    unit_semantics: str | None = None
    support: Literal["supported", "source_only", "unsupported"]
    available: bool
    reason_code: str | None = None
    label: str = ""
    description: str = ""
    aliases: tuple[str, ...] = ()
    conditional_requirements: tuple[str, ...] = ()
    nullable: bool = False
    input_sources: tuple[Literal["excel", "binding", "shared_value"], ...] = ("excel",)
    allowed_shared_scopes: tuple[Literal["PROFILE_CONSTANT", "IMPORT_VALUE"], ...] = ()
    input_help: str = ""
    value_role: Literal[
        "canonical_candidate", "resolve_only", "source_only", "unsupported"
    ] = "canonical_candidate"


class SchemaDescriptor(DTO):
    schema_id: Schema
    label: str
    description: str
    supported: Literal[True] = True
    fields: tuple[FieldOption, ...]


class FieldOptions(DTO):
    schema: Schema | None
    schema_version: str
    schema_context_id: UUID
    mapping_revision: str
    duplicate_mapping_allowed: Literal[False] = False
    options: tuple[FieldOption, ...]
    schemas: tuple[SchemaDescriptor, ...] = ()


class MappingUpdated(DTO):
    mapping_id: UUID
    status: str
    mapping_revision: str
    progress: Progress
    sheets: tuple[SheetInfo, ...]
    proposal_revision: str | None
    approval_required: bool


class DecisionResult(DTO):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    profile_id: UUID
    approved_version: str | None
    active_version: str | None
    lifecycle_revision: str
    decision_id: UUID
    decided_at: datetime
    audit_id: UUID
    submission: MappingSubmission | None = None
    notification_delivery: NotificationDelivery = Field(default_factory=lambda: NotificationDelivery(status='not_required',event_id=None))


class SourceEvidenceCell(DTO):
    location: SourceLocation
    column_label: str | None
    raw_value: str | None
    cell_kind: Literal['text','numeric','boolean','date','empty','error']
    formula_present: bool


class MappingReviewSource(DTO):
    file_id: UUID
    filename: str
    sheet_id: UUID
    sheet_name: str
    source_system_key: str
    report_type: str
    schema_signature: Version
    evidence_references: tuple[str,...]


class ReviewEvidence(DTO):
    cells: tuple[SourceEvidenceCell,...]
    next_cursor: str | None
    total_count: int


class MappingReviewDetail(DTO):
    submission: MappingSubmission
    source: MappingReviewSource
    spec: ProfileSpec
    warnings: tuple[Notice,...]
    missing_fields: tuple[str,...]
    evidence: ReviewEvidence


from app.application.contracts.import_domains import CanonicalValue, SupplierTermSemantics


class Change(DTO):
    field: str
    before: str | None
    after: str | None
    delta: str | None = None


class FieldProvenance(DTO):
    field: str
    source_value: str | bool | int | None = None
    origin: Literal[
        "SOURCE_EXPLICIT",
        "DETERMINISTIC_DERIVED",
        "SYSTEM_ASSIGNED",
        "UNKNOWN",
        "AMBIGUOUS",
    ]
    applied_rule_ids: tuple[str, ...] = ()
    value_source: Literal[
        "SOURCE_COLUMN", "PROFILE_CONSTANT", "IMPORT_VALUE", "IDENTITY_BINDING"
    ] = "SOURCE_COLUMN"
    source_column_index: int | None = None
    declaration_id: UUID | None = None


class EntityRef(DTO):
    entity: Literal["product", "ingredient", "lot", "supplier", "supplier_term", "fee"]
    canonical_id: UUID
    path: str | None = None


class EntityRefs(DTO):
    product_id: UUID | None = None
    ingredient_id: UUID | None = None
    lot_id: UUID | None = None
    supplier_id: UUID | None = None
    supplier_term_id: UUID | None = None
    fee_id: UUID | None = None
    ingredient_ids: tuple[UUID, ...] = ()


class ProvenanceValue(DTO):
    source_value: str | bool | int | None = None
    origin: Literal[
        "SOURCE_EXPLICIT",
        "DETERMINISTIC_DERIVED",
        "SYSTEM_ASSIGNED",
        "UNKNOWN",
        "AMBIGUOUS",
    ]
    applied_rule_ids: tuple[str, ...]
    value_source: Literal[
        "SOURCE_COLUMN", "PROFILE_CONSTANT", "IMPORT_VALUE", "IDENTITY_BINDING"
    ] = "SOURCE_COLUMN"
    source_column_index: int | None = None
    declaration_id: UUID | None = None


class NestedRecordProvenance(DTO):
    path: str
    source_location: SourceLocation
    provenance: dict[str, ProvenanceValue]


class RecipeLineProvenance(DTO):
    ingredient_id: UUID
    quantity_basis: Literal["PER_SERVING", "WHOLE_BATCH"] | None = None
    source_location: SourceLocation
    provenance: dict[str, ProvenanceValue]


class InventoryEffect(DTO):
    origin: Literal["OPENING_STOCK", "IMPORT_COUNT"]
    lot_id: UUID
    before_quantity: Quantity | None
    after_quantity: Quantity
    quantity_delta: Annotated[str, Field(pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$", max_length=201)]
    movement_type: Literal["COUNT_CORRECTION"] | None
    unit: str
    observed_at: datetime


from app.application.contracts.stock_writes import ReceiptIdentity


class ReceiptEffect(DTO):
    action: Literal['CREATE_RECEIPT','REUSE_RECEIPT','BLOCKED']
    source_identity: ReceiptIdentity
    receipt_id: UUID | None
    lot_id: UUID | None
    movement_id: UUID | None
    origin: Literal['ACTUAL_RECEIPT'] = 'ACTUAL_RECEIPT'
    movement_kind: Literal['receipt'] = 'receipt'
    quantity_delta: Quantity
    unit: str
    occurred_at: datetime
    recorded_at: datetime | None
    conflict_code: str | None


class ReceiptCommitReference(DTO):
    source_identity: ReceiptIdentity
    receipt_id: UUID
    lot_id: UUID
    movement_id: UUID
    action: Literal['CREATED','REUSED']
    audit_reference: UUID


class SalesContribution(DTO):
    source_system_key: Code
    report_type: Code
    business_report_key: Text
    semantics: Literal['daily_total', 'disjoint_contribution']
    quantity: Quantity
    is_stockout: StrictBool | None
    stockout_update: Literal['source', 'quantity_only', 'not_provided'] | None
    source_locations: tuple[SourceLocation, ...]
    provenance: tuple[FieldProvenance, ...]


class PreviewRow(DTO):
    row_id: UUID
    source_location: SourceLocation
    classification: Literal["NEW", "UNCHANGED", "CHANGED", "INVALID", "CONFLICT"]
    proposed_action: str
    entity_refs: tuple[EntityRef, ...]
    before: CanonicalValue | None
    after: CanonicalValue | None
    changes: tuple[Change, ...] = ()
    provenance: tuple[FieldProvenance, ...]
    blockers: tuple[Notice, ...] = ()
    warnings: tuple[Notice, ...] = ()
    confirmation_required: bool = False
    source_locations: tuple[SourceLocation, ...] = ()
    line_provenance: tuple[RecipeLineProvenance, ...] = ()
    nested_provenance: tuple[NestedRecordProvenance, ...] = ()
    nested_references: tuple[EntityRef, ...] = ()
    dependencies: tuple[UUID, ...] = ()
    canonical_domain: Schema | None = None
    target_reserved_or_existing_id: UUID | None = None
    expected_version: str | None = None
    normalized_source_quantity: Quantity | None = None
    normalized_source_stockout: StrictBool | None = None
    stockout_update: Literal['source', 'quantity_only', 'not_provided'] | None = None
    sales_contributions: tuple[SalesContribution, ...] = ()
    required_permissions: tuple[str, ...] = ()
    supplier_term_semantics: SupplierTermSemantics | None = None
    inventory_effect: InventoryEffect | None = None
    receipt_effect: ReceiptEffect | None = None

    @field_validator("before", "after", mode="before")
    @classmethod
    def canonical_value(cls, value):
        return value.model_dump() if hasattr(value, "model_dump") else value

    @field_validator("entity_refs", mode="before")
    @classmethod
    def read_refs(cls, value):
        if isinstance(value, dict):
            parsed = EntityRefs.model_validate(value)
            refs = [
                EntityRef(entity=k.removesuffix("_id"), canonical_id=v)
                for k, v in parsed.model_dump().items()
                if k.endswith("_id") and v is not None
            ]
            refs.extend(
                EntityRef(entity="ingredient", canonical_id=i)
                for i in parsed.ingredient_ids
            )
            return tuple(refs)
        return value

    @field_serializer("entity_refs", return_type=EntityRefs)
    def refs_wire(self, value):
        values = {}
        ingredients = []
        for r in value:
            if r.entity == "ingredient":
                ingredients.append(r.canonical_id)
            else:
                values[r.entity + "_id"] = r.canonical_id
        if len(ingredients) == 1:
            values["ingredient_id"] = ingredients[0]
        elif ingredients:
            values["ingredient_ids"] = tuple(ingredients)
        return EntityRefs(**values)

    @field_validator("provenance", mode="before")
    @classmethod
    def read_provenance(cls, value):
        if isinstance(value, dict):
            return tuple(
                FieldProvenance(
                    field=k, **ProvenanceValue.model_validate(v).model_dump()
                )
                for k, v in value.items()
            )
        return value

    @field_serializer("provenance", return_type=dict[str, ProvenanceValue])
    def provenance_wire(self, value):
        return {
            p.field: ProvenanceValue(**p.model_dump(exclude={"field"})) for p in value
        }


class PreviewGroup(DTO):
    canonical_domain: Schema
    required_write_action: str
    row_count: int
    planned_insert_count: int
    planned_update_count: int
    no_op_count: int
    blocked_count: int


class ClassificationCounts(DTO):
    NEW: int = 0
    UNCHANGED: int = 0
    CHANGED: int = 0
    INVALID: int = 0
    CONFLICT: int = 0


class PreviewSummary(DTO):
    preview_id: UUID
    digest: str
    created_at: datetime
    source_set_version: str
    mapping_bindings: tuple[BindingRef, ...]
    policy_version: Literal["import_mapping_policy/1"] = "import_mapping_policy/1"
    mode: Literal["atomic"] = "atomic"
    validation_status: Literal["ready", "blocked", "confirmation_required"]
    can_commit: bool = False
    required_actions: tuple[str, ...]
    groups: tuple[PreviewGroup, ...]
    counts: ClassificationCounts
    blockers: tuple[Notice, ...]
    warnings: tuple[Notice, ...]
    confirmed_resolutions_version: None = None


class ReceiptPlannedEffect(ReceiptEffect):
    kind: Literal['receipt'] = 'receipt'


class CatalogEffect(DTO):
    kind: Literal['catalog'] = 'catalog'
    entity: Literal['product','ingredient','supplier']
    id: UUID
    action: Literal['create','reuse']
    expected_version: str | None


class CountEffect(DTO):
    kind: Literal['count'] = 'count'
    lot_id: UUID
    before_quantity: Quantity
    after_quantity: Quantity
    delta: Annotated[str, Field(pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$", max_length=201)]
    unit: str
    expected_version: str


class RecipeEffect(DTO):
    kind: Literal['recipe'] = 'recipe'
    product_id: UUID
    recipe_id: UUID | None
    identity_availability: Literal['available','not_reserved']
    recipe_version: int
    action: Literal['create_version','reuse'] = 'create_version'
    effective_from: date
    effective_to: date | None
    dependency_ids: tuple[UUID,...]


class SupplierEffect(DTO):
    kind: Literal['supplier'] = 'supplier'
    entity: Literal['supplier_term','payable_fee']
    id: UUID
    action: Literal['create_version','close_period','reuse']
    expected_version: str | None


class SalesEffect(DTO):
    kind: Literal['sales'] = 'sales'
    product_id: UUID
    date: date
    action: Literal['record','replace','merge','reuse']
    before_quantity: Quantity | None
    after_quantity: Quantity
    unit: str
    expected_version: str | None


class DeclarationEffect(DTO):
    kind: Literal['declaration'] = 'declaration'
    id: UUID
    action: Literal['declare','reuse']
    dependency_ids: tuple[UUID,...]
    expected_version: str | None


class OpeningEffect(DTO):
    kind: Literal['opening_stock'] = 'opening_stock'
    lot_id: UUID
    action: Literal['create','reuse']
    quantity_delta: Quantity
    unit: str
    observed_at: datetime


class HistoryEffect(DTO):
    kind: Literal['history'] = 'history'
    domain: Literal['calendar_events','promotion_observations','usage_history','purchase_history']
    id: UUID
    action: Literal['record','reuse']
    expected_version: str | None


PlannedEffect = Annotated[ReceiptPlannedEffect | CatalogEffect | CountEffect | RecipeEffect |
    SupplierEffect | SalesEffect | DeclarationEffect | OpeningEffect | HistoryEffect, Field(discriminator='kind')]


class SourceEffectRow(PreviewRow):
    source_cells: tuple[SourceEvidenceCell,...]
    planned_effect: PlannedEffect | None
    source_evidence_availability: Literal['available','partial','unavailable']
    source_cells_truncated: bool


class PreviewScope(DTO):
    file_id: UUID | None = None
    sheet_id: UUID | None = None
    classification: Literal['NEW','UNCHANGED','CHANGED','INVALID','CONFLICT'] | None = None


class RawSourceRowCount(DTO):
    availability: Literal['available','unavailable']
    count: int | None


class PreviewActionGroupCount(DTO):
    canonical_domain: str | None
    proposed_action: str
    action_count: int
    blocked_action_count: int
    warning_action_count: int


class NoticeActionCount(DTO):
    code: str
    action_count: int


class ScopedPreviewAggregate(DTO):
    scope: PreviewScope
    raw_source_rows: RawSourceRowCount
    logical_action_count: int
    by_classification: ClassificationCounts
    groups: tuple[PreviewActionGroupCount,...]
    blockers: tuple[NoticeActionCount,...]
    warnings: tuple[NoticeActionCount,...]


class PreviewAggregates(DTO):
    preview_id: UUID
    preview_digest: str
    batch: ScopedPreviewAggregate
    selected: ScopedPreviewAggregate
    files: tuple[ScopedPreviewAggregate,...]
    sheets: tuple[ScopedPreviewAggregate,...]


class PreviewPage(DTO):
    aggregates: PreviewAggregates | None = None
    mapping_revision: str
    read_set_digest: str
    source_evidence_digest: str | None
    summary: PreviewSummary
    rows: tuple[SourceEffectRow | PreviewRow, ...]
    rows_page: Pagination
    stale: bool


from app.application.contracts.import_domains import (
    SupplierSource,
    TermValue,
    FeeSource,
    DeclarationSource,
)


class SourceIdentity(DTO):
    source_system_key: str
    source_record_key: str | None


class ConfigurationRevision(DTO):
    canonical_id: UUID
    version: str
    source_identity: SourceIdentity
    state: Literal["staged", "committed"] = "staged"
    expected_before_version: str | None
    provenance: dict[str, ProvenanceValue]


class SupplierConfiguration(ConfigurationRevision):
    payload: SupplierSource


class TermConfiguration(ConfigurationRevision):
    payload: TermValue
    internal_term_version: int


class FeeConfiguration(ConfigurationRevision):
    payload: FeeSource


class DeclarationConfiguration(ConfigurationRevision):
    payload: DeclarationSource


class StagedConfigurationCell(DTO):
    source_column_index: int
    source_header: str
    raw_value: str | None
    kind: Literal["text", "numeric", "boolean", "date", "empty", "error"]
    proposed_target_field: str | None


class StagedConfigurationRow(DTO):
    schema: Schema | None
    source_location: SourceLocation
    cells: tuple[StagedConfigurationCell, ...]
    normalization_status: Literal["NOT_PREVIEWED"] = "NOT_PREVIEWED"


class Configurations(DTO):
    suppliers: tuple[SupplierConfiguration, ...]
    terms: tuple[TermConfiguration, ...]
    fees: tuple[FeeConfiguration, ...]
    declarations: tuple[DeclarationConfiguration, ...]
    preview_id: UUID | None
    preview_digest: str | None
    blocked_row_ids: tuple[UUID, ...]
    rows_page: Pagination
    analysis_rows: tuple[StagedConfigurationRow, ...] = ()
    basis: Literal["analysis", "preview"] = "preview"
    stale: bool = False


class SourceSet(DTO):
    version: str
    sealed: bool
    accepted_file_ids: tuple[UUID, ...]
    digest: str


class ImportQuota(DTO):
    accepted_file_count: Annotated[StrictInt, Field(ge=0, le=20)]
    accepted_total_bytes: Annotated[StrictInt, Field(ge=0, le=100 * 1024 * 1024)]
    remaining_file_slots: Annotated[StrictInt, Field(ge=0, le=20)]
    remaining_bytes: Annotated[StrictInt, Field(ge=0, le=100 * 1024 * 1024)]


class ImportRead(Draft):
    quota: ImportQuota
    active_job_id: UUID | None
    files: tuple[FileView, ...]
    files_page: Pagination
    source_set: SourceSet
    allowed_actions: tuple[str, ...]
    preview: PreviewPage | None
    completion_available: bool = False
    configurations: Configurations | None = None
    review_confirmation: ReviewConfirmation | None = None
    confirmation_usable: bool = False


class JobContext(DTO):
    store_id: UUID
    import_id: UUID


class AnalysisResult(DTO):
    resource_type: Literal["import_analysis"]
    resource_id: UUID
    analysis_id: UUID


class PreviewResult(DTO):
    resource_type: Literal["import_preview"]
    resource_id: UUID
    preview_id: UUID


class CompletionResult(DTO):
    resource_type: Literal["import_completion"] = "import_completion"
    resource_id: UUID
    commit_id: UUID


class CompletionSummary(DTO):
    files: int
    sheets: int
    rows: int
    mapped_fields: int
    errors: Literal[0] = 0
    warnings: int
    counts: ClassificationCounts
    inserted_record_count: int
    changed_record_count: int
    no_op_count: int


class InventoryImpact(DTO):
    updated: bool = False
    affected_ingredient_count: int | None = None
    changed_record_count: int | None = None


class MenuImpact(DTO):
    updated: bool
    affected_product_count: int | None
    changed_record_count: int | None


class SalesImpact(DTO):
    updated: bool
    added_record_count: int
    changed_record_count: int


class CatalogImpact(DTO):
    created_product_count: int
    created_ingredient_count: int


class ConfigurationImpact(DTO):
    updated: bool = False
    created_count: int = 0
    changed_count: int = 0


class UpdatedResources(DTO):
    inventory: InventoryImpact
    menu: MenuImpact
    sales: SalesImpact
    catalog: CatalogImpact
    suppliers: ConfigurationImpact = Field(default_factory=ConfigurationImpact)
    terms: ConfigurationImpact = Field(default_factory=ConfigurationImpact)
    fees: ConfigurationImpact = Field(default_factory=ConfigurationImpact)
    declarations: ConfigurationImpact = Field(default_factory=ConfigurationImpact)


from app.application.contracts.readiness import CompletionReadinessIssue,CompletionReadinessDetails
from app.application.contracts.readiness import ActionReadiness


class CompletionActionReadiness(ActionReadiness):
    action: Literal["import", "menu", "inventory"]
    availability: Literal["ready","blocked","unknown"] = "unknown"
    can_execute: bool = False
    data_status: Literal["valid","invalid","incomplete","unknown"] = "unknown"
    execution_status: Literal["available","unavailable","unknown"] = "unknown"
    blockers: tuple[CompletionReadinessIssue, ...] = ()
    warnings: tuple[CompletionReadinessIssue, ...] = (CompletionReadinessIssue(code='EXECUTION_UNAVAILABLE',source='runtime',scope='STORE',entity_id=None,affected_dates=(),details=CompletionReadinessDetails()),)
    result_assessment: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


class OmittedAction(DTO):
    action: Literal["import", "menu", "inventory"]
    reason: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"


class CompletionReadiness(DTO):
    evaluated_at: datetime
    as_of_date: date
    data_version: str
    actions: tuple[CompletionActionReadiness, ...]
    evaluated_actions: tuple[Literal["import", "menu", "inventory"], ...]
    omitted_actions: tuple[OmittedAction, ...]


class CommitRowReference(DTO):
    row_id: UUID
    canonical_domain: Schema
    canonical_id: UUID
    source_location: SourceLocation
    source_locations: tuple[SourceLocation, ...] = ()
    line_provenance: tuple[RecipeLineProvenance, ...] = ()
    nested_provenance: tuple[NestedRecordProvenance, ...] = ()
    provenance: dict[str, ProvenanceValue]
    canonical_version: str | None = None
    movement_ids: tuple[UUID, ...] = ()
    nested_references: tuple[EntityRef, ...] = ()
    supplier_term_semantics: SupplierTermSemantics | None = None
    inventory_effect: InventoryEffect | None = None
    sales_contributions: tuple[SalesContribution, ...] = ()
    history_record: HistoryValue | None = None
    receipt_effect: ReceiptEffect | None = None
    receipt_reference: ReceiptCommitReference | None = None


class ImportCompletion(DTO):
    import_id: UUID
    status: Literal["completed", "completed_with_warnings"]
    data_date: date
    outcome: Literal["committed", "no_changes"]
    mode: Literal["atomic"] = "atomic"
    completed_at: datetime
    commit_id: UUID
    preview_id: UUID
    effective_plan_digest: str
    mapping_bindings: tuple[BindingRef, ...]
    summary: CompletionSummary
    updated_resources: UpdatedResources
    readiness: CompletionReadiness
    audit_reference: UUID
    canonical_references: tuple[CommitRowReference, ...]


class ParseFailureLocation(DTO):
    file_id: UUID
    sheet_name: str | None = None
    row_number: int | None = None
    source_column_index: int | None = None


class JobErrorDetails(DTO):
    source_locations: tuple[ParseFailureLocation, ...] = ()
    blockers: tuple[Notice, ...] = ()
    approval_request_allowed: Literal[False] = False


class JobError(DTO):
    code: str
    message: str
    details: JobErrorDetails = Field(default_factory=JobErrorDetails)


class JobView(DTO):
    job_id: UUID
    operation: Literal["import_analyze", "import_preview", "import_commit", "planning_pdf_export"]
    status: Literal["queued", "running", "completed", "failed"]
    stage: Literal["queued", "parsing", "mapping", "validating", "committing", "rendering", "completed", "failed"]
    progress: float | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    context: JobContext | ExportJobContext
    result: (
        Annotated[AnalysisResult | PreviewResult | CompletionResult | ExportJobResult, Field(discriminator="resource_type")]
        | None
    )
    error: JobError | None
