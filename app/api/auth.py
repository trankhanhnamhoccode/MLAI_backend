"""Thin public transport for S4.1; authority belongs to application use cases."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request, Response, Security
from fastapi.security import APIKeyCookie

from app.application.contracts.auth import (
    AuthContext, AuthError, CompletedCredential, CredentialCompletion, Envelope,
    ErrorEnvelope, LoginRequest, Meta, StoreContext, StoreList, StoreSummary,
    PublicEmailRequest, RegistrationRequest, PublicEmailAcceptance, PublicEmailErrorEnvelope,
)
from app.application.contracts.store_creation import StoreCreateRequest
from app.api.collaboration import strict_transport

router = APIRouter(prefix="/api/v1", tags=["Auth and Store"])
cookie = APIKeyCookie(name="__Host-shelfcash_session", auto_error=False)
ERRORS = {status: {"model": ErrorEnvelope} for status in (400, 401, 403, 404, 422, 429, 503)}


def service(request: Request):
    return request.app.state.auth


def email_service(request: Request):
    return request.app.state.email_verification


def reset_service(request: Request):
    return request.app.state.password_reset


def raw_session_token(request: Request):
    settings = request.app.state.settings
    return request.cookies.get("shelfcash_dev_session" if settings.auth_dev_cookie else "__Host-shelfcash_session")


def session_token(request: Request, documented=Security(cookie)):
    return raw_session_token(request)


def strict_query(request: Request, allowed=()):
    if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise AuthError("INVALID_FILTER", 422)


async def no_body_query(request: Request):
    strict_query(request)
    if await request.body():
        raise AuthError("VALIDATION_ERROR", 422)


def mutations(request: Request, origin: str | None = Header(default=None, alias="Origin")):
    if origin not in request.app.state.settings.auth_allowed_origins:
        raise AuthError("CSRF_CHECK_FAILED")


def set_cookie(response, request, token, remember):
    dev = request.app.state.settings.auth_dev_cookie
    response.set_cookie("shelfcash_dev_session" if dev else "__Host-shelfcash_session", token,
        max_age=30*24*3600 if remember else None, secure=not dev, httponly=True, samesite="lax", path="/")


def clear_cookie(response, request):
    dev = request.app.state.settings.auth_dev_cookie
    response.delete_cookie("shelfcash_dev_session" if dev else "__Host-shelfcash_session", path="/", secure=not dev, httponly=True, samesite="lax")


@router.post("/auth/register", operation_id="A02", status_code=202,
    response_model=Envelope[PublicEmailAcceptance], responses={status: {"model": PublicEmailErrorEnvelope} for status in (400, 403, 413, 422, 429, 503)}, dependencies=[Depends(mutations)])
def register(body: RegistrationRequest, request: Request, use_cases=Depends(email_service)):
    strict_query(request)
    return dict(data=use_cases.request(body, request.client.host if request.client else "unknown", request_id=request.state.request_id),
                meta=dict(request_id=request.state.request_id), error=None)


@router.post("/auth/email-verifications/request", operation_id="A06", status_code=202,
    response_model=Envelope[PublicEmailAcceptance], responses={status: {"model": PublicEmailErrorEnvelope} for status in (400, 403, 413, 422, 429, 503)}, dependencies=[Depends(mutations)])
def request_verification(body: PublicEmailRequest, request: Request, use_cases=Depends(email_service)):
    strict_query(request)
    return dict(data=use_cases.request(body, request.client.host if request.client else "unknown", request_id=request.state.request_id),
                meta=dict(request_id=request.state.request_id), error=None)


@router.post("/auth/email-verifications/complete", operation_id="A05",
    response_model=Envelope[CompletedCredential], responses={status: {"model": ErrorEnvelope} for status in (400, 403, 413, 422, 429, 503)}, dependencies=[Depends(mutations)])
def complete_verification(body: CredentialCompletion, request: Request, use_cases=Depends(email_service)):
    strict_query(request)
    return dict(data=use_cases.complete(body, request.client.host if request.client else "unknown", request_id=request.state.request_id),
                meta=dict(request_id=request.state.request_id), error=None)


@router.post("/auth/password-reset/request", operation_id="A07", status_code=202,
    response_model=Envelope[PublicEmailAcceptance], responses={status: {"model": PublicEmailErrorEnvelope} for status in (400, 403, 413, 422, 429, 503)}, dependencies=[Depends(mutations)])
def request_password_reset(body: PublicEmailRequest, request: Request, use_cases=Depends(reset_service)):
    strict_query(request)
    return dict(data=use_cases.request(body, request.client.host if request.client else "unknown", request_id=request.state.request_id),
                meta=dict(request_id=request.state.request_id), error=None)


@router.post("/auth/login", operation_id="A01", response_model=Envelope[AuthContext],
    responses={**ERRORS, 200: {"headers": {"Set-Cookie": {"schema": {"type": "string"}}, "Cache-Control": {"schema": {"type": "string"}}}}}, dependencies=[Depends(mutations)])
def login(body: LoginRequest, request: Request, response: Response, auth=Depends(service), previous=Depends(raw_session_token)):
    strict_query(request)
    context, token = auth.login(body, request.client.host if request.client else "unknown", previous)
    set_cookie(response, request, token, body.remember_me)
    return dict(data=context, meta=Meta(request_id=request.state.request_id), error=None)


@router.get("/auth/me", operation_id="A03", response_model=Envelope[AuthContext], responses=ERRORS, dependencies=[Depends(no_body_query)])
def me(request: Request, auth=Depends(service), token=Depends(session_token)):
    return dict(data=auth.me(token), meta=dict(request_id=request.state.request_id), error=None)


@router.post("/auth/logout", operation_id="A04", status_code=204, response_class=Response, responses=ERRORS,
    dependencies=[Depends(mutations), Depends(no_body_query)], openapi_extra={"security": [{}, {"APIKeyCookie": []}]})
def logout(request: Request, response: Response, auth=Depends(service), token=Depends(raw_session_token), csrf: str | None = Header(default=None, alias="X-CSRF-Token", description="Required when a valid session exists.")):
    auth.logout(token, csrf)
    clear_cookie(response, request)
    response.status_code = 204
    return response


@router.post("/auth/credentials/complete", operation_id="N7", response_model=Envelope[CompletedCredential], responses=ERRORS, dependencies=[Depends(mutations)])
def complete(body: CredentialCompletion, request: Request, auth=Depends(service)):
    strict_query(request)
    return dict(data=auth.complete(body, request.client.host if request.client else "unknown", request_id=request.state.request_id), meta=dict(request_id=request.state.request_id), error=None)


@router.get("/stores", operation_id="T01", response_model=Envelope[StoreList], responses=ERRORS)
async def stores(request: Request, limit: int = Query(default=50, ge=1, le=100), cursor: str | None = Query(default=None, min_length=1, max_length=4096), auth=Depends(service), token=Depends(session_token)):
    strict_query(request, ("limit", "cursor"))
    if await request.body():
        raise AuthError("VALIDATION_ERROR", 422)
    # Blocking work must stay off the event loop.
    from starlette.concurrency import run_in_threadpool
    data, pagination = await run_in_threadpool(auth.stores, token, limit, cursor)
    return dict(data=data, meta=Meta(request_id=request.state.request_id, pagination=pagination), error=None)


@router.get("/stores/{store_id}", operation_id="T02", response_model=Envelope[StoreContext], responses=ERRORS, dependencies=[Depends(no_body_query)])
def store_context(store_id: UUID, request: Request, auth=Depends(service), token=Depends(session_token)):
    return dict(data=auth.store_context(token, store_id), meta=dict(request_id=request.state.request_id), error=None)


@router.post('/stores',operation_id='T03',status_code=201,response_model=Envelope[StoreSummary],
    responses={**ERRORS,201:{'headers':{'Location':{'schema':{'type':'string'}}}},409:{'model':ErrorEnvelope},
               413:{'model':ErrorEnvelope},428:{'model':ErrorEnvelope}},dependencies=[Depends(strict_transport),Depends(mutations)])
def create_store(body:StoreCreateRequest,request:Request,response:Response,auth=Depends(service),
    token=Depends(session_token),csrf:str|None=Header(None,alias='X-CSRF-Token',max_length=512),
    key:str|None=Header(None,alias='Idempotency-Key',max_length=128)):
    from app.application.use_cases.store_creation import StoreCreation
    strict_query(request)
    result=StoreCreation(auth).create(token,csrf,key,body,request.state.request_id)
    response.headers['Location']='/api/v1/stores/'+str(result.store_id)
    return dict(data=result,meta=Meta(request_id=request.state.request_id),error=None)
