"""Resource-budget representation is identity-bearing at the retained plan boundary."""
from typing import Annotated
from pydantic import Field
from app.application.forecast_challenger_serialization import canonical_bytes

ResourceSeconds = Annotated[int,Field(strict=True,gt=0,le=300)] | Annotated[float,Field(strict=True,gt=0,le=300,allow_inf_nan=False)]


def restore_plan(raw:dict,plan_type):
    """Full schema validation, followed by exact canonical round-trip verification.

    Preserve int/float for this resource field only. Do not normalize quantities,
    probabilities, IDs, money, or arbitrary numeric fields to rescue a digest.
    """
    plan=plan_type.model_validate(raw)
    if canonical_bytes(plan)!=canonical_bytes(raw):raise ValueError('FROZEN_PLAN_REPRESENTATION_MISMATCH')
    return plan
