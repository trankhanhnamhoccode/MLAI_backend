"""Import transport only. Durable acceptance does not run computation in requests."""

from typing import Annotated, Literal
from uuid import UUID
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
)
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from app.api.auth import mutations, session_token, strict_query, no_body_query
from app.application.contracts.auth import AuthError, ErrorEnvelope
from app.application.contracts import import_mapping as dto

router = APIRouter(prefix="/api/v1", tags=["Import staging and mapping"])
ERRORS = {
    s: {"model": ErrorEnvelope}
    for s in (400, 401, 403, 404, 409, 412, 413, 415, 422, 428, 503)
}
Key = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]
Match = Annotated[str | None, Header(alias="If-Match", max_length=256)]
CSRF = Annotated[str | None, Header(alias="X-CSRF-Token", max_length=512)]
ETAG = {"ETag": {"schema": {"type": "string"}}}


def service(request: Request):
    return request.app.state.import_staging


def wrap(request, data, *, page=None, poll=None):
    return dict(
        data=data,
        meta=dto.ImportMeta(
            request_id=request.state.request_id,
            pagination=page,
            poll_after_ms=poll,
            warnings=getattr(data, "warnings", ()),
        ),
        error=None,
    )


async def read_query(request, allowed=()):
    strict_query(request, allowed)
    if await request.body():
        raise AuthError("VALIDATION_ERROR", 422)


async def bounded_json(request: Request):
    # Bound before Pydantic parsing; multipart has its own byte/file bounds.
    if request.headers.get("content-length"):
        value = request.headers["content-length"]
        if not value.isascii() or not value.isdecimal():
            raise AuthError("INVALID_REQUEST", 400)
        if int(value) > 65536:
            raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
    if len(await request.body()) > 65536:
        raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)


@router.post(
    "/stores/{store_id}/imports",
    operation_id="I01",
    status_code=201,
    response_model=dto.ImportEnvelope[dto.Draft],
    responses={**ERRORS, 201: {"headers": ETAG}},
    dependencies=[Depends(mutations), Depends(bounded_json)],
)
def draft(
    store_id: UUID,
    body: dto.DraftRequest,
    request: Request,
    response: Response,
    key: Key = None,
    csrf: CSRF = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    strict_query(request)
    data = svc.create(token, store_id, body, key, csrf)
    response.headers["ETag"] = '"' + data.import_revision + '"'
    return wrap(request, data)


@router.post(
    "/imports/{import_id}/files",
    operation_id="I02",
    response_model=dto.ImportEnvelope[dto.UploadResult],
    responses={**ERRORS, 200: {"headers": ETAG}, 422: {"model": dto.UploadFailure}},
    dependencies=[Depends(mutations)],
)
async def upload(
    import_id: UUID,
    request: Request,
    response: Response,
    files: Annotated[list[UploadFile], File(alias="files[]")],
    client_file_ids: Annotated[list[UUID], Form(alias="client_file_ids[]")],
    key: Key = None,
    csrf: CSRF = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    strict_query(request)
    if not 1 <= len(files) <= 20:
        raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
    if len(files) != len(client_file_ids):
        raise AuthError("INVALID_IMPORT_CONFIGURATION", 422)
    form = await request.form()
    if set(form.keys()) != {"files[]", "client_file_ids[]"}:
        raise AuthError("VALIDATION_ERROR", 422)
    entries = []
    for ident, file in zip(client_file_ids, files):
        # Transport bounds the entire request; hash the full rejected bytes too,
        # rather than reporting a truncated prefix as file size/content identity.
        content = await file.read(100 * 1024 * 1024 + 128 * 1024 + 1)
        entries.append((ident, file.filename or "", content))
        await file.close()
    data = await run_in_threadpool(svc.upload, token, import_id, entries, key, csrf)
    if all(item.upload_status == "rejected" for item in data.items):
        from fastapi.responses import JSONResponse

        failure = dto.UploadFailure(
            meta=dto.ImportMeta(request_id=request.state.request_id),
            error=dto.UploadFailureInfo(
                details=dto.UploadFailureDetails(
                    items=data.items,
                    import_revision=data.import_revision,
                    file_set_version=data.file_set_version,
                )
            ),
        )
        return JSONResponse(
            status_code=422,
            content=failure.model_dump(mode="json"),
            headers={"ETag": '"' + data.import_revision + '"'},
        )
    response.headers["ETag"] = '"' + data.import_revision + '"'
    return wrap(request, data)


@router.post(
    "/imports/{import_id}/analyze",
    operation_id="I03",
    status_code=202,
    response_model=dto.ImportEnvelope[dto.AnalysisAccepted],
    responses={**ERRORS, 202: {"headers": ETAG}},
    dependencies=[Depends(mutations), Depends(bounded_json)],
)
def analyze(
    import_id: UUID,
    body: dto.AnalyzeRequest,
    request: Request,
    response: Response,
    key: Key = None,
    match: Match = None,
    csrf: CSRF = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    strict_query(request)
    data = svc.analyze(token, import_id, body, key, match, csrf)
    response.headers["ETag"] = '"' + data.import_revision + '"'
    return wrap(request, data, poll=2000)


@router.get(
    "/imports/{import_id}",
    operation_id="I04",
    response_model=dto.ImportEnvelope[dto.ImportRead],
    responses={**ERRORS, 200: {"headers": ETAG}},
)
async def read(
    import_id: UUID,
    request: Request,
    response: Response,
    files_limit: int = Query(50, ge=1, le=100),
    files_cursor: str | None = Query(None, max_length=4096),
    include_preview: bool = False,
    preview_id: UUID | None = None,
    rows_limit: int = Query(50, ge=1, le=100),
    rows_cursor: str | None = Query(None, max_length=4096),
    classification: (
        Literal["NEW", "UNCHANGED", "CHANGED", "INVALID", "CONFLICT"] | None
    ) = None,
    include: (
        Literal[
            "configurations",
            "preview",
            "configurations,preview",
            "preview,configurations",
        ]
        | None
    ) = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    await read_query(
        request,
        (
            "files_limit",
            "files_cursor",
            "include_preview",
            "preview_id",
            "rows_limit",
            "rows_cursor",
            "classification",
            "include",
        ),
    )
    data = await run_in_threadpool(
        svc.read,
        token,
        import_id,
        files_limit,
        files_cursor,
        include_preview or bool(include and "preview" in include),
        preview_id,
        rows_limit,
        rows_cursor,
        classification,
        bool(include and "configurations" in include),
    )
    response.headers["ETag"] = '"' + data.import_revision + '"'
    return wrap(request, data)


@router.get(
    "/imports/{import_id}/mapping-summary",
    operation_id="M01",
    response_model=dto.ImportEnvelope[dto.MappingSummary],
    responses={**ERRORS, 200: {"headers": ETAG}},
)
async def summary(
    import_id: UUID,
    request: Request,
    response: Response,
    include_clean_sheets: bool = False,
    include_profile_details: bool = False,
    svc=Depends(service),
    token=Depends(session_token),
):
    await read_query(request, ("include_clean_sheets", "include_profile_details"))
    data = await run_in_threadpool(
        svc.summary, token, import_id, include_profile_details, include_clean_sheets
    )
    response.headers["ETag"] = '"' + data.mapping_revision + '"'
    return wrap(request, data)


@router.get(
    "/imports/{import_id}/mappings",
    operation_id="M02",
    response_model=dto.ImportEnvelope[dto.MappingList],
    responses=ERRORS,
)
async def mappings(
    import_id: UUID,
    request: Request,
    sheet_id: UUID | None = None,
    review_only: bool = True,
    status: (
        Literal[
            "auto_mapped", "resolved", "needs_confirmation", "ambiguous", "unmatched"
        ]
        | None
    ) = None,
    include_details: bool = False,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, max_length=4096),
    svc=Depends(service),
    token=Depends(session_token),
):
    await read_query(
        request,
        ("sheet_id", "review_only", "status", "include_details", "limit", "cursor"),
    )
    data, page = await run_in_threadpool(
        svc.mappings,
        token,
        import_id,
        sheet_id,
        review_only,
        status,
        include_details,
        limit,
        cursor,
    )
    return wrap(request, data, page=page)


@router.get(
    "/imports/{import_id}/sheets/{sheet_id}/field-options",
    operation_id="M03",
    response_model=dto.ImportEnvelope[dto.FieldOptions],
    responses=ERRORS,
)
async def field_options(
    import_id: UUID,
    sheet_id: UUID,
    request: Request,
    mapping_id: UUID | None = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    await read_query(request, ("mapping_id",))
    return wrap(
        request,
        await run_in_threadpool(
            svc.field_options, token, import_id, sheet_id, mapping_id
        ),
    )


@router.patch(
    "/imports/{import_id}/mappings/{mapping_id}",
    operation_id="M04",
    response_model=dto.ImportEnvelope[dto.MappingUpdated],
    responses={**ERRORS, 200: {"headers": ETAG}},
    dependencies=[Depends(mutations), Depends(bounded_json)],
)
def resolve(
    import_id: UUID,
    mapping_id: UUID,
    body: dto.TargetRequest | dto.ResolveRequest,
    request: Request,
    response: Response,
    key: Key = None,
    match: Match = None,
    csrf: CSRF = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    strict_query(request)
    data = svc.resolve(token, import_id, mapping_id, body, key, match, csrf)
    response.headers["ETag"] = '"' + data.mapping_revision + '"'
    return wrap(request, data)


@router.post(
    "/stores/{store_id}/mapping-profiles/{profile_id}/decisions",
    operation_id="N5",
    response_model=dto.ImportEnvelope[dto.DecisionResult],
    responses={**ERRORS, 200: {"headers": ETAG}},
    dependencies=[Depends(mutations), Depends(bounded_json)],
)
def decide(
    store_id: UUID,
    profile_id: UUID,
    body: Annotated[
        dto.Approve | dto.Reject | dto.RequestChanges | dto.Retire, Body(discriminator="decision")
    ],
    request: Request,
    response: Response,
    key: Key = None,
    match: Match = None,
    csrf: CSRF = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    strict_query(request)
    data = svc.decision(token, store_id, profile_id, body, key, match, csrf)
    response.headers["ETag"] = '"' + data.lifecycle_revision + '"'
    return wrap(request, data)


@router.post(
    "/imports/{import_id}/process",
    operation_id="I05",
    status_code=202,
    response_model=dto.ImportEnvelope[dto.PreviewAccepted] | dto.ImportEnvelope[dto.CommitAccepted],
    responses={
        **ERRORS,
        202: {"headers": ETAG},
        200: {"model": dto.ImportEnvelope[dto.ConfirmationResult], "headers": ETAG},
    },
    dependencies=[Depends(mutations), Depends(bounded_json)],
)
def process(
    import_id: UUID,
    body: Annotated[
        dto.PreviewRequest | dto.CommitRequest | dto.ConfirmReviewRequest,
        Body(discriminator="phase"),
    ],
    request: Request,
    response: Response,
    key: Key = None,
    match: Match = None,
    csrf: CSRF = None,
    svc=Depends(service),
    token=Depends(session_token),
):
    strict_query(request)
    if isinstance(body, dto.ConfirmReviewRequest):
        data = svc.confirm_review(token, import_id, body, key, match, csrf)
        envelope = dto.ImportEnvelope[dto.ConfirmationResult].model_validate(
            wrap(request, data)
        )
        return JSONResponse(
            envelope.model_dump(mode="json"),
            status_code=200,
            headers={"ETag": '"' + data.import_revision + '"'},
        )
    data = svc.preview(token, import_id, body, key, match, csrf)
    response.headers["ETag"] = '"' + data.import_revision + '"'
    return wrap(request, data, poll=2000)


@router.get(
    "/imports/{import_id}/completion",
    operation_id="I06",
    response_model=dto.ImportEnvelope[dto.ImportCompletion],
    responses=ERRORS,
    dependencies=[Depends(no_body_query)],
)
def completion(
    import_id: UUID, request: Request, svc=Depends(service), token=Depends(session_token)
):
    return wrap(request, svc.completion(token, import_id))


@router.get(
    "/jobs/{job_id}",
    operation_id="J01",
    response_model=dto.ImportEnvelope[dto.JobView],
    responses=ERRORS,
    dependencies=[Depends(no_body_query)],
)
def job(
    job_id: UUID, request: Request, svc=Depends(service), token=Depends(session_token)
):
    data = request.app.state.planning_exports.job(token,job_id)
    if data is None:data = svc.job(token, job_id)
    return wrap(request, data, poll=2000 if data.status in {"queued", "running"} else 0)
