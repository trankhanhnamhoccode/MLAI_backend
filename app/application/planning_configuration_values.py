"""Save/validation policy over explicit configuration values; no persistence I/O."""
from decimal import Decimal
from app.application.contracts import planning_configuration as dto
from app.application.contracts.planning_setup import StoredRequirements
from app.application.use_cases.planning_setup import resolve_custom_paths, ResolutionRejected
from app.application.recipe_schedule_plan import exact


def field_error(code, field):
    return dto.FieldError(code=code, field=field, message='Kiểm tra lại cấu hình tại trường này.')


def resolve_save(body, defaults, cap, products):
    try:
        paths, reference = resolve_custom_paths(body.requirements, defaults, body.default_requirements_version)
    except ResolutionRejected as error:
        code = error.errors[0].code
        if code == 'DEFAULT_REQUIREMENTS_CHANGED':
            raise dto.ConfigurationError(code,409) from None
        mapped = {'DEFAULT_REQUIREMENTS_VERSION_REQUIRED':'DEFAULT_VERSION_REQUIRED'}.get(code,code)
        raise dto.ConfigurationError('INVALID_PLANNING_CONFIGURATION',field_errors=(field_error(mapped,error.errors[0].field),)) from None
    requirements = StoredRequirements(paths=tuple(sorted((p.model_copy(update={
        'min_fill_rate_percent':exact(p.min_fill_rate_percent),
        'product_overrides':tuple(sorted((o.model_copy(update={'min_fill_rate_percent':exact(o.min_fill_rate_percent)}) for o in p.product_overrides),key=lambda o:str(o.product_id)))
    }) for p in paths),key=lambda p:('LOW','BASE','HIGH').index(p.path))),
        budget_limit=exact(body.requirements.budget_limit) if body.requirements.budget_limit is not None else None)
    ids={p.id:p.active for p in products}
    for i,p in enumerate(requirements.paths):
        for j,o in enumerate(p.product_overrides):
            if not ids.get(o.product_id,False):
                raise dto.ConfigurationError('INVALID_PLANNING_CONFIGURATION',field_errors=(field_error('PRODUCT_NOT_AVAILABLE',f'requirements.paths[{i}].product_overrides[{j}].product_id'),))
    if requirements.budget_limit is not None:
        code='BUDGET_CEILING_UNKNOWN' if cap is None else 'BUDGET_LIMIT_EXCEEDS_CEILING' if Decimal(requirements.budget_limit)>Decimal(cap.amount) else None
        if code:
            raise dto.ConfigurationError('INVALID_PLANNING_CONFIGURATION',field_errors=(field_error(code,'requirements.budget_limit'),))
    return requirements,reference


def saved_validation(state, requirements, cap, products):
    if state == 'archived':
        return dto.Validation(status='invalid',reason_codes=('SAVED_REQUIREMENTS_ARCHIVED',))
    ids={p.id:p.active for p in products}
    codes=[]
    if any(not ids.get(o.product_id,False) for p in requirements.paths for o in p.product_overrides):
        codes.append('PRODUCT_NOT_AVAILABLE')
    if cap and requirements.budget_limit is not None and Decimal(requirements.budget_limit)>Decimal(cap.amount):
        codes.append('BUDGET_LIMIT_EXCEEDS_CEILING')
    if codes:
        return dto.Validation(status='invalid',reason_codes=tuple(codes))
    return dto.Validation(status='unknown' if cap is None else 'valid',reason_codes=('BUDGET_CEILING_UNKNOWN',) if cap is None else ())


def detail(row, defaults, cap, products):
    requirements=StoredRequirements.model_validate(row.requirements_json)
    updated=defaults.updated_at if defaults else None
    code='DEFAULT_CHANGE_HISTORY_UNKNOWN' if updated is None else 'DEFAULT_CHANGED_SINCE_SAVED_UPDATE' if row.updated_at<updated else None
    warnings=(dto.Notification(code=code,message='Kiểm tra lịch sử thay đổi cấu hình mặc định.',details=dto.NotificationDetails(default_updated_at=updated,saved_updated_at=row.updated_at)),) if code else ()
    return dto.SavedDetail(saved_requirement_id=row.id,store_id=row.store_id,name=row.name,version=row.version,
        state=row.state,created_at=row.created_at,updated_at=row.updated_at,created_by_user_id=row.created_by,
        updated_by_user_id=row.updated_by,requirements=requirements,default_reference=row.default_reference_json,
        validation=saved_validation(row.state,requirements,cap,products),warnings=warnings)
