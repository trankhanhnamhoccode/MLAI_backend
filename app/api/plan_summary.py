"""Explicit summary creation and pure retained reads; C08 is unchanged."""
from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool
from app.api.auth import session_token, mutations, strict_query
from app.api.import_staging import CSRF, read_query
from app.api.planning_public import PlanningKey, request_boundary
from app.application.contracts.planning_setup import ResourceId
from app.application.contracts.planning_configuration import ConfigurationError, ConfigurationErrorEnvelope
from app.application.contracts.plan_summary import SummaryRequest, SummaryEnvelope, SummaryMeta

router = APIRouter(prefix='/api/v1',tags=['Decision Assistant summary'],responses={
    code:{'model':ConfigurationErrorEnvelope} for code in (400,401,403,404,409,413,422,429,503)})


@router.post('/procurement-plans/{plan_id}/assistant/summary',operation_id='AS01',
    response_model=SummaryEnvelope,dependencies=[Depends(mutations),Depends(request_boundary)],
    responses={200:{'headers':{name:{'schema':{'type':'string'}} for name in ('Location','Cache-Control')}}})
def create(plan_id: ResourceId, body: SummaryRequest, request: Request, response: Response, key: PlanningKey,
           csrf: CSRF=None, token=Depends(session_token)):
    strict_query(request)
    if any(h in request.headers for h in ('If-Match','If-None-Match')): raise ConfigurationError('INVALID_REQUEST',400)
    result = request.app.state.plan_summaries.create(token,plan_id,body,key,csrf)
    response.headers['Cache-Control']='private, no-store'
    response.headers['Location']=f'/api/v1/procurement-plans/{plan_id}/assistant/summary/{result.generation_id}'
    return SummaryEnvelope(data=result,meta=SummaryMeta(request_id=request.state.request_id))


@router.get('/procurement-plans/{plan_id}/assistant/summary/{generation_id}',operation_id='AS02',response_model=SummaryEnvelope,
    responses={200:{'headers':{'Cache-Control':{'schema':{'type':'string'}}}}})
async def read(plan_id: ResourceId, generation_id: ResourceId, request: Request, response: Response, token=Depends(session_token)):
    await read_query(request)
    result = await run_in_threadpool(request.app.state.plan_summaries.read,token,plan_id,generation_id)
    response.headers['Cache-Control']='private, no-store'
    return SummaryEnvelope(data=result,meta=SummaryMeta(request_id=request.state.request_id))
