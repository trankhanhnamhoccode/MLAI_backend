"""C02/C03 orchestration over the durable Run; current sensitive-read fences."""
from uuid import UUID
from datetime import timedelta
from app.application.contracts.auth import AuthError
from app.application.contracts.planning_configuration import ConfigurationError,FieldError
from app.application.contracts.planning_setup import PlanningConfiguration,SavedRequirementsRecord
from app.application.contracts.decision_capture_v2 import MenuProduct
from app.application.contracts.planning_public_evidence import PublicPlanningAcceptance
from app.application.contracts import planning_public as dto
from app.application.contracts.planning_run import PlanningPersistenceError
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_run import PlanningRunUseCases,decode_row
from app.application.planning_runtime_policy import policy_for_acceptance
from app.application.planning_public_projection import project_run
from app.application.readiness_evaluation import versions
from app.application.import_identity import content_digest
from app.infrastructure.database.auth_session import auth_session
from app.repositories.readiness import load_readiness,fence_readiness_inputs
from app.repositories.planning import PlanningRepository
from app.repositories.planning_configuration import saved_row
from app.application.readiness_evaluation import contains

RUN_PERMISSIONS=('planning.run','budget.read','procurement.cost.read')
READ_PERMISSIONS=('planning.result.read','budget.read','procurement.cost.read')


def public_failure(error):
    cause=error.__cause__
    while cause is not None:
        if isinstance(cause,(AuthError,ConfigurationError)):raise cause
        cause=cause.__cause__
    if error.code=='NOT_FOUND':raise AuthError('RESOURCE_NOT_FOUND',404) from error
    if error.code=='EVIDENCE_NOT_VERIFIED':raise AuthError('EVIDENCE_NOT_VERIFIED',503) from error
    if error.code=='UNSUPPORTED_RESULT_VERSION':raise AuthError('UNSUPPORTED_RESULT_VERSION',503) from error
    if error.code=='IDEMPOTENCY_KEY_REUSED':raise ConfigurationError(error.code,409) from error
    raise AuthError('RESULT_INTEGRITY_UNAVAILABLE' if error.code=='RESULT_INTEGRITY_UNAVAILABLE' else 'SERVICE_UNAVAILABLE',503) from error


def reject(code,field):
    raise ConfigurationError('INVALID_PLANNING_CONFIGURATION',422,
        (FieldError(code=code,field=field,message='Kiểm tra lại dữ liệu hoặc cấu hình tại trường này.'),))


def bounded_inspection(value):
    if len(value.model_dump_json().encode('utf-8'))>3*1024*1024:
        raise ConfigurationError('RESOURCE_LIMIT_EXCEEDED',413)
    return value


class PublicPlanning:
    def __init__(self,auth,forecast):
        self.auth,self.engine,self.forecast=auth,auth.engine,forecast
        self.runs=PlanningRunUseCases(self.engine,clock=auth.clock)
        from app.application.planning_retained_reads import VerifiedPlanningReads
        self.retained=VerifiedPlanningReads()

    def accept(self,token,store,request,key,csrf):
        try:
            if key is None or str(UUID(key))!=key:raise ValueError()
        except (ValueError,TypeError,AttributeError):
            raise ConfigurationError('INVALID_REQUEST',400) from None
        # Caller identity only; actual acceptance/replay repeats authorization in
        # the Run transaction, in User -> session -> Store -> membership order.
        with auth_session(self.engine) as s:
            actor,_,_=self.auth.authorize_in_session(s,token,store,RUN_PERMISSIONS,csrf=csrf or '')
            s.commit()
        def authority(s):
            current,_,_=self.auth.authorize_in_session(s,token,store,RUN_PERMISSIONS,csrf=csrf or '')
            if current!=actor:raise AuthError('UNAUTHENTICATED',401)
        def resolve(s):
            fence_readiness_inputs(s)
            facts=load_readiness(s,store)
            menu=tuple(MenuProduct(store_id=store,product_id=r['id'],name=r['name'],selling_unit=r['selling_unit'],active=r['active']) for r in facts.snapshot['products'])
            active={p.product_id for p in menu if p.active}
            if not active:reject('NO_ACTIVE_PRODUCTS','products')
            required={r['ingredient_id'] for r in facts.snapshot['recipe_lines'] if r['recipe_id'] in {
                r['id'] for r in facts.snapshot['recipes'] if UUID(r['product_id']) in active
                and r['assigned'] and r['effective_from']<=str(request.forecast_start_date+timedelta(days=6))
                and (r['effective_to'] is None or r['effective_to']>=str(request.forecast_start_date))
            }}
            # All captured offers/lots are bounded, never silently truncated.
            suppliers={r['id'] for r in facts.snapshot['suppliers'] if r['active']}
            offers=[r for r in facts.snapshot['supplier_terms'] if r['ingredient_id'] in required and r['supplier_id'] in suppliers and r['active'] and contains(r,request.forecast_start_date)]
            lots=[r for r in facts.snapshot['inventory_lots'] if r['ingredient_id'] in required]
            if len(active)>50 or len(required)>100 or len(offers)>100 or len(lots)>1000:
                reject('RESOURCE_LIMIT_EXCEEDED','scope')
            saved=next((r for r in facts.saved if r.saved_requirement_id==request.saved_requirement_id),None)
            if request.requirements_mode=='saved' and (saved is None or saved.state!='active'):
                row=saved_row(s,store,request.saved_requirement_id)
                reject('SAVED_REQUIREMENTS_ARCHIVED' if row and row.state=='archived' else 'SAVED_REQUIREMENT_NOT_FOUND','saved_requirement_id')
            if facts.serving is None:reject('MODEL_CONFIGURATION_UNKNOWN','model_configuration')
            source=PlanningConfiguration(store_id=store,currency=facts.snapshot['stores'][0]['currency'],
                timezone=facts.snapshot['stores'][0]['timezone'],read_at=self.auth.clock(),
                configuration_version=content_digest(versions(facts).model_dump(mode='json')),
                provenance='C02 fenced canonical configuration read',consistency='SINGLE_SNAPSHOT_DECLARED',
                defaults=facts.defaults,budget_ceiling=facts.cap,products=menu,policy=policy_for_acceptance(facts,request.forecast_start_date),
                saved=SavedRequirementsRecord(store_id=store,saved_requirement_id=saved.saved_requirement_id,version=saved.version,name=saved.name,
                    updated_at=saved.updated_at,requirements=saved.requirements) if saved else None)
            result=resolve_planning_setup(request,source)
            if result.resolution is None:
                codes={e.code for e in result.errors}
                if 'DEFAULT_REQUIREMENTS_CHANGED' in codes:raise ConfigurationError('DEFAULT_REQUIREMENTS_CHANGED',409)
                raise ConfigurationError('INVALID_PLANNING_CONFIGURATION',422,tuple(FieldError(code=e.code,field=e.field,message=e.message) for e in result.errors))
            return result.resolution
        def metadata(s,resolved):
            current,summary,_=self.auth.authorize_in_session(s,token,store,RUN_PERMISSIONS,csrf=csrf or '')
            facts=load_readiness(s,store)
            pin=self.forecast.acceptance_pin(facts,store,request.forecast_start_date)
            return PublicPlanningAcceptance(schema_version='planning_public_acceptance/2' if pin else 'planning_public_acceptance/1',
                challenger_test=pin,session_digest=current.session_digest,authorization_version=summary.authorization_version,
                serving=facts.serving,offer_eligibility_policy='offer_eligibility/1',receipt_warnings=tuple(dto.PlanningNotification(code=w.code,message='Review saved/default change history.',
                    details=dto.PlanningNotificationDetails(field=w.field,default_updated_at=w.default_updated_at,saved_updated_at=w.saved_updated_at)) for w in resolved.warnings))
        try:return self.runs.accept(actor.user_id,store,key,request,resolve,authority=authority,public_metadata=metadata)
        except PlanningPersistenceError as error:public_failure(error)

    def read(self,token,run_id):
        record,projected=self.read_record(token,run_id)
        return projected,record.public_acceptance.receipt_warnings

    def read_record(self,token,run_id,*,with_authority=False,require_cached=False,evidence_only=False):
        # Resolve owning Store only; content is checked after current Store grants.
        with auth_session(self.engine) as s:
            store=PlanningRepository(s).owning_store(run_id)
            if store is None:
                self.auth._resolve(s,token)
                raise AuthError('RESOURCE_NOT_FOUND',404)
            actor,authorization,_=self.auth.authorize_in_session(s,token,store,READ_PERMISSIONS)
            try:
                row=PlanningRepository(s).get(store,run_id)
                record,projected=(self.retained.read(row,evidence=True) if evidence_only else
                    self.retained.read(row,require_cached=True) if require_cached else self.retained.read(row))
            except PlanningPersistenceError as error:public_failure(error)
            if record.public_acceptance is None:raise AuthError('RESOURCE_NOT_FOUND',404)
            s.commit()
            return (record,projected,actor,authorization) if with_authority else (record,projected)

    def assistant_evidence(self,token,run_id,*,option_id=None,ingredient_id=None):
        """Durable retained consistency read; recheck C03 rights on every call."""
        from app.application.decision_evidence_projection import project_evidence
        record,view=self.read_record(token,run_id,evidence_only=True)
        return bounded_inspection(project_evidence(record,view,option_id=option_id,ingredient_id=ingredient_id))

    def ingredients(self,token,run_id,request_id,option_id=None,limit=50,cursor=None,ingredient_ids=()):
        import base64,hmac,json
        from app.application.contracts import planning_inspection as inspection
        from app.application.contracts.auth import Pagination
        from app.application.planning_inspection_projection import computed,select,ingredient_row
        record,view,actor,authorization=self.read_record(token,run_id,with_authority=True)
        prepared=computed(record)
        option,status=select(view,option_id)
        # Session-bound signed cursor includes the verified aggregate revision
        # digest and exact representation/filter. No retained result recompute.
        identity=[str(actor.user_id),str(record.store_id),authorization.authorization_version,str(run_id),view.response_version,option_id,limit,sorted(str(i) for i in ingredient_ids)]
        offset=0
        if cursor:
            try:
                payload,signature=cursor.rsplit('.',1)
                if not hmac.compare_digest(signature,self.auth.cursor_signer.sign(token,'planning-ingredients',payload)):raise ValueError()
                saved=json.loads(base64.urlsafe_b64decode(payload+'='*((-len(payload))%4)))
                if saved['identity']!=identity:raise ConfigurationError('SNAPSHOT_NOT_AVAILABLE',409)
                offset=saved['offset']
                if type(offset) is not int or offset<0:raise ValueError()
            except (ValueError,KeyError,TypeError):raise ConfigurationError('INVALID_CURSOR',422) from None
        rows=sorted((i for i in prepared.ingredients if not ingredient_ids or i.ingredient_id in ingredient_ids),key=lambda i:i.ingredient_id)
        page=rows[offset:offset+limit]
        next_cursor=None
        if offset+limit<len(rows):
            payload=base64.urlsafe_b64encode(json.dumps(dict(identity=identity,offset=offset+limit),separators=(',',':')).encode()).decode().rstrip('=')
            next_cursor=payload+'.'+self.auth.cursor_signer.sign(token,'planning-ingredients',payload)
        return bounded_inspection(inspection.InspectionEnvelope[inspection.IngredientNavigator](
            data=inspection.IngredientNavigator(run_id=run_id,result_digest=record.result_digest,
                selected_option_id=option.option_id if option else None,selection_status=status,
                items=tuple(ingredient_row(record,view,i,option,status) for i in page)),
            meta=inspection.InspectionMeta(request_id=request_id,run_id=run_id,result_digest=record.result_digest,
                response_version=view.response_version,pagination=Pagination(limit=limit,next_cursor=next_cursor,total_count=len(rows))),error=None))

    def ingredient(self,token,run_id,ingredient_id,request_id,option_id=None):
        from app.application.contracts import planning_inspection as inspection
        from app.application.planning_inspection_projection import ingredient_detail
        record,view=self.read_record(token,run_id)
        return bounded_inspection(inspection.InspectionEnvelope[inspection.IngredientDetail](
            data=ingredient_detail(record,view,ingredient_id,option_id),
            meta=inspection.InspectionMeta(request_id=request_id,run_id=run_id,result_digest=record.result_digest,response_version=view.response_version),error=None))

    def explanation(self,token,run_id,option_id=None):
        from app.application.planning_inspection_projection import explanation
        record,view=self.read_record(token,run_id)
        return explanation(record,view,option_id)

    def history(self,token,store,request_id,limit=50,cursor=None,status=None,start_from=None,start_to=None,
                creator=None,created_date_from=None,created_date_to=None,snapshot_id=None):
        import base64,hmac,json
        from app.application.contracts import history as history
        from app.application.contracts.auth import Pagination
        statuses=tuple(sorted(set(status.split(',')))) if status else ()
        if any(value not in ('queued','running','completed','failed') for value in statuses) or (start_from and start_to and start_from>start_to):
            raise ConfigurationError('INVALID_FILTER',422)
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with auth_session(connection) as s:
                actor,authorization,_=self.auth.authorize_in_session(s,token,store,READ_PERMISSIONS)
                repo=PlanningRepository(s)
                from app.application.planning_discovery import local_created_range,captured_budget
                zone=repo.timezone(store)
                lower,upper=local_created_range(created_date_from,created_date_to,zone)
                extra=dict(creator=creator,created_from=lower,created_to=upper)
                total,revision=repo.history_revision(store,statuses,start_from,start_to,**extra)
                identity=[str(actor.user_id),str(store),authorization.authorization_version,list(statuses),str(start_from) if start_from else None,str(start_to) if start_to else None,limit]
                identity += [str(creator) if creator else None,str(created_date_from) if created_date_from else None,str(created_date_to) if created_date_to else None,zone]
                snapshot='run-list-'+content_digest([revision,identity])
                if snapshot_id is not None and snapshot_id!=snapshot:raise ConfigurationError('SNAPSHOT_NOT_AVAILABLE',409)
                offset=0
                if cursor:
                    try:
                        payload,signature=cursor.rsplit('.',1)
                        if not hmac.compare_digest(signature,self.auth.cursor_signer.sign(token,'run-history',payload)):raise ValueError()
                        saved=json.loads(base64.urlsafe_b64decode(payload+'='*((-len(payload))%4)))
                        if saved['identity']!=identity:raise ValueError()
                        if saved['snapshot']!=snapshot:raise ConfigurationError('SNAPSHOT_NOT_AVAILABLE',409)
                        offset=saved['offset']
                        if type(offset) is not int or not 0<offset<total:raise ValueError()
                    except (ValueError,KeyError,TypeError):raise ConfigurationError('INVALID_CURSOR',422) from None
                rows=repo.history_page(store,statuses,start_from,start_to,offset,limit,**extra)
                items=[]
                for row in rows:
                    try:record,view=self.retained.read(row)
                    except PlanningPersistenceError as error:public_failure(error)
                    items.append(history.RunSummary(run_id=record.run_id,store_id=store,status=record.status,accepted_at=record.accepted_at,
                        started_at=record.started_at,completed_at=record.finished_at,forecast_start_date=record.request.forecast_start_date,
                        forecast_end_date=record.resolution.forecast_end_date,requirements_mode=record.request.requirements_mode,
                        created_by=history.RunCreator(user_id=record.actor_id,display_name=None),
                        winner_option_id=view.result.winner_option_id if view.result else None,outcome=record.outcome,error_code=record.error_code,
                        result_schema_version=record.result.semantics_version if record.result else None,result_digest=record.result_digest,record_version=view.response_version,captured_budget=captured_budget(row.record_json)))
                next_cursor=None
                if offset+limit<total:
                    payload=base64.urlsafe_b64encode(json.dumps(dict(identity=identity,snapshot=snapshot,offset=offset+limit),separators=(',',':')).encode()).decode().rstrip('=')
                    next_cursor=payload+'.'+self.auth.cursor_signer.sign(token,'run-history',payload)
                result=history.RunHistoryEnvelope(data=history.RunHistory(items=tuple(items)),meta=history.RunHistoryMeta(request_id=request_id,snapshot_id=snapshot,
                    pagination=Pagination(limit=limit,next_cursor=next_cursor,total_count=total),timezone=zone,
                    applied_filters=history.RunHistoryFilters(created_by_user_id=creator,created_date_from=created_date_from,created_date_to=created_date_to)),error=None)
                s.commit()
                return result
