"""Resolve supplied intent with the C02 resolver; never execute or persist a Run."""
from app.application.contracts.planning_setup import PlanningConfiguration,SavedRequirementsRecord
from app.application.contracts.decision_capture_v2 import MenuProduct
from app.application.contracts import readiness as dto
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.planning_runtime_policy import policy_for_acceptance
from app.application.import_identity import content_digest


def resolve_context(facts,store,now,request):
    from app.application.readiness_evaluation import issue,versions
    saved=next((r for r in facts.saved if r.saved_requirement_id==request.saved_requirement_id),None)
    if request.requirements_mode=='saved' and saved is None:
        code='SAVED_REQUIREMENTS_ARCHIVED' if request.saved_requirement_id in facts.archived_saved_ids else 'SAVED_REQUIREMENT_NOT_FOUND'
        return None,(issue(code,'configuration'),)
    source=PlanningConfiguration(store_id=store,currency=facts.snapshot['stores'][0]['currency'],
        timezone=facts.snapshot['stores'][0]['timezone'],read_at=now,
        configuration_version=content_digest(versions(facts).model_dump(mode='json')),
        provenance='Current contextual configuration read',consistency='SINGLE_SNAPSHOT_DECLARED',
        defaults=facts.defaults,budget_ceiling=facts.cap,
        products=tuple(MenuProduct(store_id=store,product_id=p['id'],name=p['name'],selling_unit=p['selling_unit'],active=p['active']) for p in facts.snapshot['products']),
        policy=policy_for_acceptance(facts,request.forecast_start_date),
        saved=SavedRequirementsRecord(store_id=store,saved_requirement_id=saved.saved_requirement_id,version=saved.version,
            name=saved.name,updated_at=saved.updated_at,requirements=saved.requirements) if saved else None)
    result=resolve_planning_setup(request,source)
    return result.resolution,tuple(dto.Issue(code=e.code,source='configuration',scope='STORE',entity_id=None,
        affected_dates=(),details=dto.IssueDetails(field=e.field)) for e in result.errors)
