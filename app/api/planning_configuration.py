"""N1–N4 accepted PLAN14 transport; config decisions live in application."""
from typing import Annotated
from fastapi import APIRouter, Body, Depends, Header, Request, Response
from app.api.auth import mutations,session_token,strict_query
from app.api.import_staging import Key,Match,CSRF,read_query
from app.application.contracts.auth import Envelope,Meta
from app.application.contracts.planning_setup import ResourceId
from app.application.contracts import planning_configuration as dto

router=APIRouter(prefix='/api/v1',tags=['Planning configuration'],responses={
    **{status:{'model':dto.ConfigurationErrorEnvelope} for status in (400,401,403,404,409,412,413,428,503)},
    422:{'model':dto.ConfigurationErrorEnvelope}})
NoneMatch=Annotated[str | None,Header(alias='If-None-Match',max_length=256)]
ETAG={'ETag':{'schema':{'type':'string'}}}
CREATED_HEADERS={**ETAG,'Location':{'schema':{'type':'string'}}}


def service(request:Request):
    return request.app.state.planning_configuration


async def bounded(request:Request):
    from app.application.contracts.planning_configuration import ConfigurationError
    if len(await request.body())>65536:
        raise ConfigurationError('REQUEST_TOO_LARGE',413)


def wrap(request,response,result,status):
    response.status_code=status
    version=result.budget_ceiling.version if isinstance(result,dto.BudgetResult) else result.version
    response.headers['ETag']='"'+version+'"'
    if status==201:
        response.headers['Location']=f'/api/v1/stores/{result.store_id}/planning-context' if isinstance(result,dto.BudgetResult) else f'/api/v1/stores/{result.store_id}/planning-requirements/{result.saved_requirement_id}'
    return dict(data=result,meta=Meta(request_id=request.state.request_id),error=None)


@router.post('/stores/{store_id}/planning-requirements',operation_id='N1',status_code=201,
    response_model=Envelope[dto.SavedDetail],responses={201:{'headers':CREATED_HEADERS}},dependencies=[Depends(mutations),Depends(bounded)])
def save(store_id:ResourceId,body:dto.SaveRequest,request:Request,response:Response,
    key:Key=None,csrf:CSRF=None,svc=Depends(service),token=Depends(session_token)):
    strict_query(request)
    result,status,_=svc.write(token,store_id,body,key,csrf,match=request.headers.get('If-Match'),
        none=request.headers.get('If-None-Match'),request_id=request.state.request_id)
    return wrap(request,response,result,status)


@router.get('/stores/{store_id}/planning-requirements/{saved_requirement_id}',operation_id='N2',response_model=Envelope[dto.SavedDetail],responses={200:{'headers':ETAG}})
async def read(store_id:ResourceId,saved_requirement_id:ResourceId,request:Request,response:Response,svc=Depends(service),token=Depends(session_token)):
    await read_query(request)
    from starlette.concurrency import run_in_threadpool
    result=await run_in_threadpool(svc.read,token,store_id,saved_requirement_id)
    return wrap(request,response,result,200)


@router.put('/stores/{store_id}/planning-requirements/{saved_requirement_id}',operation_id='N3',
    response_model=Envelope[dto.SavedDetail],responses={200:{'headers':ETAG}},dependencies=[Depends(mutations),Depends(bounded)])
def replace(store_id:ResourceId,saved_requirement_id:ResourceId,
    body:Annotated[dto.ReplaceRequest | dto.ArchiveRequest,Body(discriminator='state')],request:Request,response:Response,
    key:Key=None,match:Match=None,csrf:CSRF=None,svc=Depends(service),token=Depends(session_token)):
    strict_query(request)
    result,status,_=svc.write(token,store_id,body,key,csrf,ident=saved_requirement_id,match=match,
        none=request.headers.get('If-None-Match'),request_id=request.state.request_id)
    return wrap(request,response,result,status)


@router.put('/stores/{store_id}/planning-budget',operation_id='N4',response_model=Envelope[dto.BudgetResult],
    responses={200:{'headers':ETAG},201:{'model':Envelope[dto.BudgetResult],'headers':CREATED_HEADERS}},dependencies=[Depends(mutations),Depends(bounded)])
def budget(store_id:ResourceId,body:dto.BudgetRequest,request:Request,response:Response,
    key:Key=None,match:Match=None,none:NoneMatch=None,csrf:CSRF=None,svc=Depends(service),token=Depends(session_token)):
    strict_query(request)
    result,status,_=svc.write(token,store_id,body,key,csrf,match=match,none=none,request_id=request.state.request_id)
    return wrap(request,response,result,status)
