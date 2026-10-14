"""Three notification operations only; no send/task/delivery endpoint."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from app.api.auth import mutations, session_token, strict_query
from app.application.contracts.auth import AuthError, Envelope, Meta
from app.application.contracts.notifications import (Inbox, InboxMeta, NotificationEnvelope,
    NotificationMeta, ReadRequest, ReadState, UnreadCount, NotificationErrorEnvelope)

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])
ERRORS = {i: {"model": NotificationErrorEnvelope} for i in (400, 401, 403, 404, 409, 412, 413, 422, 428, 503)}


def service(request: Request):
    # Uses the currently wired authority, including controlled test clocks.
    from app.application.use_cases.notifications import Notifications
    return Notifications(request.app.state.auth)


async def read_query(request: Request):
    if await request.body():
        raise AuthError("INVALID_REQUEST", 400)
    raw = request.query_params.get("store_id")
    if raw is not None:
        try:
            if str(UUID(raw)) != raw:
                raise ValueError()
        except ValueError:
            raise AuthError("INVALID_FILTER", 422) from None


@router.get("", operation_id="NF01", response_model=NotificationEnvelope[Inbox, InboxMeta],
    responses=ERRORS, dependencies=[Depends(read_query)])
def inbox(request: Request, token=Depends(session_token), use_cases=Depends(service),
          store_id: UUID | None = None, unread: str | None = None,
          limit: int = Query(50, ge=1, le=100), cursor: str | None = Query(None, max_length=4096)):
    strict_query(request, ("store_id", "unread", "limit", "cursor"))
    if unread not in (None, "true", "false"):
        raise AuthError("INVALID_FILTER", 422)
    data, meta = use_cases.list(token, store_id=store_id, unread=None if unread is None else unread == "true", limit=limit, cursor=cursor)
    return dict(data=data, meta=dict(request_id=request.state.request_id, **meta), error=None)


@router.get("/unread-count", operation_id="NF02", response_model=NotificationEnvelope[UnreadCount, NotificationMeta],
    responses=ERRORS, dependencies=[Depends(read_query)])
def unread_count(request: Request, token=Depends(session_token), use_cases=Depends(service),
                 store_id: UUID | None = None, snapshot_id: str | None = Query(None, min_length=1, max_length=256)):
    strict_query(request, ("store_id", "snapshot_id"))
    data, meta = use_cases.count(token, store_id=store_id, snapshot_id=snapshot_id)
    return dict(data=data, meta=dict(request_id=request.state.request_id, **meta), error=None)


@router.patch("/{notification_id}", operation_id="NF03", response_model=Envelope[ReadState],
    responses={**ERRORS, 200: {"headers": {"ETag": {"schema": {"type": "string"}}}}}, dependencies=[Depends(mutations)])
def mark_read(notification_id: UUID, body: ReadRequest, request: Request, response: Response,
              token=Depends(session_token), use_cases=Depends(service),
              csrf: str | None = Header(None, alias="X-CSRF-Token"),
              match: str | None = Header(None, alias="If-Match"), key: str | None = Header(None, alias="Idempotency-Key")):
    strict_query(request)
    if request.path_params["notification_id"] != str(notification_id):
        raise AuthError("INVALID_RESOURCE_ID", 422)
    if any(len(request.headers.getlist(h)) != 1 for h in ("If-Match", "Idempotency-Key", "X-CSRF-Token") if h in request.headers):
        raise AuthError("INVALID_REQUEST", 400)
    data = use_cases.read(token, csrf, notification_id, body, match, key, request.state.request_id)
    response.headers["ETag"] = '"' + data.version + '"'
    return dict(data=data, meta=Meta(request_id=request.state.request_id), error=None)
