"""Internal acceptance seam uses current configuration in caller transaction."""
from datetime import date
from uuid import UUID,uuid4
import pytest
from sqlalchemy.orm import Session
from app.application.planning_configuration_resolution import resolve_configuration_in_transaction
from app.application.contracts.planning_configuration import ConfigurationError
from app.models.planning_configuration import PlanningBudget,SavedRequirement
from tests.integration.test_planning_configuration_public import env,config,save,base,cap
from scripts.decision_capture_v2_demo_cases import synthetic_case_v2


def test_caller_owned_resolution_current_cap_and_archived_refusal(config):
    c=config;assert cap(c,'100',**{'If-None-Match':'*'}).status_code==201
    wire=save(c).json()['data'];ident=UUID(wire['saved_requirement_id'])
    policy=synthetic_case_v2()[0].procurement.policy
    request=dict(requirements_mode='saved',saved_requirement_id=ident,forecast_start_date=date(2026,10,10))
    with Session(c[0][1]) as s:
        result=resolve_configuration_in_transaction(s,c[1].store_id,request,policy,c[0][4][0])
        assert result.status=='RESOLVED' and result.resolution.budget.amount==100
        assert s.in_transaction()
        s.rollback()
    assert cap(c,'0',**{'If-Match':'"'+wire.get('budget_version','missing')+'"'}).status_code==412
    with Session(c[0][1]) as s:
        current=s.get(PlanningBudget,c[1].store_id).version
    assert cap(c,'0',**{'If-Match':'"'+current+'"'}).status_code==200
    with Session(c[0][1]) as s:
        result=resolve_configuration_in_transaction(s,c[1].store_id,request,policy,c[0][4][0])
        assert result.status=='RESOLVED' and result.resolution.budget.amount==0
    response=c[0][5].put(base(c)+'/planning-requirements/'+str(ident),json={'state':'archived'},headers={**c[3],'If-Match':'"'+wire['version']+'"','Idempotency-Key':str(uuid4())})
    assert response.status_code==200,response.text
    with Session(c[0][1]) as s:
        with pytest.raises(ConfigurationError):resolve_configuration_in_transaction(s,c[1].store_id,request,policy,c[0][4][0])
