"""S4.9 coherent owned RR snapshot: source pins, declarations and /2 facts."""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from app.application.planning_source_proof import source_confirmation
from app.application.contracts.decision_capture_v2 import DecisionCaptureOutcomeV2
from app.application.contracts.planning_public_evidence import PublicPlanningCapture,IngredientLabel
from app.application.contracts.planning_source_evidence import (PlanningSourceEvidence,TermEvidence,SupplierEvidence,FeeEvidence,DeclarationEvidence)
from app.application.contracts.planning_public import ForecastView
from app.application.planning_public_projection import notice,forecast_window_warnings
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations,prepare_planning_pipeline
from app.application.forecast_preparation import prepare_observations
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.forecast_serving import source_digest
from app.application.readiness_evaluation import latest_declarations,contains,versions
from app.application.operational_import_facts import current_fees
from app.application.decision_capture_v2_validation import project_capture_v2
from app.application.contracts.auth import AuthError
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.database.decision_capture_v2 import read_operational_facts_v2
from app.repositories.readiness import load_readiness


@dataclass(frozen=True)
class PlanningCaptured:
    declarations: PlanningPipelineDeclarations
    capture: DecisionCaptureOutcomeV2
    evidence: PublicPlanningCapture
    source_matches: bool


def declarations_for(record,facts,forecast_id,now):
    from app.application.planning_admission import planning_declarations
    return planning_declarations(record.resolution,facts,forecast_id,now,run_id=record.run_id,
        offer_policy=record.public_acceptance.offer_eligibility_policy if record.public_acceptance else None)


class PostgresPlanningCapture:
    def __init__(self,engine,clock):self.engine,self.clock=engine,clock

    def read(self,record,served,preparation,elapsed):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with auth_session(connection) as s:
                facts=load_readiness(s,record.store_id)
                now=self.clock()
                matched=True
                try:current=prepare_observations(facts,record.store_id,record.request.forecast_start_date,
                    native_challenger=record.public_acceptance.challenger_test is not None)
                except AuthError as error:
                    if error.code!='NO_COMPUTABLE_PRODUCTS':raise
                    matched=served is None
                else:
                    matched=served is not None and serialize_prepared(current).digest==served.identity.prepared_digest and source_digest(facts,current)==served.identity.source_digest
                declarations,extra,bounds=declarations_for(record,facts,served.run.id if served else None,now)
                request=prepare_planning_pipeline(record.resolution,declarations)
                source=read_operational_facts_v2(s,request,self.clock)
                if extra:source=source.model_copy(update={'problems':(*source.problems,*extra)})
                snap=facts.snapshot
                term_ids={str(t.term_id) for t in source.supplier_term_scope}
                term_versions={r['id']:r['version'] for r in snap['supplier_terms']}
                source_evidence=PlanningSourceEvidence(
                    terms=tuple(TermEvidence(term_id=r['id'],version=term_versions[r['id']],source_system_key=r['source_system_key'],
                        source_record_key=r['source_record_key'],payload=r['payload']) for r in snap['term_source_records'] if r['id'] in term_ids),
                    suppliers=tuple(SupplierEvidence(supplier_id=r['supplier_id'],source_system_key=r['source_system_key'],source_record_key=r['source_record_key']) for r in snap['supplier_source_records']),
                    fees=tuple(FeeEvidence(id=r['id'],version=r['version'],source_system_key=r['source_system_key'],source_record_key=r['source_record_key'],payload=r['payload']) for r in current_fees(snap) if contains(r['payload'],record.request.forecast_start_date)),
                    declarations=tuple(DeclarationEvidence(id=r['id'],version=r['version'],source_system_key=r['source_system_key'],source_record_key=r['source_record_key'],
                        dependency_digest=r['dependency_digest'],payload=r['payload']) for r,d in latest_declarations(snap)),bounds=bounds,
                    observed_history_product_ids=tuple(sorted({UUID(r['product_id']) for r in snap['sales_daily'] if r['sales_date']<=str(record.resolution.cutoff_date)
                        and any(p['id']==r['product_id'] and p['active'] for p in snap['products'])})),
                    confirmations=tuple(source_confirmation(entity,identifier,r,snap['import_audit'])
                        for entity,rows in (
                            ('supplier_term',[(r['id'],r) for r in snap['term_source_records'] if r['id'] in term_ids]),
                            ('supplier',[(r['supplier_id'],r) for r in snap['supplier_source_records']]),
                            ('fee',[(r['id'],r) for r in current_fees(snap) if contains(r['payload'],record.request.forecast_start_date)]),
                            ('declaration',[(r['id'],r) for r,d in latest_declarations(snap)]))
                        for identifier,r in rows) if declarations.offer_admission else None)
        capture=DecisionCaptureOutcomeV2(semantics_version='operational_capture/2',request=request,captured_at=source.facts.captured_at,
            source=source,**project_capture_v2(request,source))
        identity=served.identity if served else None
        forecast=ForecastView(forecast_run_id=served.run.id,input_digest=identity.prepared_digest,model_type=identity.model_type,
            model_version=identity.model_version,artifact_identity=identity.artifact_identity,start_date=served.run.forecast_start_date,
            end_date=served.run.forecast_end_date,history_start_date=preparation.prepared.request.history_start_date,
            history_end_date=preparation.prepared.request.cutoff_date,training_start_date=identity.training_start_date,
            training_end_date=identity.training_end_date,reused=served.reused,quality_status='not_evaluated',
            warnings=(tuple(notice(w.code,entity='product' if w.product_id else 'forecast',entity_id=w.product_id) for w in source.facts.forecast.execution.warnings)
                if source.facts.forecast and source.facts.forecast.execution else ())+
                forecast_window_warnings(identity.training_start_date,identity.training_end_date,served.run.forecast_start_date,served.run.forecast_end_date)) if served else None
        return PlanningCaptured(declarations,capture,PublicPlanningCapture(forecast=forecast,identity=identity,source_versions=versions(facts),
            preparation_seconds=elapsed,operational_evidence=source_evidence,
            ingredient_labels=tuple(IngredientLabel(ingredient_id=r['id'],name=r['name'],sku=r['sku']) for r in snap['ingredients']
                if capture.prepared and any(str(i.ingredient_id)==r['id'] for i in capture.prepared.ingredients))),matched)
