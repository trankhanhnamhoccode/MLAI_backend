"""PLAN4 setup projection from canonical IMP14 readiness, without computation."""
from datetime import date
from app.application.contracts import planning_context as dto
from app.application.contracts.planning_configuration import BudgetCeiling
from app.application.import_identity import content_digest


def descriptors():
    rows=(
        ('requirements.paths[].path','path',True,False,dict(enum=('LOW','BASE','HIGH'),unique=True,max_items=3),'none'),
        ('requirements.paths[].min_fill_rate_percent','decimal_text',False,False,dict(minimum='0',maximum='100',max_fraction_digits=32),'same_path_default'),
        ('requirements.paths[].product_overrides','product_override_array',False,False,dict(max_items=50,unique_product_id=True),'same_path_default_replace'),
        ('requirements.budget_limit','decimal_text',False,True,dict(minimum='0',max_integer_digits=18,max_fraction_digits=18),'current_store_ceiling'))
    return tuple(dto.FieldDescriptor(field=f,type=t,required=r,nullable=n,constraints=c,inheritance=i) for f,t,r,n,c,i in rows)


def project_context(facts,readiness,*,planning_available=False):
    store=facts.snapshot['stores'][0]
    action=next(r for r in readiness.actions if r.action=='planning')
    default=facts.defaults;cap=facts.cap
    saved=facts.saved
    if not saved:availability,codes='unavailable',('NO_SAVED_REQUIREMENTS',)
    elif any(r.validation.status=='valid' for r in saved):availability,codes='available',()
    elif any(r.validation.status=='unknown' for r in saved):availability,codes='unknown',('SAVED_VALIDATION_UNKNOWN',)
    else:availability,codes='unavailable',('NO_VALID_SAVED_REQUIREMENTS',)
    reason_codes=tuple(dict.fromkeys(i.code for i in action.blockers))
    return dto.Context(store_id=readiness.store_id,currency=store['currency'],timezone=store['timezone'],
        observed_at=readiness.evaluated_at,context_version=content_digest(dict(sources=readiness.source_versions.model_dump(mode='json'),evaluation=readiness.data_version)),
        latest_business_date=max((date.fromisoformat(r['sales_date']) for r in facts.snapshot['sales_daily'] if r['sales_date']<=str(readiness.as_of_date)),default=None),
        defaults=dto.Defaults(cutoff_date=readiness.cutoff_date,forecast_start_date=readiness.evaluated_forecast_start_date),
        default_requirements=default.requirements if default else None,default_requirements_version=default.version if default else None,
        default_requirements_updated_at=default.updated_at if default else None,
        budget_ceiling=BudgetCeiling(**cap.model_dump(exclude={'provenance'})) if cap else None,
        products=tuple(dto.ProductBrief(product_id=p['id'],name=p['name'],selling_unit=p['selling_unit']) for p in sorted(
            (r for r in facts.snapshot['products'] if r['active']),key=lambda p:(p['name'],p['id']))),
        custom_requirement_fields=descriptors(),requirements_modes=(
            dto.Mode(mode='default',availability='available' if default else 'unavailable',reason_codes=() if default else ('DEFAULT_CONFIGURATION_UNAVAILABLE',)),
            dto.Mode(mode='custom',availability='available',reason_codes=()),dto.Mode(mode='saved',availability=availability,reason_codes=codes)),
        saved_requirements=tuple(dto.Saved(**r.model_dump(include={'saved_requirement_id','name','updated_at','requirements','validation','warnings'})) for r in saved),
        capabilities=dto.Capabilities(winner_selection=planning_available,saved_requirements=True),
        readiness=dto.PlanningReadiness(status={'ready':'ready','blocked':'not_ready','unknown':'unknown'}[action.availability],
            can_generate=action.can_execute,reason_codes=reason_codes,evaluated_forecast_start_date=readiness.evaluated_forecast_start_date,
            scope_estimate=readiness.scope_estimate,history_watermark=readiness.history_watermark,
            assessment=readiness.planning_assessment,forecast=readiness.forecast_assessment))
