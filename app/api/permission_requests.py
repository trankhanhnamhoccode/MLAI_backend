"""PR01--PR04 transport; membership and decision policy lives in application."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response
from app.api.auth import mutations, session_token, strict_query
from app.application.contracts.auth import Envelope, Meta, AuthError
from app.application.contracts import permission_requests as dto
from app.application.contracts.collaboration import PageEnvelope, PageMeta, WorkflowErrorEnvelope
from app.api.collaboration import strict_transport, ETAG_RESPONSE

router = APIRouter(prefix="/api/v1/stores/{store_id}/permission-requests", tags=["Permission requests"], dependencies=[Depends(strict_transport)])
ERRORS = {s: {"model": WorkflowErrorEnvelope} for s in (400,401,403,404,409,412,413,422,428,503)}


def service(request: Request):
    from app.application.use_cases.permission_requests import PermissionRequests
    return PermissionRequests(request.app.state.staff)


def envelope(request, data):
    return dict(data=data, meta=Meta(request_id=request.state.request_id), error=None)


def etag(response, version):
    response.headers["ETag"] = '"' + version + '"'


@router.post("", operation_id="PR01", status_code=201, response_model=Envelope[dto.PermissionRequest], responses={**ERRORS,201:ETAG_RESPONSE}, dependencies=[Depends(mutations)])
def submit(store_id: UUID, body: dto.SubmitRequest, request: Request, response: Response,
           token=Depends(session_token), use_cases=Depends(service),
           key: str | None=Header(None, alias="Idempotency-Key"), csrf: str | None=Header(None, alias="X-CSRF-Token")):
    strict_query(request)
    data=use_cases.submit(token, store_id, body, key, csrf, request.state.request_id)
    etag(response, data.version)
    return envelope(request, data)


@router.get("", operation_id="PR02", response_model=PageEnvelope[dto.RequestList], responses=ERRORS)
async def listing(store_id: UUID, request: Request, state: dto.State | None=None,
                  limit: int=Query(50, ge=1, le=100), cursor: str | None=Query(None, min_length=1, max_length=4096),
                  token=Depends(session_token), use_cases=Depends(service)):
    from starlette.concurrency import run_in_threadpool
    strict_query(request, ("state", "limit", "cursor"))
    if await request.body(): raise AuthError("INVALID_REQUEST", 400)
    data, meta=await run_in_threadpool(use_cases.list, token, store_id, state, limit, cursor)
    return dict(data=data, meta=PageMeta(request_id=request.state.request_id, **meta), error=None)


@router.get("/{request_id}", operation_id="PR03", response_model=Envelope[dto.PermissionRequest], responses={**ERRORS,200:ETAG_RESPONSE})
async def detail(store_id: UUID, request_id: UUID, request: Request, response: Response,
           token=Depends(session_token), use_cases=Depends(service)):
    from starlette.concurrency import run_in_threadpool
    strict_query(request)
    if await request.body(): raise AuthError("INVALID_REQUEST", 400)
    data=await run_in_threadpool(use_cases.detail, token, store_id, request_id)
    etag(response, data.version)
    return envelope(request, data)


@router.post("/{request_id}/actions", operation_id="PR04", response_model=Envelope[dto.ActionResult], responses={**ERRORS,200:ETAG_RESPONSE}, dependencies=[Depends(mutations)])
def action(store_id: UUID, request_id: UUID, body: Annotated[dto.ApproveRequest | dto.RejectRequest | dto.CancelRequest, Body(discriminator="action")],
           request: Request, response: Response, token=Depends(session_token), use_cases=Depends(service),
           key: str | None=Header(None, alias="Idempotency-Key"), match: str | None=Header(None, alias="If-Match"),
           csrf: str | None=Header(None, alias="X-CSRF-Token")):
    strict_query(request)
    data=use_cases.action(token, store_id, request_id, body, key, match, csrf, request.state.request_id)
    etag(response, data.request.version)
    return envelope(request, data)
