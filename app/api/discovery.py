"""D01/SU01 query syntax; application code owns permissions and facts."""
from fastapi import APIRouter, Depends, Request, Query
from starlette.concurrency import run_in_threadpool
from typing import Annotated, Literal
from app.api.auth import session_token
from app.api.import_staging import read_query
from app.application.contracts.planning_setup import ResourceId
from app.application.contracts import discovery as dto
from app.application.contracts.auth import ErrorEnvelope
from app.application.use_cases.discovery import DiscoveryReads

router=APIRouter(prefix='/api/v1',tags=['Operational discovery'],responses={
    code:{'model':ErrorEnvelope} for code in (401,403,404,409,422,503)})


@router.get('/stores/{store_id}/today',operation_id='D01',response_model=dto.TodayEnvelope,response_model_exclude_unset=True)
async def today(store_id:ResourceId,request:Request,section:str|None=None,
    limit:Annotated[int,Query(ge=1,le=20)]=5,
    snapshot_id:Annotated[str|None,Query(min_length=1,max_length=128)]=None,token=Depends(session_token)):
    from app.application.use_cases.today import TodayReads
    await read_query(request,{'section','limit','snapshot_id'})
    state=request.app.state
    service=TodayReads(state.auth,state.planning_public,state.readiness,state.public_reads)
    return await run_in_threadpool(service.read,token,store_id,request.state.request_id,section,limit,snapshot_id)


@router.get('/stores/{store_id}/suppliers',operation_id='SU01',response_model=dto.SupplierPickerEnvelope)
async def suppliers(store_id:ResourceId,request:Request,q:Annotated[str|None,Query(min_length=1,max_length=200)]=None,
    active:bool|None=None,sort:Literal['name','-name']='name',limit:Annotated[int,Query(ge=1,le=100)]=50,
    cursor:Annotated[str|None,Query(min_length=1,max_length=4096)]=None,
    snapshot_id:Annotated[str|None,Query(min_length=1,max_length=128)]=None,token=Depends(session_token)):
    await read_query(request,{'q','active','sort','limit','cursor','snapshot_id'})
    return await run_in_threadpool(DiscoveryReads(request.app.state.auth).suppliers,
        token,store_id,request.state.request_id,q,active,sort,limit,cursor,snapshot_id)
