"""Six read-only routes. Query syntax only; computation/authority outside routes."""

from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BeforeValidator
from starlette.concurrency import run_in_threadpool
from app.api.auth import session_token
from app.application.contracts.auth import AuthError
from app.application.contracts import public_reads as dto

router = APIRouter(prefix="/api/v1", tags=["Menu and inventory reads"])
READ_HEADERS = {
    "Cache-Control": {"schema": {"type": "string", "enum": ["private, no-store"]}},
    "X-Request-ID": {"schema": {"type": "string", "format": "uuid"}},
}
ERRORS = {
    200: {"headers": READ_HEADERS},
    **{
        s: {"model": dto.ReadErrorEnvelope, "headers": READ_HEADERS}
        for s in (400, 401, 403, 404, 409, 422, 503)
    },
}


def canonical_uuid(value):
    try:
        result = UUID(value)
        if str(result) != value:
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Canonical UUID required") from None


ResourceId = Annotated[UUID, BeforeValidator(canonical_uuid)]
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(min_length=1, max_length=4096)]
Snapshot = Annotated[str | None, Query(min_length=1, max_length=128)]


def service(request: Request):
    return request.app.state.public_reads


async def read_query(request, allowed):
    if any(
        key not in allowed
        or key != "ingredient_id"
        and len(request.query_params.getlist(key)) != 1
        for key in request.query_params
    ):
        raise AuthError("INVALID_FILTER", 422)
    async for chunk in request.stream():
        if chunk:
            raise AuthError("INVALID_REQUEST", 400)


def search(q):
    if q is not None:
        q = q.strip()
        if not 1 <= len(q) <= 200:
            raise AuthError("INVALID_FILTER", 422)
    return q


@router.get(
    "/stores/{store_id}/products",
    operation_id="P01",
    response_model=dto.CatalogEnvelope[dto.Menu],
    responses=ERRORS,
)
async def menu(
    store_id: ResourceId,
    request: Request,
    q: str | None = None,
    status: Literal["active", "paused"] | None = None,
    sort: Literal["name", "-name", "selling_price", "-selling_price"] = "name",
    limit: Limit = 50,
    cursor: Cursor = None,
    reads=Depends(service),
    token=Depends(session_token),
):
    await read_query(request, ("q", "status", "sort", "limit", "cursor"))
    return await run_in_threadpool(
        reads.menu,
        token,
        store_id,
        request.state.request_id,
        q=search(q),
        status=status,
        sort=sort,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/stores/{store_id}/products/{product_id}",
    operation_id="P02",
    response_model=dto.CatalogEnvelope[dto.ProductDetail],
    responses=ERRORS,
)
async def product(
    store_id: ResourceId,
    product_id: ResourceId,
    request: Request,
    reads=Depends(service),
    token=Depends(session_token),
):
    await read_query(request, ())
    return await run_in_threadpool(
        reads.product, token, store_id, product_id, request.state.request_id
    )


@router.get(
    "/stores/{store_id}/inventory",
    operation_id="V01",
    response_model=dto.InventoryEnvelope[dto.InventoryList],
    responses=ERRORS,
)
async def inventory(
    store_id: ResourceId,
    request: Request,
    q: str | None = None,
    ingredient_id: Annotated[list[ResourceId] | None, Query()] = None,
    status: str | None = None,
    sort: Literal["name", "-name", "nearest_expiry"] = "name",
    limit: Limit = 50,
    cursor: Cursor = None,
    reads=Depends(service),
    token=Depends(session_token),
):
    await read_query(
        request, ("q", "ingredient_id", "status", "sort", "limit", "cursor")
    )
    statuses = tuple(status.split(",")) if status is not None else ()
    if statuses and (
        not set(statuses)
        <= {"expired", "empty", "low_stock", "near_expiry", "watch", "stable"}
        or len(set(statuses)) != len(statuses)
    ):
        raise AuthError("INVALID_FILTER", 422)
    return await run_in_threadpool(
        reads.inventory,
        token,
        store_id,
        request.state.request_id,
        q=search(q),
        statuses=statuses,
        identifiers=tuple(ingredient_id or ()),
        sort=sort,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/stores/{store_id}/inventory/{ingredient_id}",
    operation_id="V02",
    response_model=dto.InventoryEnvelope[dto.InventoryDetail],
    responses=ERRORS,
)
async def inventory_detail(
    store_id: ResourceId,
    ingredient_id: ResourceId,
    request: Request,
    snapshot_id: Snapshot = None,
    lot_limit: Limit = 50,
    reads=Depends(service),
    token=Depends(session_token),
):
    await read_query(request, ("snapshot_id", "lot_limit"))
    return await run_in_threadpool(
        reads.lot_read,
        token,
        store_id,
        ingredient_id,
        request.state.request_id,
        detail=True,
        snapshot_id=snapshot_id,
        limit=lot_limit,
    )


@router.get(
    "/stores/{store_id}/inventory/{ingredient_id}/lots",
    operation_id="V03",
    response_model=dto.InventoryEnvelope[dto.Lots],
    responses=ERRORS,
)
async def lots(
    store_id: ResourceId,
    ingredient_id: ResourceId,
    request: Request,
    snapshot_id: Snapshot = None,
    limit: Limit = 50,
    cursor: Cursor = None,
    sort: Literal["expiry_date,batch_code"] = "expiry_date,batch_code",
    reads=Depends(service),
    token=Depends(session_token),
):
    await read_query(request, ("snapshot_id", "limit", "cursor", "sort"))
    return await run_in_threadpool(
        reads.lot_read,
        token,
        store_id,
        ingredient_id,
        request.state.request_id,
        snapshot_id=snapshot_id,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/stores/{store_id}/inventory/{ingredient_id}/movements",
    operation_id="V04",
    response_model=dto.InventoryEnvelope[dto.Movements],
    responses=ERRORS,
)
async def movements(
    store_id: ResourceId,
    ingredient_id: ResourceId,
    request: Request,
    snapshot_id: Snapshot = None,
    limit: Limit = 50,
    cursor: Cursor = None,
    sort: Literal["-occurred_at"] = "-occurred_at",
    reads=Depends(service),
    token=Depends(session_token),
):
    await read_query(request, ("snapshot_id", "limit", "cursor", "sort"))
    return await run_in_threadpool(
        reads.movements,
        token,
        store_id,
        ingredient_id,
        request.state.request_id,
        snapshot_id=snapshot_id,
        limit=limit,
        cursor=cursor,
    )
