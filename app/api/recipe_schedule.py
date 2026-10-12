"""N20–N22 transport; calendar policy and writes belong to application layer."""
from datetime import date
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Body, Depends, Query, Request, Response
from app.api.auth import mutations, session_token
from app.api.import_staging import Key, Match, CSRF, bounded_json, read_query, ETAG
from app.application.contracts.auth import Envelope, Meta, ErrorEnvelope
from app.application.contracts import recipe_schedule as dto

router = APIRouter(prefix="/api/v1",tags=["Recipe schedule"])
ERRORS = {status:{"model":ErrorEnvelope} for status in (400,401,403,404,409,412,413,422,428,503)}
ChangeBody = Annotated[dto.PreviewRequest | dto.CommitRequest, Body(discriminator="phase")]


def service(request: Request):
    return request.app.state.recipe_schedule


@router.get("/stores/{store_id}/products/{product_id}/recipe-schedule",operation_id="N20",
    response_model=Envelope[dto.Timeline],responses={**ERRORS,200:{"headers":ETAG}})
async def timeline(store_id: UUID, product_id: UUID, request: Request, response: Response,
    status: Annotated[str,Query(max_length=128)]="in_effect,scheduled",limit:Annotated[int,Query(ge=1,le=100)]=50,
    cursor:Annotated[str | None,Query(max_length=4096)]=None,sort:Annotated[str,Query(max_length=64)]="effective_from,version",
    from_date:Annotated[str | None,Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]=None,
    to_date:Annotated[str | None,Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]=None,
    svc=Depends(service),token=Depends(session_token)):
    await read_query(request,("status","limit","cursor","sort","from_date","to_date"))
    from app.application.contracts.auth import AuthError
    try:
        start,end = date.fromisoformat(from_date) if from_date else None,date.fromisoformat(to_date) if to_date else None
    except ValueError:
        raise AuthError("INVALID_FILTER",422) from None
    from starlette.concurrency import run_in_threadpool
    result,page = await run_in_threadpool(svc.timeline,token,store_id,product_id,status=status,limit=limit,
        cursor=cursor,sort=sort,from_date=start,to_date=end)
    response.headers["ETag"]='"'+result.schedule_version+'"'
    return dict(data=result,meta=Meta(request_id=request.state.request_id,pagination=page),error=None)


@router.post("/stores/{store_id}/products/{product_id}/recipe-schedule/changes",operation_id="N21",
    response_model=Envelope[dto.Preview | dto.Receipt],responses={**ERRORS,200:{"headers":ETAG}},
    dependencies=[Depends(mutations),Depends(bounded_json)])
def change(store_id: UUID, product_id: UUID, body: ChangeBody, request: Request, response: Response,
    key:Key=None,match:Match=None,csrf:CSRF=None,svc=Depends(service),token=Depends(session_token)):
    from app.api.auth import strict_query
    strict_query(request)
    result = svc.change(token,store_id,product_id,body,key,match,csrf,request.state.request_id)
    response.headers["ETag"]='"'+(result.schedule_version if isinstance(result,dto.Preview) else result.schedule_version_after)+'"'
    return dict(data=result,meta=Meta(request_id=request.state.request_id),error=None)


@router.get("/stores/{store_id}/products/{product_id}/recipe-schedule/changes/{change_id}",operation_id="N22",
    response_model=Envelope[dto.ChangeRead],responses=ERRORS)
async def read_change(store_id: UUID, product_id: UUID, change_id: UUID, request: Request,
    svc=Depends(service),token=Depends(session_token)):
    await read_query(request)
    from starlette.concurrency import run_in_threadpool
    result = await run_in_threadpool(svc.read_change,token,store_id,product_id,change_id)
    return dict(data=result,meta=Meta(request_id=request.state.request_id),error=None)
