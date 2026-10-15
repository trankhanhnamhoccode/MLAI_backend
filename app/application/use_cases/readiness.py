"""R01/C01 coherent detached read-only facts and current authorization fences."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from app.application.contracts.auth import AuthError
from app.application.readiness_evaluation import ACTION_READS,evaluate
from app.application.forecast_preparation import prepare_observations
from app.application.planning_context_projection import project_context
from app.infrastructure.database.auth_session import auth_session
from app.repositories.readiness import load_readiness


class ReadinessReads:
    def __init__(self,auth,forecast,*,planning_available=lambda:False):
        self.auth,self.engine,self.forecast=auth,auth.engine,forecast
        self.planning_available=planning_available

    def _authorize(self,token,store,required):
        with auth_session(self.engine) as s:
            _,summary,permissions=self.auth.authorize_in_session(s,token,store,required)
            s.commit()
            return summary,permissions

    def read(self,token,store,actions=('import','menu','inventory'),start=None,*,context=False,planning_request=None):
        if context:
            actions=('planning',)
        if not actions or len(set(actions))!=len(actions) or any(a not in ACTION_READS for a in actions) or (start is not None and not {'forecast','planning'}&set(actions)):
            raise AuthError('INVALID_FILTER',422)
        required=tuple(sorted({p for a in actions for p in ACTION_READS[a]}))
        summary,permissions=self._authorize(token,store,required)
        requested=None
        if planning_request is not None:
            if 'planning' not in actions:raise AuthError('INVALID_FILTER',422)
            from app.application.contracts.planning_setup import PlanningRequest
            from pydantic import ValidationError
            from app.application.use_cases.planning_setup import _json_object
            import json
            try:
                if len(planning_request.encode('utf-8'))>65536:raise ValueError()
                requested=PlanningRequest.model_validate(json.loads(planning_request,object_pairs_hook=_json_object))
            except (ValidationError,ValueError,UnicodeError):
                raise AuthError('INVALID_FILTER',422) from None
            if start is not None and start!=requested.forecast_start_date:raise AuthError('INVALID_FILTER',422)
            start=requested.forecast_start_date
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with auth_session(connection) as s:
                facts=load_readiness(s,store)
                now=self.auth.clock()
                evaluated_start=start or now.astimezone(ZoneInfo(facts.snapshot['stores'][0]['timezone'])).date()
        try:
            evaluated_start-timedelta(days=1);evaluated_start+timedelta(days=6)
        except OverflowError:
            if not context:
                raise AuthError('INVALID_FILTER',422) from None
            from app.application.contracts import readiness as dto
            from app.application.readiness_evaluation import versions,issue
            from app.application.import_identity import content_digest
            source_versions=versions(facts)
            from app.application.contracts.planning_context import ContextSourceReadiness
            result=ContextSourceReadiness(store_id=store,as_of_date=evaluated_start,evaluated_at=now,
                data_version=content_digest(source_versions.model_dump(mode='json')),
                evaluated_forecast_start_date=None,cutoff_date=None,source_versions=source_versions,
                scope_estimate=None,history_watermark=None,
                actions=(dto.ActionReadiness(action='planning',availability='blocked',can_execute=False,
                    data_status='invalid',execution_status='unavailable',
                    blockers=(issue('FORECAST_DATE_OUT_OF_RANGE','configuration'),),warnings=()),))
            current,_=self._authorize(token,store,required)
            if current.authorization_version!=summary.authorization_version:
                raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
            return project_context(facts,result,planning_available=self.planning_available())
        assessment=None
        if self.forecast is not None and facts.serving and {'forecast','planning'}&set(actions):
            try:
                prepared=prepare_observations(facts,store,evaluated_start)
            except AuthError as error:
                if error.code!='NO_COMPUTABLE_PRODUCTS':raise
            else:
                assessment=self.forecast.assess(prepared,facts.serving)
        available=self.planning_available()
        result=evaluate(facts,store,now,evaluated_start,actions,permissions,forecast_assessment=assessment,
            forecast_available=self.forecast is not None,planning_available=available,planning_request=requested)
        current,_=self._authorize(token,store,required)
        if current.authorization_version!=summary.authorization_version:
            raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
        return project_context(facts,result,planning_available=available) if context else result

    @staticmethod
    def completion_in_transaction(s,store,now,permissions):
        """Post-write projection in Import's own fenced transaction, no engine/FS."""
        from app.application.contracts.import_mapping import CompletionReadiness,OmittedAction
        actions=tuple(a for a in ('import','menu','inventory') if set(ACTION_READS[a])<=set(permissions))
        facts=load_readiness(s,store)
        today=now.astimezone(ZoneInfo(facts.snapshot['stores'][0]['timezone'])).date()
        evaluation=evaluate(facts,store,now,today,actions,permissions,planning_available=False)
        return CompletionReadiness(evaluated_at=now,as_of_date=today,data_version=evaluation.data_version,
            actions=tuple(a.model_dump() for a in evaluation.actions),evaluated_actions=actions,
            omitted_actions=tuple(OmittedAction(action=a) for a in ('import','menu','inventory') if a not in actions))
