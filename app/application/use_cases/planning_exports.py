"""Purpose-specific durable PDF acceptance/claim/publication and private reads."""
from uuid import UUID,uuid4
from threading import Lock
from time import perf_counter
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from app.repositories.planning_export import PlanningExportRepository
from app.repositories.auth import AuthRepository
from app.repositories.planning import PlanningRepository
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.auth_crypto import digest as key_digest
from app.infrastructure.planning_process import current_process,liveness
from app.infrastructure.storage.planning_pdf import PDFArtifactError
from app.application.contracts.auth import AuthError
from app.application.contracts.planning_configuration import ConfigurationError
from app.application.contracts.planning_export import ExportRecord,ExportAccepted,ExportJobContext,ExportJobResult
from app.application.contracts.planning_run import PlanningClaim,PlanningPersistenceError
from app.application.contracts.planning_pdf import PlanningPDFDocument
from app.application.contracts import import_mapping as jobs
from app.application.planning_serialization import canonical_bytes,digest,exact_json
from app.application.planning_inspection_projection import ingredient_detail,explanation

EXPORT_PERMISSIONS=('planning.export','planning.result.read','budget.read','procurement.cost.read')
MAX_DOCUMENT_BYTES=3*1024*1024


def decode_export(row):
    if row is None:raise AuthError('RESOURCE_NOT_FOUND',404)
    try:
        if row.record_digest!=digest('export',row.record_json):raise ValueError('Export digest mismatch')
        record=ExportRecord.model_validate(row.record_json)
        if row.revision<1 or canonical_bytes(record)!=canonical_bytes(row.record_json):raise ValueError('Noncanonical export record')
        for column,field in [('id','export_id'),('job_id','job_id'),('run_id','run_id'),('store_id','store_id'),
            ('actor_id','actor_id'),('key_digest','key_digest'),('request_digest','request_digest'),('status','status'),('created_at','created_at')]:
            if getattr(row,column)!=getattr(record,field):raise ValueError('Export column identity mismatch')
        return record
    except (ValueError,TypeError,ValidationError) as error:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503) from error


def document(record,view,option):
    details=tuple(ingredient_detail(record,view,i.ingredient_id,option.option_id) for i in record.capture.prepared.ingredients) if record.capture and record.capture.prepared else ()
    result=PlanningPDFDocument(view=view,option=option,ingredients=details,explanation=explanation(record,view,option.option_id),
        source_evidence=record.public_capture.operational_evidence if record.public_capture else None)
    if len(result.model_dump_json().encode('utf-8'))>MAX_DOCUMENT_BYTES:raise ConfigurationError('RESOURCE_LIMIT_EXCEEDED',413)
    return result


class PlanningExports:
    def discovery(self,token,run_id,request_id,option_id=None,status=None,limit=50,cursor=None,snapshot_id=None):
        from app.application.contracts import planning_export as dto
        from app.application.contracts.discovery import DiscoveryMeta
        from app.application.use_cases.collaboration_paging import page
        if status is not None and status not in ('queued','running','completed','failed'):
            raise AuthError('INVALID_FILTER',422)
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with auth_session(connection) as s:
                repo=PlanningRepository(s);store=repo.owning_store(run_id)
                if store is None:
                    self.auth._resolve(s,token);raise AuthError('RESOURCE_NOT_FOUND',404)
                actor,authority,_=self.auth.authorize_in_session(s,token,store,EXPORT_PERMISSIONS)
                try:run,view=self.public.retained.read(repo.get(store,run_id))
                except PlanningPersistenceError as error:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503) from error
                if run.public_acceptance is None:raise AuthError('RESOURCE_NOT_FOUND',404)
                if option_id is not None and (view.result is None or option_id not in
                    {o.option_id for o in view.result.options}|{o.option_id for o in view.result.strategies}):
                    raise AuthError('INVALID_OPTION',422)
                rows=PlanningExportRepository(s).for_run(store,run_id,status,option_id)
                if (rows or run.status=='completed') and view.result is None:
                    raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
                items=[]
                for row in rows:
                    record=decode_export(row)
                    if record.receipt.result_digest!=run.result_digest:
                        raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
                    availability='pending' if record.status in ('queued','running') else 'failed'
                    if record.status=='completed':
                        availability=self.artifacts.availability(record.export_id,record.result.sha256,record.result.byte_count)
                    verified=availability=='available'
                    retry_evidence=run.capture is not None and run.public_capture is not None and run.public_capture.ingredient_labels is not None
                    actions=('poll',) if availability=='pending' else ('download',) if verified else ('request_new_export',) if retry_evidence else ()
                    items.append(dto.ExportSummary(export_id=record.export_id,run_id=run_id,job_id=record.job_id,
                        option_id=record.receipt.option_id,created_by_user_id=record.actor_id,created_at=record.created_at,
                        status=record.status,result_digest=record.receipt.result_digest,render_version=record.receipt.render_version,
                        version=row.record_digest,artifact_availability=availability,completed_at=record.completed_at,
                        error_code=record.error_code or ('EXPORT_ARTIFACT_UNAVAILABLE' if availability in ('missing','unverifiable') else None),
                        download_url=record.result.download_url if verified else None,sha256=record.result.sha256 if verified else None,
                        byte_count=record.result.byte_count if verified else None,allowed_actions=actions))
                binding=[str(actor.user_id),str(store),authority.authorization_version,view.response_version]
                filters=dict(run_id=str(run_id),option_id=option_id,status=status)
                selected,meta=page(self.auth,token,'export-discovery',tuple(items),binding,filters,limit,cursor,
                    fingerprint_facts=[binding,filters])
                if snapshot_id is not None and snapshot_id!=meta['snapshot_id']:raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
                s.commit()
                return dto.ExportCollectionEnvelope(data=dto.ExportCollection(items=selected),
                    meta=DiscoveryMeta(request_id=request_id,**meta),error=None)

    def __init__(self,public,artifacts,renderer):
        self.public,self.auth,self.engine=public,public.auth,public.engine
        self.artifacts,self.renderer=artifacts,renderer
        self.clock=self.auth.clock
        self._execution=Lock()
        self._recovery_after=None

    def _worker_authority(self,s,record):
        repo=AuthRepository(s)
        user=repo.lock_user(record.actor_id);session=repo.lock_session(record.session_digest)
        account=repo.account(record.actor_id)
        if not user or not user.active or not session or session.user_id!=record.actor_id or not account or not account.credential_ready or session.credential_revision!=account.credential_revision or account.verified_email!=user.email:
            raise AuthError('UNAUTHENTICATED',401)
        store=repo.lock_store(record.store_id);member=repo.lock_membership(record.store_id,record.actor_id)
        if not store or not store.active or not member or not member.active:raise AuthError('PERMISSION_DENIED')
        _,permissions=self.auth._summary(s,store,member)
        if not set(EXPORT_PERMISSIONS)<=set(permissions):raise AuthError('PERMISSION_DENIED')
        self._run_binding(s,record)

    @staticmethod
    def _run_binding(s,record):
        # Export fields/hash are not proof of the parent Run's Store ownership.
        # Read identity metadata only; never recapture historical business facts.
        store=PlanningRepository(s).owning_store(record.run_id)
        if store!=record.store_id:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)

    def _run(self,s,store,run_id):
        try:record,view=self.public.retained.read(PlanningRepository(s).get(store,run_id))
        except PlanningPersistenceError as error:
            if error.code=='NOT_FOUND':raise AuthError('RESOURCE_NOT_FOUND',404) from error
            raise ConfigurationError('RESULT_INTEGRITY_ERROR',409) from error
        if record.public_acceptance is None:raise AuthError('RESOURCE_NOT_FOUND',404)
        if record.status!='completed' or view.result is None:raise ConfigurationError('RESULT_NOT_READY',409)
        return record,view

    @staticmethod
    def _option(view,option_id):
        selected=option_id if option_id is not None else view.result.winner_option_id
        if selected is None:raise ConfigurationError('WINNER_NOT_AVAILABLE',409)
        option=next((o for o in view.result.options if o.option_id==selected),None)
        if option is None:
            # A known strategy binding with no candidate is not exportable.
            known=any(s.option_id==selected for s in view.result.strategies)
            raise ConfigurationError('OPTION_NOT_EXPORTABLE' if known else 'OPTION_NOT_FOUND',409 if known else 404)
        return option

    def _reconcile(self,expected,authority):
        with auth_session(self.engine) as s:
            authority(s)
            row=PlanningExportRepository(s).get(expected.export_id)
            if row is None:raise AuthError('SERVICE_UNAVAILABLE',503)
            observed=decode_export(row)
            self._run_binding(s,observed)
            if canonical_bytes(observed)!=canonical_bytes(expected):raise AuthError('SERVICE_UNAVAILABLE',503)
            if observed.result:self.artifacts.read(observed.export_id,observed.result.sha256,observed.result.byte_count)
            s.commit()
            return observed

    def accept(self,token,run_id,body,key,csrf):
        try:
            if key is None or str(UUID(key))!=key:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise ConfigurationError('INVALID_REQUEST',400) from None
        kd=key_digest(key);fp=digest('export-request',dict(run_id=run_id,request=body));expected=None
        try:
            with auth_session(self.engine) as s:
                store=PlanningRepository(s).owning_store(run_id)
                if store is None:self.auth._resolve(s,token);raise AuthError('RESOURCE_NOT_FOUND',404)
                actor,_,_=self.auth.authorize_in_session(s,token,store,EXPORT_PERMISSIONS,csrf=csrf or '')
                prior=PlanningExportRepository(s).by_key(actor.user_id,store,run_id,kd)
                if prior:
                    retained=decode_export(prior)
                    if retained.request_digest!=fp:raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
                    s.commit();return retained.receipt
                record,view=self._run(s,store,run_id);option=self._option(view,body.option_id)
                if not self.renderer.available:raise ConfigurationError('SERVICE_UNAVAILABLE',503)
                document(record,view,option)  # Actual representation budget at admission.
                outstanding=PlanningExportRepository(s).outstanding_count(store)
                if outstanding>=20:raise ConfigurationError('RESOURCE_LIMIT_EXCEEDED',413)
                export_id,job_id=uuid4(),uuid4()
                expected=ExportRecord(export_id=export_id,job_id=job_id,run_id=run_id,store_id=store,actor_id=actor.user_id,
                    session_digest=actor.session_digest,key_digest=kd,request_digest=fp,request=body,created_at=self.clock(),
                    receipt=ExportAccepted(export_id=export_id,job_id=job_id,run_id=run_id,option_id=option.option_id,result_digest=record.result_digest))
                PlanningExportRepository(s).add_accepted(expected)
                s.info['pdf_export_accept']=True;s.commit()
                return expected.receipt
        except SQLAlchemyError:
            if expected is None:raise
            return self._reconcile(expected,lambda s:self.auth.authorize_in_session(s,token,expected.store_id,EXPORT_PERMISSIONS,csrf=csrf or '')).receipt

    def _transition(self,ident,build,*,authority=True):
        expected=None
        try:
            with auth_session(self.engine) as s:
                original=decode_export(PlanningExportRepository(s).get(ident))
                if authority:self._worker_authority(s,original)
                row=PlanningExportRepository(s).get(ident,lock=True)
                old=decode_export(row)
                expected=ExportRecord.model_validate(build(s,old))
                if any(getattr(expected,f)!=getattr(old,f) for f in ('export_id','job_id','run_id','receipt','actor_id','store_id','session_digest','key_digest','request_digest','request','created_at')):
                    raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
                row.record_json=exact_json(expected);row.record_digest=digest('export',expected)
                row.status=expected.status;row.revision+=1
                s.info['pdf_export_transition']=expected.status;s.commit()
                return expected
        except SQLAlchemyError:
            if expected is None:raise
            return self._reconcile(expected,(lambda s:self._worker_authority(s,expected)) if authority else lambda s:None)

    def claim(self,ident):
        def build(s,old):
            if old.status!='queued':raise ConfigurationError('EXPORT_NOT_QUEUED',409)
            return {**old.model_dump(round_trip=True),'status':'running','started_at':self.clock(),
                'claim':PlanningClaim(token=uuid4(),generation=old.attempt,process=current_process())}
        # Claim identity is durable even if the actor's rights were revoked;
        # materialization then fails without source reads or artifact publication.
        return self._transition(ident,build,authority=False)

    @staticmethod
    def _owner(old,claim):
        if old.status!='running' or old.claim!=claim:raise ConfigurationError('STALE_EXPORT_CLAIM',409)

    def fail(self,ident,claim,code):
        def build(s,old):
            self._owner(old,claim)
            return {**old.model_dump(round_trip=True),'status':'failed','completed_at':self.clock(),'error_code':code}
        return self._transition(ident,build,authority=False)

    def run_one(self):
        if not self._execution.acquire(False):return None
        try:
            with auth_session(self.engine) as s:
                ident=PlanningExportRepository(s).next_queued_id()
            if ident is None:return None
            try:claimed=self.claim(ident)
            except ConfigurationError as error:
                if error.code=='EXPORT_NOT_QUEUED':return None
                raise
            return self.execute(claimed)
        finally:self._execution.release()

    def execute(self,claimed):
        prepared=None;started=perf_counter()
        try:
            with auth_session(self.engine) as s:
                self._worker_authority(s,claimed)
                actual=decode_export(PlanningExportRepository(s).get(claimed.export_id));self._owner(actual,claimed.claim)
                record,view=self._run(s,claimed.store_id,claimed.run_id)
                if record.result_digest!=claimed.receipt.result_digest:raise ConfigurationError('RESULT_INTEGRITY_ERROR',409)
                report=document(record,view,self._option(view,claimed.receipt.option_id));s.commit()
            # No DB session or authorization lock during expensive rendering/IO.
            if not self.renderer.available:raise ConfigurationError('SERVICE_UNAVAILABLE',503)
            if claimed.receipt.render_version=='planning-pdf/1':data=self.renderer.render_legacy(report)
            elif claimed.receipt.render_version=='planning-pdf/2':data=self.renderer.render_v2(report)
            else:data=self.renderer.render(report)
            if perf_counter()-started>120:raise RuntimeError('Bounded PDF render deadline exceeded')
            prepared=self.artifacts.prepare(claimed.export_id,data)
            def publish(s,old):
                self._owner(old,claimed.claim)
                self.artifacts.publish(old.export_id,prepared)
                result=ExportJobResult(resource_id=old.export_id,run_id=old.run_id,option_id=old.receipt.option_id,
                    download_url=f'/api/v1/procurement-plans/{old.run_id}/exports/{old.export_id}',sha256=prepared.sha256,byte_count=prepared.byte_count)
                return {**old.model_dump(round_trip=True),'status':'completed','completed_at':self.clock(),'result':result}
            return self._transition(claimed.export_id,publish)
        except Exception as error:
            with auth_session(self.engine) as s:actual=decode_export(PlanningExportRepository(s).get(claimed.export_id))
            if actual.status in ('completed','failed'):raise
            code=error.code if isinstance(error,(AuthError,ConfigurationError)) else 'ARTIFACT_WRITE_FAILED' if isinstance(error,(PDFArtifactError,OSError)) else 'RENDER_FAILED'
            return self.fail(claimed.export_id,claimed.claim,code)
        finally:
            if prepared:self.artifacts.discard(prepared)

    def recover(self):
        with auth_session(self.engine) as s:
            rows=PlanningExportRepository(s).running_page(self._recovery_after)
            self._recovery_after=(rows[-1].created_at,rows[-1].id) if len(rows)==100 else None
            candidates=tuple(decode_export(r) for r in rows)
        recovered=[]
        for record in candidates:
            if liveness(record.claim.process)=='DEAD':
                def build(s,old):
                    self._owner(old,record.claim)
                    if liveness(old.claim.process)!='DEAD':raise ConfigurationError('EXPORT_OWNER_NOT_DEAD',409)
                    return {**old.model_dump(round_trip=True),'status':'failed','completed_at':self.clock(),'error_code':'PROCESS_INTERRUPTED'}
                try:recovered.append(self._transition(record.export_id,build,authority=False))
                except ConfigurationError as error:
                    if error.code not in ('STALE_EXPORT_CLAIM','EXPORT_OWNER_NOT_DEAD'):raise
        return tuple(recovered)

    def retry_failed(self,ident):
        """Internal controlled retry, one additional attempt; no public retry route."""
        def build(s,old):
            if old.status!='failed' or old.attempt>=2 or old.error_code not in ('RENDER_FAILED','ARTIFACT_WRITE_FAILED','PROCESS_INTERRUPTED','SERVICE_UNAVAILABLE'):
                raise ConfigurationError('EXPORT_RETRY_NOT_ALLOWED',409)
            outstanding=PlanningExportRepository(s).outstanding_count(old.store_id)
            if outstanding>=20:raise ConfigurationError('RESOURCE_LIMIT_EXCEEDED',413)
            return {**old.model_dump(round_trip=True),'status':'queued','attempt':old.attempt+1,'started_at':None,'completed_at':None,'claim':None,'error_code':None}
        return self._transition(ident,build)

    def job(self,token,job_id):
        with auth_session(self.engine) as s:
            row=PlanningExportRepository(s).by_job(job_id)
            if row is None:return None
            self.auth.authorize_in_session(s,token,row.store_id,EXPORT_PERMISSIONS)
            record=decode_export(row)
            self._run_binding(s,record)
            data=jobs.JobView(job_id=record.job_id,operation='planning_pdf_export',status=record.status,
                stage='rendering' if record.status=='running' else record.status,progress=1 if record.status=='completed' else None,
                created_at=record.created_at,started_at=record.started_at,completed_at=record.completed_at,
                context=ExportJobContext(store_id=record.store_id,run_id=record.run_id,export_id=record.export_id),result=record.result,
                error=jobs.JobError(code=record.error_code,message='Không thể hoàn tất xuất báo cáo.') if record.error_code else None)
            s.commit();return data

    def download(self,token,run_id,ident):
        with auth_session(self.engine) as s:
            row=PlanningExportRepository(s).get(ident)
            if row is None or row.run_id!=run_id:
                self.auth._resolve(s,token);raise AuthError('RESOURCE_NOT_FOUND',404)
            self.auth.authorize_in_session(s,token,row.store_id,EXPORT_PERMISSIONS)
            record=decode_export(row)
            self._run_binding(s,record)
            if record.status!='completed':raise ConfigurationError('EXPORT_NOT_READY',409)
            try:data=self.artifacts.read(ident,record.result.sha256,record.result.byte_count)
            except PDFArtifactError as error:raise ConfigurationError('EXPORT_ARTIFACT_UNAVAILABLE',503) from error
            s.commit();return data,record.result.sha256
