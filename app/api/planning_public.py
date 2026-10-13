"""Exact C02/C03 transport; durable Run UUID is the only polling identity."""
from fastapi import APIRouter,Depends,Request,Response,Header,Query
from typing import Annotated
from uuid import UUID
from app.api.auth import session_token,mutations,strict_query
from app.api.import_staging import CSRF,read_query
from app.application.contracts.planning_setup import PlanningRequest,ResourceId
from app.application.contracts.planning_configuration import ConfigurationError,ConfigurationErrorEnvelope,FieldError
from app.application.contracts import planning_public as dto
from app.application.contracts import planning_inspection as inspection
from typing import Literal

router=APIRouter(prefix='/api/v1',tags=['Planning runs'],responses={
    status:{'model':ConfigurationErrorEnvelope} for status in (400,401,403,404,409,422,503)})
RECEIPT_HEADERS={k:{'schema':{'type':'string'}} for k in ('Location','Retry-After','Cache-Control')}
PlanningKey=Annotated[str,Header(alias='Idempotency-Key',min_length=36,max_length=36,
    pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')]


def service(request:Request):return request.app.state.planning_public


async def request_boundary(request:Request):
    key=request.headers.get('Idempotency-Key')
    try:
        if len(request.headers.getlist('Idempotency-Key'))!=1 or key is None or str(UUID(key))!=key:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ConfigurationError('INVALID_REQUEST',400) from None
    if len(await request.body())>65536:
        raise ConfigurationError('INVALID_PLANNING_CONFIGURATION',422,(FieldError(code='RESOURCE_LIMIT_EXCEEDED',field='request',message='Yêu cầu vượt giới hạn 64 KiB.'),))
    import json
    from app.application.use_cases.planning_setup import _json_object
    def invalid_constant(value):raise ValueError('Non-JSON numeric constant')
    try:json.loads(await request.body(),object_pairs_hook=_json_object,parse_constant=invalid_constant)
    except (ValueError,UnicodeDecodeError):raise ConfigurationError('INVALID_REQUEST',400) from None


@router.post('/stores/{store_id}/procurement-plans',operation_id='C02',status_code=202,
    response_model=dto.PlanningEnvelope[dto.Accepted],responses={202:{'headers':RECEIPT_HEADERS},
        200:{'model':dto.PlanningEnvelope[dto.Accepted],'headers':RECEIPT_HEADERS}},dependencies=[Depends(mutations),Depends(request_boundary)])
def accept(store_id:ResourceId,body:PlanningRequest,request:Request,response:Response,key:PlanningKey,csrf:CSRF=None,
    svc=Depends(service),token=Depends(session_token)):
    strict_query(request)
    if any(h in request.headers for h in ('If-Match','If-None-Match')):raise ConfigurationError('INVALID_REQUEST',400)
    record=svc.accept(token,store_id,body,key,csrf)
    active=record.status in ('queued','running')
    response.status_code=202 if active else 200
    response.headers['Location']=f'/api/v1/procurement-plans/{record.run_id}'
    if active:response.headers['Retry-After']='2'
    return dto.PlanningEnvelope[dto.Accepted](data=dto.Accepted(run_id=record.run_id,status=record.status,accepted_at=record.accepted_at),
        meta=dto.PollMeta(warnings=record.public_acceptance.receipt_warnings,poll_after_ms=2000 if active else 0),error=None)


@router.get('/procurement-plans/{plan_id}',operation_id='C03',response_model=dto.PlanningEnvelope[dto.RunView],
    responses={200:{'headers':{'ETag':{'schema':{'type':'string'}},'Cache-Control':{'schema':{'type':'string'}}}}})
async def read(plan_id:ResourceId,request:Request,response:Response,svc=Depends(service),token=Depends(session_token)):
    await read_query(request)
    from starlette.concurrency import run_in_threadpool
    result,warnings=await run_in_threadpool(svc.read,token,plan_id)
    response.headers['ETag']='"'+result.response_version+'"'
    return dto.PlanningEnvelope[dto.RunView](data=result,meta=dto.PollMeta(warnings=warnings,
        poll_after_ms=2000 if result.status in ('queued','running') else 0),error=None)


@router.get('/procurement-plans/{plan_id}/ingredients',operation_id='C04',
    response_model=inspection.InspectionEnvelope[inspection.IngredientNavigator],responses={413:{'model':ConfigurationErrorEnvelope}})
async def ingredients(plan_id:ResourceId,request:Request,
    option_id:Annotated[str | None,Query(min_length=1,max_length=128)]=None,
    limit:Annotated[int,Query(ge=1,le=100)]=50,
    cursor:Annotated[str | None,Query(min_length=1,max_length=4096)]=None,
    sort:Literal['ingredient_id']='ingredient_id',
    ingredient_id:Annotated[list[ResourceId] | None,Query()]=None,svc=Depends(service),token=Depends(session_token)):
    allowed={'option_id','limit','cursor','sort','ingredient_id'}
    if any(k not in allowed or (k!='ingredient_id' and len(request.query_params.getlist(k))!=1) for k in request.query_params):
        raise ConfigurationError('INVALID_FILTER',422)
    if await request.body():raise ConfigurationError('INVALID_REQUEST',422)
    if len(ingredient_id or ())>100:raise ConfigurationError('RESOURCE_LIMIT_EXCEEDED',413)
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(svc.ingredients,token,plan_id,request.state.request_id,option_id,limit,cursor,tuple(ingredient_id or ()))


@router.get('/procurement-plans/{plan_id}/ingredients/{ingredient_id}',operation_id='C05',
    response_model=inspection.InspectionEnvelope[inspection.IngredientDetail],responses={413:{'model':ConfigurationErrorEnvelope}})
async def ingredient(plan_id:ResourceId,ingredient_id:ResourceId,request:Request,
    option_id:Annotated[str | None,Query(min_length=1,max_length=128)]=None,svc=Depends(service),token=Depends(session_token)):
    await read_query(request,{'option_id'})
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(svc.ingredient,token,plan_id,ingredient_id,request.state.request_id,option_id)


@router.get('/procurement-plans/{plan_id}/explanation',operation_id='C08',
    response_model=inspection.ExplanationEnvelope)
async def explanation(plan_id:ResourceId,request:Request,
    option_id:Annotated[str | None,Query(min_length=1,max_length=128)]=None,svc=Depends(service),token=Depends(session_token)):
    await read_query(request,{'option_id'})
    from starlette.concurrency import run_in_threadpool
    result=await run_in_threadpool(svc.explanation,token,plan_id,option_id)
    return inspection.ExplanationEnvelope(data=result,meta=inspection.ExplanationMeta(request_id=request.state.request_id),error=None)
