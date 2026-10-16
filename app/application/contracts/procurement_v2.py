"""Explicit procurement/2; effective ratios only, no API/default/saved parser."""
from typing import Literal
from uuid import UUID
from pydantic import model_validator, ValidationInfo
from app.application.contracts.common import Contract, Nonblank, Strategy
from app.application.contracts.procurement import (
    ProcurementInput, ProcurementPolicy, ProductFloor, Ratio, ProcurementCandidate,
    ConstraintCoverage, SolverEvidence, Count, PositiveCount,
)
from app.application.contracts.serving import Quantity


class PathRequirement(Contract):
    path: Literal['LOW', 'BASE', 'HIGH']
    minimum: Ratio
    overrides: tuple[ProductFloor, ...]

    @model_validator(mode='after')
    def unique(self):
        if len({p.product_id for p in self.overrides}) != len(self.overrides):
            raise ValueError('Duplicate Product override')
        object.__setattr__(self, 'overrides', tuple(sorted(self.overrides, key=lambda p:p.product_id)))
        return self


class EffectiveRequirements(Contract):
    paths: tuple[PathRequirement, ...]
    provenance: Nonblank

    @model_validator(mode='after')
    def explicit(self):
        if not self.paths or len({p.path for p in self.paths}) != len(self.paths):
            raise ValueError('Effective requirements need unique nonempty paths')
        object.__setattr__(self, 'paths', tuple(sorted(self.paths, key=lambda p:p.path)))
        return self


class ProcurementPolicyV2(ProcurementPolicy):
    policy_id: Literal['procurement_api_policy']
    service_units: Literal['PER_PRODUCT_HORIZON_RATIO']
    fallback: Literal['MAX_MIN_PRODUCT_THEN_EQUAL_MEAN_THEN_MIN_OUTLAY']

    @model_validator(mode='after')
    def fixed_construction(self):
        if any(r.target != 1 or r.floors for r in self.rules):
            raise ValueError('API policy/1 construction is 100% each Product; no construction overrides')
        return self


class ProcurementInputV2(ProcurementInput):
    policy: ProcurementPolicyV2
    requirements: EffectiveRequirements

    @model_validator(mode='after')
    def effective(self):
        if self.prepared.capture_version != 2:
            raise ValueError('procurement/2 requires explicit capture_version=2')
        if any(o.product_id not in self.prepared.request.product_ids
               for p in self.requirements.paths for o in p.overrides):
            raise ValueError('Customer override outside captured Product scope')
        return self


class ProductGap(Contract):
    path: Literal['LOW', 'BASE', 'HIGH']
    product_id: UUID
    target: Ratio
    shortfall_quantity: Quantity


class SolverEvidenceV2(SolverEvidence):
    phase: Literal['TARGET', 'FALLBACK_MIN', 'FALLBACK_MEAN', 'FALLBACK_COST', 'REFERENCE']


class EvaluationEvidence(Contract):
    counts: tuple[Count, ...]
    stage: Nonblank
    hard_valid: bool
    customer_pass: bool
    construction_pass: bool
    reasons: tuple[Nonblank, ...]


class StrategyResultV2(Contract):
    strategy: Strategy
    construction_path: Literal['LOW', 'BASE', 'HIGH']
    execution: Literal['FINISHED', 'INCOMPLETE', 'ERROR', 'BLOCKED', 'NUMERIC_UNSUPPORTED']
    termination: Nonblank
    candidate: ProcurementCandidate | None
    selection_kind: Literal['TARGET', 'CUSTOMER_PASS_FALLBACK', 'REFERENCE_NOT_RANKED', 'NONE']
    customer_pass: bool
    construction_pass: bool
    customer_gaps: tuple[ProductGap, ...]
    construction_gaps: tuple[ProductGap, ...]
    customer_feasibility: Literal['PASS_EXISTS', 'NO_PASS_CERTIFIED', 'UNKNOWN']
    construction_feasibility: Literal['PASS_EXISTS', 'NO_PASS_CERTIFIED', 'UNKNOWN']
    proof: Literal['COMPLETE_EXACT_ENUMERATION', 'UNPROVEN']
    proof_scope: Literal['CAPTURED_FINITE_DOMAIN_ONLY']
    search_complete: bool
    domain_size: PositiveCount
    enumerated_vectors: Count
    solver: tuple[SolverEvidenceV2, ...]
    journal: tuple[EvaluationEvidence, ...]
    diagnostic: str | None


class ProcurementResultV2(Contract):
    semantics_version: Literal['procurement/2']
    input: ProcurementInputV2
    execution: Literal['FINISHED', 'INCOMPLETE', 'ERROR', 'BLOCKED', 'NUMERIC_UNSUPPORTED']
    coverage: tuple[ConstraintCoverage, ...]
    strategies: tuple[StrategyResultV2, ...]
    elapsed_seconds: float
    deadline_overrun_seconds: float
    unique_exact_evaluations: Count

    @model_validator(mode='after')
    def reconcile(self, info: ValidationInfo):
        if info.context and info.context.get('retained_consistency'):
            from app.application.retained_decision_validation import validate_procurement
            validate_procurement(self)
            return self
        from app.application.procurement_v2_validation import validate_result
        validate_result(self)
        return self
