"""Accepted R01/C01 reads, no public forecast or PlanningRun mutation."""
from typing import Annotated
from fastapi import APIRouter,Depends,Query,Request
from app.api.auth import session_token
from app.api.import_staging import read_query
from app.application.contracts.auth import Envelope,Meta
from app.application.contracts.planning_setup import ResourceId,BusinessDate
from app.application.contracts.readiness import Readiness
from app.application.contracts.planning_context import Context
from app.application.contracts.public_reads import ReadErrorEnvelope

router=APIRouter(prefix='/api/v1',tags=['Readiness and planning context'],responses={
    status:{'model':ReadErrorEnvelope} for status in (400,401,403,404,409,422,503)})


def service(request:Request):
    return request.app.state.readiness


@router.get('/stores/{store_id}/readiness',operation_id='R01',response_model=Envelope[Readiness])
async def readiness(store_id:ResourceId,request:Request,actions:Annotated[str,Query(max_length=128)]='import,menu,inventory',
    forecast_start_date:Annotated[BusinessDate | None,Query()]=None,
    planning_request:Annotated[str | None,Query(max_length=65536)]=None,svc=Depends(service),token=Depends(session_token)):
    await read_query(request,('actions','forecast_start_date','planning_request'))
    from starlette.concurrency import run_in_threadpool
    result=await run_in_threadpool(svc.read,token,store_id,tuple(actions.split(',')),forecast_start_date,planning_request=planning_request)
    return dict(data=result,meta=Meta(request_id=request.state.request_id),error=None)


@router.get('/stores/{store_id}/planning-context',operation_id='C01',response_model=Envelope[Context])
async def context(store_id:ResourceId,request:Request,planning_request:Annotated[str | None,Query(max_length=65536)]=None,svc=Depends(service),token=Depends(session_token)):
    await read_query(request,('planning_request',))
    from starlette.concurrency import run_in_threadpool
    result=await run_in_threadpool(svc.read,token,store_id,context=True,planning_request=planning_request)
    return dict(data=result,meta=Meta(request_id=request.state.request_id),error=None)
