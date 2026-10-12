"""N10 durable acceptance and N11 private binary download."""
from fastapi import APIRouter,Depends,Request,Response
from starlette.concurrency import run_in_threadpool
from app.api.auth import session_token,mutations,strict_query
from app.api.import_staging import CSRF,read_query
from app.api.planning_public import PlanningKey,request_boundary
from app.application.contracts.planning_setup import ResourceId
from app.application.contracts import planning_export as dto
from app.application.contracts.planning_configuration import ConfigurationError,ConfigurationErrorEnvelope

router=APIRouter(prefix='/api/v1',tags=['Planning PDF export'],responses={
    code:{'model':ConfigurationErrorEnvelope} for code in (400,401,403,404,409,413,422,503)})


@router.post('/procurement-plans/{plan_id}/exports',operation_id='N10',status_code=202,
    response_model=dto.ExportEnvelope,dependencies=[Depends(mutations),Depends(request_boundary)])
def accept(plan_id:ResourceId,body:dto.ExportRequest,request:Request,key:PlanningKey,csrf:CSRF=None,token=Depends(session_token)):
    strict_query(request)
    if any(h in request.headers for h in ('If-Match','If-None-Match')):raise ConfigurationError('INVALID_REQUEST',400)
    receipt=request.app.state.planning_exports.accept(token,plan_id,body,key,csrf)
    return dto.ExportEnvelope(data=receipt,meta=dto.ExportMeta(request_id=request.state.request_id),error=None)


@router.get('/procurement-plans/{plan_id}/exports/{export_id}',operation_id='N11',response_class=Response,
    responses={200:{'content':{'application/pdf':{'schema':{'type':'string','format':'binary'}}},
        'headers':{name:{'schema':{'type':'string'}} for name in ('Content-Disposition','Content-Length','ETag','Cache-Control','X-Content-Type-Options')}}})
async def download(plan_id:ResourceId,export_id:ResourceId,request:Request,token=Depends(session_token)):
    await read_query(request)
    data,sha=await run_in_threadpool(request.app.state.planning_exports.download,token,plan_id,export_id)
    return Response(data,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="shelfcash-plan-{plan_id}.pdf"',
        'ETag':'"'+sha+'"','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
