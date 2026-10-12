"""N6/N8 transport; all authority and stock writes live in application layer."""
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from app.api.auth import mutations, session_token, strict_query
from app.api.import_staging import Key, Match, CSRF, bounded_json
from app.application.contracts.auth import Envelope, Meta, ErrorEnvelope
from app.application.contracts import stock_writes as dto

router = APIRouter(prefix="/api/v1", tags=["Inventory writes"])
ERRORS = {status: {"model": ErrorEnvelope} for status in (400,401,403,404,409,412,413,422,428,503)}

def service(request: Request):
    return request.app.state.stock_writes

def wrap(request, value):
    return dict(data=value, meta=Meta(request_id=request.state.request_id), error=None)

@router.post("/stores/{store_id}/inventory/receipts", operation_id="N6", status_code=201,
    response_model=Envelope[dto.StockReceiptResult], responses={**ERRORS,200:{"model":Envelope[dto.StockReceiptResult]}},
    dependencies=[Depends(mutations),Depends(bounded_json)])
def receive(store_id: UUID, body: dto.StockReceiptRequest, request: Request, response: Response,
            key: Key=None, csrf: CSRF=None, svc=Depends(service), token=Depends(session_token)):
    strict_query(request)
    result,replay=svc.receive(token,store_id,body,key,csrf)
    response.status_code=200 if replay else 201
    return wrap(request,result)

@router.put("/stores/{store_id}/inventory/{ingredient_id}/threshold", operation_id="N8",
    response_model=Envelope[dto.ThresholdResult], responses=ERRORS,
    dependencies=[Depends(mutations),Depends(bounded_json)])
def threshold(store_id: UUID, ingredient_id: UUID, body: dto.ThresholdRequest, request: Request,
              response: Response, key: Key=None, csrf: CSRF=None, match: Match=None,
              svc=Depends(service), token=Depends(session_token)):
    strict_query(request)
    result,_=svc.threshold(token,store_id,ingredient_id,body,key,csrf,match)
    response.headers["ETag"]='"'+result.version+'"'
    return wrap(request,result)
