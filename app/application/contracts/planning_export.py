"""Accepted N10 and purpose-specific durable PDF intent; no solver inputs."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator
from app.application.contracts.auth import DTO
from app.application.contracts.common import Contract
from app.application.contracts.planning_public import OptionId
from app.application.contracts.planning_setup import Version
from app.application.contracts.planning_run import PlanningClaim
from app.application.planning_serialization import digest
from app.application.contracts.discovery import DiscoveryMeta


class ExportRequest(DTO):
    format: Literal['pdf']
    option_id: OptionId | None=Field(...)
    locale: Literal['vi']


class ExportAccepted(DTO):
    export_id: UUID
    run_id: UUID
    option_id: OptionId
    status: Literal['queued']='queued'
    job_id: UUID
    result_digest: Version
    render_version: Literal['planning-pdf/1']='planning-pdf/1'


class ExportMeta(DTO):
    request_id: str
    poll_after_ms: Literal[2000]=2000


class ExportEnvelope(DTO):
    data: ExportAccepted
    meta: ExportMeta
    error: None


class ExportSummary(DTO):
    export_id: UUID
    run_id: UUID
    job_id: UUID
    option_id: OptionId
    created_by_user_id: UUID
    created_at: AwareDatetime
    status: Literal['queued','running','completed','failed']
    result_digest: Version
    render_version: str
    version: Version
    artifact_availability: Literal['pending','available','missing','unverifiable','failed']
    completed_at: AwareDatetime | None
    error_code: str | None
    download_url: str | None
    sha256: str | None
    byte_count: int | None
    media_type: Literal['application/pdf']='application/pdf'
    allowed_actions: tuple[Literal['poll','download','request_new_export'],...]


class ExportCollection(DTO):
    items: tuple[ExportSummary,...]


class ExportCollectionEnvelope(DTO):
    data: ExportCollection
    meta: DiscoveryMeta
    error: None


class ExportJobContext(DTO):
    store_id: UUID
    run_id: UUID
    export_id: UUID


class ExportJobResult(DTO):
    resource_type: Literal['planning_pdf_export']='planning_pdf_export'
    resource_id: UUID
    run_id: UUID
    option_id: OptionId
    download_url: str
    sha256: str=Field(pattern=r'^[0-9a-f]{64}$')
    byte_count: int=Field(gt=0,strict=True)
    media_type: Literal['application/pdf']='application/pdf'

    @model_validator(mode='after')
    def relative_resource(self):
        if self.download_url!=f'/api/v1/procurement-plans/{self.run_id}/exports/{self.resource_id}':
            raise ValueError('Export download must reference its owning retained resource')
        return self


class ExportRecord(Contract):
    storage_version: Literal['planning_export/1']='planning_export/1'
    export_id: UUID
    job_id: UUID
    run_id: UUID
    store_id: UUID
    actor_id: UUID
    session_digest: str=Field(pattern=r'^[0-9a-f]{64}$')
    key_digest: str=Field(pattern=r'^[0-9a-f]{64}$')
    request_digest: str=Field(pattern=r'^[0-9a-f]{64}$')
    request: ExportRequest
    receipt: ExportAccepted
    created_at: AwareDatetime
    status: Literal['queued','running','completed','failed']='queued'
    started_at: AwareDatetime | None=None
    completed_at: AwareDatetime | None=None
    claim: PlanningClaim | None=None
    result: ExportJobResult | None=None
    error_code: str | None=None
    attempt: int=Field(default=1,ge=1,le=2,strict=True)

    @model_validator(mode='after')
    def reconcile(self):
        receipt=self.receipt
        if (receipt.export_id,receipt.job_id,receipt.run_id)!=(self.export_id,self.job_id,self.run_id):
            raise ValueError('Receipt identity differs from intent')
        if self.request.option_id is not None and self.request.option_id!=receipt.option_id:
            raise ValueError('Resolved option differs from explicit request')
        if self.request_digest!=digest('export-request',dict(run_id=self.run_id,request=self.request)):
            raise ValueError('Original request digest differs')
        if self.status=='queued':
            if any(v is not None for v in (self.started_at,self.completed_at,self.claim,self.result,self.error_code)):raise ValueError('Queued intent has execution facts')
        else:
            if self.claim is None or self.started_at is None or self.started_at<self.created_at:raise ValueError('Execution lacks valid claim/start')
            if self.claim.generation!=self.attempt:raise ValueError('Claim generation differs from controlled attempt')
            if self.status=='running':
                if any(v is not None for v in (self.completed_at,self.result,self.error_code)):raise ValueError('Running intent has terminal facts')
            else:
                if self.completed_at is None or self.completed_at<self.started_at:raise ValueError('Terminal intent lacks completion')
                if self.status=='completed':
                    if self.result is None or self.error_code is not None:raise ValueError('Completed intent lacks artifact proof')
                    if (self.result.resource_id,self.result.run_id,self.result.option_id)!=(self.export_id,self.run_id,receipt.option_id):raise ValueError('Artifact resource differs')
                elif self.result is not None or not self.error_code:raise ValueError('Failed intent lacks error')
        return self
