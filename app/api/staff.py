"""N12--N19 transport; current authority and transitions live in application."""
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from app.api.auth import mutations, no_body_query, session_token, strict_query
from app.application.contracts.auth import Envelope, ErrorEnvelope, AuthError, Meta, canonical_email
from app.application.contracts import staff as dto

router = APIRouter(prefix="/api/v1", tags=["Staff permissions and invitations"])
ERRORS = {s: {"model": ErrorEnvelope} for s in (401,403,404,409,410,412,422,428,429,503)}
Key = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]
Match = Annotated[str | None, Header(alias="If-Match", max_length=256)]
CSRF = Annotated[str | None, Header(alias="X-CSRF-Token", max_length=512)]
ETAG = {"ETag": {"schema": {"type": "string"}}}


def service(request: Request):
    return request.app.state.staff


def envelope(request, data, pagination=None):
    return dict(data=data, meta=Meta(request_id=request.state.request_id, pagination=pagination), error=None)


async def read_query(request, allowed):
    strict_query(request, allowed)
    if await request.body():
        raise AuthError("VALIDATION_ERROR", 422)


@router.get("/stores/{store_id}/memberships", operation_id="N12", response_model=Envelope[dto.MembershipList], responses=ERRORS)
async def memberships(store_id: UUID, request: Request, role: Literal["STAFF"]="STAFF", active: Literal["all","true","false"]="all",
    limit: int=Query(50,ge=1,le=100), cursor: str | None=Query(None,min_length=1,max_length=4096),
    staff=Depends(service), token=Depends(session_token)):
    await read_query(request, ("role","active","limit","cursor"))
    data, page = await run_in_threadpool(staff.memberships, token, store_id, active, limit, cursor)
    return envelope(request, data, page)


@router.put("/stores/{store_id}/memberships/{membership_id}/permissions", operation_id="N13",
    response_model=Envelope[dto.PermissionUpdate], responses={**ERRORS,200:{"headers":ETAG}}, dependencies=[Depends(mutations)])
def replace(store_id: UUID, membership_id: UUID, body: dto.GrantsRequest, request: Request, response: Response,
    key: Key=None, match: Match=None, csrf: CSRF=None, staff=Depends(service), token=Depends(session_token)):
    strict_query(request)
    data = staff.replace(token, store_id, membership_id, body, key, match, csrf, request.state.request_id)
    response.headers["ETag"] = '"'+data.membership.version+'"'
    return envelope(request, data)


@router.get("/stores/{store_id}/permission-events", operation_id="N14", response_model=Envelope[dto.PermissionEvents], responses=ERRORS)
async def events(store_id: UUID, request: Request, membership_id: UUID | None=None,
    limit: int=Query(50,ge=1,le=100), cursor: str | None=Query(None,min_length=1,max_length=4096),
    staff=Depends(service), token=Depends(session_token)):
    await read_query(request, ("membership_id","limit","cursor"))
    data, page = await run_in_threadpool(staff.events, token, store_id, membership_id, limit, cursor)
    return envelope(request, data, page)


@router.post("/stores/{store_id}/staff-invitations", operation_id="N15", status_code=201,
    response_model=Envelope[dto.InvitationCreation], responses=ERRORS, dependencies=[Depends(mutations)])
def create(store_id: UUID, body: dto.CreateInvitation, request: Request,
    key: Key=None, csrf: CSRF=None, staff=Depends(service), token=Depends(session_token)):
    strict_query(request)
    return envelope(request, staff.create(token, store_id, body, key, csrf, request.state.request_id))


@router.get("/stores/{store_id}/staff-invitations", operation_id="N16",
    response_model=Envelope[dto.InvitationList] | Envelope[dto.InvitationEvents], responses=ERRORS)
async def invitations(store_id: UUID, request: Request, view: Literal["invitations","events"]="invitations",
    status: str | None=None, email: str | None=Query(None,max_length=320), invitation_id: UUID | None=None,
    sort: Literal["-issued_at"]="-issued_at", limit: int=Query(50,ge=1,le=100),
    cursor: str | None=Query(None,min_length=1,max_length=4096), staff=Depends(service), token=Depends(session_token)):
    await read_query(request, ("view","status","email","invitation_id","sort","limit","cursor"))
    if view == "events":
        if invitation_id is None or any(k in request.query_params for k in ("status","email","sort")):
            raise AuthError("INVALID_FILTER", 422)
    elif invitation_id is not None:
        raise AuthError("INVALID_FILTER", 422)
    statuses = tuple(status.split(",")) if status is not None else ()
    if statuses and (len(set(statuses)) != len(statuses) or not set(statuses) <= {"pending","accepted","revoked","expired"}):
        raise AuthError("INVALID_FILTER", 422)
    if email is not None:
        try:
            email = canonical_email(email)
        except ValueError:
            raise AuthError("INVALID_FILTER", 422) from None
    data, page = await run_in_threadpool(staff.invitations, token, store_id, view=view, statuses=statuses,
        email=email, invitation_id=invitation_id, limit=limit, cursor=cursor)
    return envelope(request, data, page)


@router.post("/stores/{store_id}/staff-invitations/{invitation_id}/actions", operation_id="N17",
    response_model=Envelope[dto.InvitationAction], responses={**ERRORS,200:{"headers":ETAG}}, dependencies=[Depends(mutations)])
def action(store_id: UUID, invitation_id: UUID, body: Annotated[dto.ReissueInvitation | dto.RevokeInvitation, Body(discriminator="action")],
    request: Request, response: Response, key: Key=None, match: Match=None, csrf: CSRF=None,
    staff=Depends(service), token=Depends(session_token)):
    strict_query(request)
    data = staff.action(token, store_id, invitation_id, body, key, match, csrf, request.state.request_id)
    response.headers["ETag"] = '"'+data.invitation.version+'"'
    return envelope(request, data)


@router.get("/staff-invitations/{invitation_id}", operation_id="N18", response_model=Envelope[dto.OfferRead],
    responses={**ERRORS,200:{"headers":ETAG}}, dependencies=[Depends(no_body_query)])
def offer(invitation_id: UUID, request: Request, response: Response,
    invitation_token: str | None=Header(None,alias="X-Invitation-Token",max_length=512), staff=Depends(service), token=Depends(session_token)):
    data = staff.offer(token, invitation_id, invitation_token, request.client.host if request.client else "unknown")
    response.headers["ETag"] = '"'+data.invitation.version+'"'
    return envelope(request, data)


@router.post("/staff-invitations/{invitation_id}/accept", operation_id="N19", status_code=201,
    response_model=Envelope[dto.AcceptanceReceipt], responses={**ERRORS,200:{"model":Envelope[dto.AcceptanceReceipt]}},
    dependencies=[Depends(mutations)])
def accept(invitation_id: UUID, body: dto.AcceptInvitation, request: Request, response: Response,
    key: Key=None, match: Match=None, csrf: CSRF=None, staff=Depends(service), token=Depends(session_token)):
    strict_query(request)
    data, replay = staff.accept(token, invitation_id, body, key, match, csrf,
        request.client.host if request.client else "unknown", request.state.request_id)
    response.status_code = 200 if replay else 201
    return envelope(request, data)
