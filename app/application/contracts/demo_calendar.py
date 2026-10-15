"""Calendar declarations for detached retrospective benchmarks only."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, model_validator
from app.application.contracts.common import Contract, Nonblank
from app.application.contracts.forecast_challenger import Digest


class DemoCalendarAssumption(Contract):
    schema_version: Literal[1] = 1
    classification: Literal['DEMO_RETROSPECTIVE_ASSUMPTION'] = 'DEMO_RETROSPECTIVE_ASSUMPTION'
    use: Literal['OFFLINE_BENCHMARK_ONLY'] = 'OFFLINE_BENCHMARK_ONLY'
    source_revision: Digest
    calendar_file_sha256: Digest
    calendar_rows_digest: Digest
    store_id: UUID
    product_ids: tuple[UUID,...]
    timezone: Nonblank
    fields: tuple[Literal['closed','holiday'],...] = ('closed','holiday')
    availability_policy: Literal['assumed_known_before_all_feature_origins'] = 'assumed_known_before_all_feature_origins'
    authority: Literal['explicit_user_request_2026-10-15'] = 'explicit_user_request_2026-10-15'
    actor_kind: Literal['USER_IN_CONVERSATION'] = 'USER_IN_CONVERSATION'
    actor_identifier: None = None
    recorded_at: AwareDatetime
    historical_vintage_proof: Literal[False] = False
    production_eligible: Literal[False] = False

    @model_validator(mode='after')
    def exact_scope(self):
        if not self.product_ids or len(set(self.product_ids))!=len(self.product_ids):
            raise ValueError('ASSUMPTION_PRODUCT_SCOPE')
        if self.fields!=('closed','holiday'): raise ValueError('ASSUMPTION_FIELDS')
        return self
