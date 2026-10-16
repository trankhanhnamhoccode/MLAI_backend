"""AS03 explicit on-demand retained evidence question."""
from fastapi import APIRouter, Depends, Request, Response
from app.api.auth import session_token, mutations, strict_query
from app.api.import_staging import CSRF
from app.api.planning_public import PlanningKey, request_boundary
from app.application.contracts.planning_setup import ResourceId
from app.application.contracts.planning_configuration import ConfigurationError, ConfigurationErrorEnvelope
from app.application.contracts.assistant_chat import ChatRequest, ChatEnvelope
from app.application.contracts.plan_summary import SummaryMeta

router=APIRouter(prefix='/api/v1',tags=['Decision Assistant chat'],responses={
    code:{'model':ConfigurationErrorEnvelope} for code in (400,401,403,404,409,413,422,429,503)})


@router.post('/procurement-plans/{plan_id}/assistant/messages',operation_id='AS03',response_model=ChatEnvelope,
             dependencies=[Depends(mutations),Depends(request_boundary)])
def create(plan_id: ResourceId, body: ChatRequest, request: Request, response: Response, key: PlanningKey,
           csrf: CSRF=None, token=Depends(session_token)):
    strict_query(request)
    if any(h in request.headers for h in ('If-Match','If-None-Match')):
        raise ConfigurationError('INVALID_REQUEST',400)
    result=request.app.state.assistant_chat.create(token,plan_id,body,key,csrf)
    response.headers['Cache-Control']='private, no-store'
    return ChatEnvelope(data=result,meta=SummaryMeta(request_id=request.state.request_id))
