"""Pure setup resolution over explicit retained values, without I/O or fallback."""
from datetime import timedelta
from decimal import Decimal
import json

from pydantic import ValidationError
from app.application.contracts.planning_setup import (
    PlanningRequest, PlanningConfiguration, PlanningFieldError, PlanningWarning,
    PlanningResolutionOutcome, ResolvedPlanningSetup, DefaultReference, SavedReference,
)
from app.application.contracts.procurement import ProcurementBudget, ProductFloor
from app.application.contracts.procurement_v2 import EffectiveRequirements, PathRequirement


class ResolutionRejected(Exception):
    """Only deliberately identified configuration/request rejection; never generic bugs."""
    def __init__(self, code, field, message):
        self.errors = (PlanningFieldError(code=code, field=field, message=message),)
        super().__init__(code)


def _reject(code, field, message):
    raise ResolutionRejected(code, field, message)


def percent_ratio(text: str) -> Decimal:
    # No division/scaleb under ambient context. Wire guard bounds coefficient size.
    value = Decimal(text)
    sign, digits, exponent = value.as_tuple()
    return Decimal((sign, digits, exponent - 2))


def resolve_custom_paths(requirements, defaults, version):
    """Shared inheritance for Save and execution, with no invented budget/history."""
    from app.application.contracts.planning_setup import StoredPath, DefaultReference
    uses_default = any(p.min_fill_rate_percent is None or p.product_overrides is None for p in requirements.paths)
    reference = None
    if uses_default:
        if version is None:
            _reject('DEFAULT_REQUIREMENTS_VERSION_REQUIRED', 'default_requirements_version', 'Default version is required')
        if defaults is None:
            _reject('DEFAULT_CONFIGURATION_UNAVAILABLE', 'default_requirements_version', 'Defaults unavailable')
        if version != defaults.version:
            _reject('DEFAULT_REQUIREMENTS_CHANGED', 'default_requirements_version', 'Defaults changed')
        d = defaults.requirements
        if len(d.paths) != 1 or d.paths[0].path != 'BASE' or Decimal(d.paths[0].min_fill_rate_percent) != 95 or d.paths[0].product_overrides or d.budget_limit is not None:
            _reject('DEFAULT_CONFIGURATION_INVALID', 'default_requirements', 'Invalid defaults')
        reference = DefaultReference(version=defaults.version, updated_at=defaults.updated_at)
    inherited = {p.path: p for p in defaults.requirements.paths} if uses_default else {}
    result = []
    for i, path in enumerate(requirements.paths):
        default = inherited.get(path.path)
        for field in ('min_fill_rate_percent', 'product_overrides'):
            if getattr(path, field) is None and default is None:
                _reject('DEFAULT_VALUE_UNAVAILABLE', f'requirements.paths[{i}].{field}', 'No same-path default')
        result.append(StoredPath(path=path.path,
            min_fill_rate_percent=path.min_fill_rate_percent if path.min_fill_rate_percent is not None else default.min_fill_rate_percent,
            product_overrides=path.product_overrides if path.product_overrides is not None else default.product_overrides))
    return tuple(result), reference


def _project(request: PlanningRequest, source: PlanningConfiguration):
    mode = request.requirements_mode
    ceiling = source.budget_ceiling
    if ceiling is None:
        _reject('BUDGET_CEILING_UNKNOWN', 'budget_ceiling', 'Store budget ceiling is unavailable')
    active = {p.product_id: p for p in source.products if p.active}
    if not active:
        _reject('NO_ACTIVE_PRODUCTS', 'products', 'Store has no active Products')
    if len(active) > 50:
        _reject('RESOURCE_LIMIT_EXCEEDED', 'products', 'Planning supports at most 50 active Products')
    default_ref = saved_ref = None
    warnings = []
    paths = []
    uses_default = mode == 'default' or (mode == 'custom' and any(
        p.min_fill_rate_percent is None or p.product_overrides is None for p in request.requirements.paths))
    if uses_default:
        if request.default_requirements_version is None:
            _reject('DEFAULT_REQUIREMENTS_VERSION_REQUIRED', 'default_requirements_version', 'Default version is required when inheriting defaults')
        if source.defaults is None:
            _reject('DEFAULT_CONFIGURATION_UNAVAILABLE', 'default_requirements_version', 'Default configuration is unavailable')
        if request.default_requirements_version != source.defaults.version:
            _reject('DEFAULT_REQUIREMENTS_CHANGED', 'default_requirements_version', 'Default requirements version has changed')
        # Explicit source must declare the approved product default, not legacy construction.
        default = source.defaults.requirements
        if (len(default.paths) != 1 or default.paths[0].path != 'BASE'
                or Decimal(default.paths[0].min_fill_rate_percent) != 95
                or default.paths[0].product_overrides or default.budget_limit is not None):
            _reject('DEFAULT_CONFIGURATION_INVALID', 'default_requirements', 'Default differs from approved BASE95/no-overrides/current-ceiling policy')
        default_ref = DefaultReference(version=source.defaults.version, updated_at=source.defaults.updated_at)
    if source.saved is not None and source.saved.store_id != source.store_id:
        _reject('SAVED_REQUIREMENT_WRONG_STORE', 'saved_requirement_id', 'Saved setup belongs to another Store')
    if mode == 'default':
        paths = list(default.paths)
        budget_text = None
    elif mode == 'saved':
        record = source.saved
        if record is None or record.saved_requirement_id != request.saved_requirement_id:
            _reject('SAVED_REQUIREMENT_NOT_FOUND', 'saved_requirement_id', 'Saved setup was not found')
        if record.store_id != source.store_id:
            _reject('SAVED_REQUIREMENT_WRONG_STORE', 'saved_requirement_id', 'Saved setup belongs to another Store')
        paths = list(record.requirements.paths)
        budget_text = record.requirements.budget_limit
        saved_ref = SavedReference(saved_requirement_id=record.saved_requirement_id, version=record.version, updated_at=record.updated_at)
        default_at = source.defaults.updated_at if source.defaults else None
        saved_at = record.updated_at
        if default_at is None or saved_at is None:
            warnings.append(PlanningWarning(code='DEFAULT_CHANGE_HISTORY_UNKNOWN', field='saved_requirement_id', default_updated_at=default_at, saved_updated_at=saved_at))
        elif saved_at < default_at:
            warnings.append(PlanningWarning(code='DEFAULT_CHANGED_SINCE_SAVED_UPDATE', field='saved_requirement_id', default_updated_at=default_at, saved_updated_at=saved_at))
    else:
        paths, default_ref = resolve_custom_paths(request.requirements, source.defaults, request.default_requirements_version)
        budget_text = request.requirements.budget_limit
    amount = Decimal(ceiling.amount) if budget_text is None else Decimal(budget_text)
    if amount > Decimal(ceiling.amount):
        _reject('BUDGET_LIMIT_EXCEEDS_CEILING', 'requirements.budget_limit' if mode != 'saved' else 'saved_requirement_id', 'Private budget exceeds current Store ceiling')
    internal = []
    for i, path in enumerate(paths):
        for j, override in enumerate(path.product_overrides):
            product = next((p for p in source.products if p.product_id == override.product_id), None)
            field = f'requirements.paths[{i}].product_overrides[{j}].product_id' if mode == 'custom' else ('saved_requirement_id' if mode == 'saved' else 'default_requirements')
            if product is None:
                _reject('PRODUCT_REFERENCE_UNKNOWN', field, 'Product reference does not exist in Store configuration')
            if not product.active:
                _reject('PRODUCT_REFERENCE_INACTIVE', field, 'Product reference is inactive')
        internal.append(PathRequirement(path=path.path, minimum=percent_ratio(path.min_fill_rate_percent), overrides=tuple(
            ProductFloor(product_id=o.product_id, target=percent_ratio(o.min_fill_rate_percent)) for o in path.product_overrides)))
    reference = ('default/' + source.defaults.version if mode == 'default' else
                 'saved/' + str(saved_ref.saved_requirement_id) + '/' + saved_ref.version if mode == 'saved' else 'custom')
    provenance = f'planning_resolution/1 {reference}; configuration/{source.configuration_version}; {source.provenance}'
    return dict(requirements=EffectiveRequirements(paths=tuple(internal), provenance=provenance),
        budget=ProcurementBudget(state='KNOWN', amount=amount, currency=source.currency, provenance=provenance + '; ceiling/' + ceiling.version),
        budget_ceiling=ProcurementBudget(state='KNOWN', amount=Decimal(ceiling.amount), currency=source.currency, provenance=ceiling.provenance),
        budget_version=ceiling.version, default_reference=default_ref, saved_reference=saved_ref,
        warnings=tuple(warnings), cutoff_date=request.forecast_start_date-timedelta(days=1),
        forecast_end_date=request.forecast_start_date+timedelta(days=6))


def _validation_errors(error: ValidationError, prefix: str):
    # No raw input, exception repr or user-supplied values in errors.
    errors = []
    for item in error.errors(include_input=False, include_context=False, include_url=False):
        field = prefix
        for loc in item['loc']:
            field += f'[{loc}]' if isinstance(loc, int) else ('.' if field else '') + str(loc)
        code = 'REQUEST_FIELD_INVALID' if prefix == '' else 'CONFIGURATION_INVALID'
        if item['type'] in {'too_long', 'string_too_long'}:
            code = 'RESOURCE_LIMIT_EXCEEDED'
        errors.append(PlanningFieldError(code=code, field=field or 'request', message='Invalid field for planning contract'))
    return tuple(errors)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def resolve_planning_setup(request: PlanningRequest | dict | bytes | str,
                           configuration: PlanningConfiguration | dict) -> PlanningResolutionOutcome:
    """Revalidate public boundary. Expected invalid input is typed; bugs propagate."""
    try:
        if isinstance(request, (bytes, str)):
            raw = request.encode('utf-8') if isinstance(request, str) else request
            if len(raw) > 65536:
                _reject('RESOURCE_LIMIT_EXCEEDED', 'request', 'Request exceeds 64KiB')
            try:
                request = json.loads(raw, object_pairs_hook=_json_object)
            except (ValueError, UnicodeDecodeError):
                _reject('INVALID_REQUEST', 'request', 'Request is not valid JSON')
        elif isinstance(request, dict):
            try:
                raw = json.dumps(request, ensure_ascii=False, allow_nan=False).encode('utf-8')
            except (TypeError, ValueError):
                _reject('INVALID_REQUEST', 'request', 'Request must contain JSON values')
            if len(raw) > 65536:
                _reject('RESOURCE_LIMIT_EXCEEDED', 'request', 'Request exceeds 64KiB')
        try:
            validated = PlanningRequest.model_validate(request)
        except ValidationError as error:
            return PlanningResolutionOutcome(status='INVALID', resolution=None, errors=_validation_errors(error, ''))
        try:
            source = PlanningConfiguration.model_validate(configuration)
        except ValidationError as error:
            return PlanningResolutionOutcome(status='INVALID', resolution=None, errors=_validation_errors(error, 'configuration'))
        values = _project(validated, source)
    except ResolutionRejected as error:
        return PlanningResolutionOutcome(status='INVALID', resolution=None, errors=error.errors)
    # Freeze copies including field presence. No caller containers survive Pydantic tuple capture.
    resolved = ResolvedPlanningSetup(semantics_version='planning_resolution/1', request=validated, configuration=source, **values)
    return PlanningResolutionOutcome(status='RESOLVED', resolution=resolved, errors=())
