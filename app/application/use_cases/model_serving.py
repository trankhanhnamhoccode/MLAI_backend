"""Supported operator config, explicit CAS; never train or choose latest artifact."""
from uuid import uuid4
from datetime import datetime
from collections.abc import Callable
import platform
from pydantic import SecretStr
from sqlalchemy import Engine
from app.config import Settings
from app.application.contracts.auth import AuthError
from app.application.contracts.model_serving import OperatorConfigurationCommand,ServingPolicy,ServingRecord
from app.application.use_cases.provisioning import AssistedProvisioning
from app.infrastructure.database.auth_session import auth_session
from app.models.planning_configuration import PlanningDefault,PlanningConfigurationRevision,PlanningConfigurationEvent
from app.models.model_serving import ModelServingConfiguration
from app.repositories.model_serving import lock_store


class ModelServingOperator:
    def __init__(self,engine: Engine,settings: Settings,clock: Callable[[],datetime]):
        self.engine,self.settings,self.clock=engine,settings,clock

    def configure(self,command: OperatorConfigurationCommand,operator: str,key: SecretStr) -> ServingRecord | str:
        command=OperatorConfigurationCommand.model_validate(command)
        AssistedProvisioning(self.engine,self.settings)._operator(operator,key)
        with auth_session(self.engine) as s:
            store=lock_store(s,command.store_id)
            if store is None or not store.active:
                raise AuthError('RESOURCE_NOT_FOUND',404)
            model=ModelServingConfiguration if command.action=='BASELINE' else PlanningDefault
            row=s.get(model,store.id)
            if (row.version if row else None)!=command.expected_version:
                raise AuthError('CONFIGURATION_VERSION_CHANGED',412)
            now=self.clock()
            if command.action=='BASELINE':
                policy=ServingPolicy(mode='BASELINE',artifact_identity=None,fallback_policy='ADR015_RECOGNIZED_ONLY',
                    dependency_versions=(('baseline','1'),('serialization','1'),('python',platform.python_version())))
                values=policy.model_dump(mode='json')
                if row and row.configuration_json==values:
                    return ServingRecord(version=row.version,policy=policy)
                if row is None:
                    row=ModelServingConfiguration(store_id=store.id);s.add(row)
                row.configuration_json=values
                row.operator_reference,row.evidence_reference=operator,command.evidence_reference
            else:
                values={'budget_limit':None,'paths':[{'path':'BASE','min_fill_rate_percent':'95','product_overrides':[]}]}
                if row and row.requirements_json==values:
                    return row.version
                if row is None:
                    row=PlanningDefault(store_id=store.id);s.add(row)
                row.requirements_json=values
            row.version,row.updated_at=str(uuid4()),now
            s.add(PlanningConfigurationRevision(store_id=store.id,resource='model' if command.action=='BASELINE' else 'defaults',
                version=row.version,record_json=dict(configuration=values,operator_reference=operator,evidence_reference=command.evidence_reference)))
            s.add(PlanningConfigurationEvent(id=uuid4(),store_id=store.id,actor_id=None,occurred_at=now,
                record_json=dict(action=command.action,operator_reference=operator,evidence_reference=command.evidence_reference,
                    before_version=command.expected_version,after_version=row.version,configuration=values)))
            s.flush();s.commit()
            return ServingRecord(version=row.version,policy=policy) if command.action=='BASELINE' else row.version
