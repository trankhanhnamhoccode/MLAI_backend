"""N9/H01/H02 syntax only; scoped history authority lives in use cases."""
from datetime import date
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,Request,Query
from starlette.concurrency import run_in_threadpool
from app.api.auth import session_token
from app.api.import_staging import read_query
from app.application.contracts.planning_setup import ResourceId
from app.application.contracts import history as dto
from app.application.contracts.auth import ErrorEnvelope
from app.application.contracts.planning_configuration import ConfigurationErrorEnvelope

router=APIRouter(prefix='/api/v1',tags=['Retained history'],responses={
    code:{'model':ErrorEnvelope} for code in (401,403,404,409,413,422,503)})
Limit=Annotated[int,Query(ge=1,le=100)]
Cursor=Annotated[str | None,Query(min_length=1,max_length=4096)]
Search=Annotated[str | None,Query(min_length=1,max_length=255)]


@router.get('/stores/{store_id}/imports/calendar',operation_id='H01',
    response_model=dto.HistoryEnvelope[dto.ImportCalendar,dto.HistoryMeta])
async def calendar(store_id:ResourceId,month:Annotated[str,Query(min_length=7,max_length=7)],request:Request,
    category:dto.Category | None=None,status:dto.ImportStatus | None=None,q:Search=None,token=Depends(session_token)):
    await read_query(request,{'month','category','status','q'})
    return await run_in_threadpool(request.app.state.import_history.calendar,token,store_id,month,category,status,q,request.state.request_id)


@router.get('/stores/{store_id}/imports',operation_id='H02',
    response_model=dto.HistoryEnvelope[dto.ImportHistory,dto.ImportHistoryMeta])
async def imports(store_id:ResourceId,import_date:date,request:Request,category:dto.Category | None=None,
    status:dto.ImportStatus | None=None,q:Search=None,limit:Limit=50,cursor:Cursor=None,
    sort:Literal['-imported_at']='-imported_at',token=Depends(session_token)):
    await read_query(request,{'import_date','category','status','q','limit','cursor','sort'})
    return await run_in_threadpool(request.app.state.import_history.history,token,store_id,import_date,category,status,q,limit,cursor,request.state.request_id)


@router.get('/stores/{store_id}/procurement-plans',operation_id='N9',response_model=dto.RunHistoryEnvelope,
    responses={code:{'model':ConfigurationErrorEnvelope} for code in (401,403,404,409,413,422,503)})
async def runs(store_id:ResourceId,request:Request,limit:Limit=50,cursor:Cursor=None,
    status:Annotated[str | None,Query(min_length=1,max_length=64)]=None,
    forecast_start_from:date | None=None,forecast_start_to:date | None=None,
    sort:Literal['-accepted_at']='-accepted_at',token=Depends(session_token)):
    await read_query(request,{'limit','cursor','status','forecast_start_from','forecast_start_to','sort'})
    return await run_in_threadpool(request.app.state.planning_public.history,token,store_id,request.state.request_id,
        limit,cursor,status,forecast_start_from,forecast_start_to)
