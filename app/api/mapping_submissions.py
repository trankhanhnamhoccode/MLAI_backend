"""MQ01--MQ03 transport, with separate batch and submission CAS domains."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response
from app.api.auth import mutations, session_token, strict_query
from app.application.contracts.auth import Envelope, Meta, AuthError
from app.application.contracts import mapping_submissions as dto, import_mapping as mapping
from app.application.contracts.collaboration import PageEnvelope, PageMeta, WorkflowErrorEnvelope
from app.api.collaboration import strict_transport, ETAG_RESPONSE

router=APIRouter(prefix='/api/v1',tags=['Mapping submissions'],dependencies=[Depends(strict_transport)])
ERRORS={s:{'model':WorkflowErrorEnvelope} for s in (400,401,403,404,409,412,413,422,428,503)}


def service(request: Request):
    from app.application.use_cases.mapping_submissions import MappingSubmissions
    return MappingSubmissions(request.app.state.import_staging)


@router.post('/imports/{import_id}/mapping-submissions',operation_id='MQ01',response_model=Envelope[dto.MappingSubmission],responses={**ERRORS,200:ETAG_RESPONSE,201:{'model':Envelope[dto.MappingSubmission],**ETAG_RESPONSE}},dependencies=[Depends(mutations)])
def mutate(import_id: UUID,body: Annotated[dto.SubmitMapping | dto.WithdrawMapping,Body(discriminator='action')],
           request: Request,response: Response,token=Depends(session_token),use_cases=Depends(service),
           key: str | None=Header(None,alias='Idempotency-Key'),match: str | None=Header(None,alias='If-Match'),
           csrf: str | None=Header(None,alias='X-CSRF-Token')):
    strict_query(request)
    data,revision=use_cases.mutate(token,import_id,body,key,match,csrf)
    response.status_code=201 if body.action=='submit' else 200
    response.headers['ETag']='"'+revision+'"'
    return dict(data=data,meta=Meta(request_id=request.state.request_id),error=None)


@router.get('/stores/{store_id}/mapping-submissions',operation_id='MQ02',response_model=PageEnvelope[dto.MappingQueue],responses=ERRORS)
async def listing(store_id: UUID,request: Request,state: dto.State | None=None,file_id: UUID | None=None,import_id: UUID | None=None,
                  limit: int=Query(50,ge=1,le=100),cursor: str | None=Query(None,min_length=1,max_length=4096),
                  token=Depends(session_token),use_cases=Depends(service)):
    from starlette.concurrency import run_in_threadpool
    strict_query(request,('state','file_id','import_id','limit','cursor'))
    if await request.body(): raise AuthError('INVALID_REQUEST',400)
    data,meta=await run_in_threadpool(use_cases.list,token,store_id,state,file_id,import_id,limit,cursor)
    return dict(data=data,meta=PageMeta(request_id=request.state.request_id,**meta),error=None)


@router.get('/stores/{store_id}/mapping-submissions/{submission_id}',operation_id='MQ03',response_model=Envelope[mapping.MappingReviewDetail],responses={**ERRORS,200:ETAG_RESPONSE})
async def detail(store_id: UUID,submission_id: UUID,request: Request,response: Response,
                 evidence_limit: int=Query(20,ge=1,le=100),evidence_cursor: str | None=Query(None,min_length=1,max_length=4096),
                 token=Depends(session_token),use_cases=Depends(service)):
    from starlette.concurrency import run_in_threadpool
    strict_query(request,('evidence_limit','evidence_cursor'))
    if await request.body(): raise AuthError('INVALID_REQUEST',400)
    data=await run_in_threadpool(use_cases.detail,token,store_id,submission_id,evidence_limit,evidence_cursor)
    response.headers['ETag']='"'+data.submission.version+'"'
    return dict(data=data,meta=Meta(request_id=request.state.request_id),error=None)
