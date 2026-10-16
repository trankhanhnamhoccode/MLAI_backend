"""Cross-phase integrity checks; no source/DB, solver or live facts."""


def pipeline_outcome(capture,bom,procurement,selection):
    if capture.status=='DATA_BLOCKED':return 'CAPTURE_BLOCKED'
    if capture.status=='NO_COMPUTABLE_PRODUCTS':return 'NO_COMPUTABLE_PRODUCTS'
    if bom is not None and bom.status=='ARITHMETIC_BLOCKED':return 'NUMERIC_UNSUPPORTED'
    if procurement is None:return 'COMPUTATION_BLOCKED'
    if procurement.execution=='ERROR':return 'EXECUTION_ERROR'
    if procurement.execution=='NUMERIC_UNSUPPORTED':return 'NUMERIC_UNSUPPORTED'
    if procurement.execution=='BLOCKED':return 'COMPUTATION_BLOCKED'
    return 'RECOMMENDATION_AVAILABLE' if selection and selection.winner_token else 'NO_ELIGIBLE_CANDIDATE'


def validate_pipeline_v2(result, *, retained=False):
    c=result.capture
    if c.status!='CAPTURED':
        if any(x is not None for x in (result.bom,result.procurement,result.comparison,result.selection)):
            raise ValueError('Blocked/empty capture cannot fabricate engine output')
    if result.bom is not None and result.bom.prepared!=c.prepared:
        raise ValueError('BOM must retain exact captured snapshot')
    if result.bom is not None:
        # BOM's historical output contract checks shape/status, not every
        # contribution. The new /2 aggregate boundary reconciles actual values
        # against retained input without weakening or rewriting that /1 contract.
        if retained:
            from app.application.retained_decision_validation import validate_bom
            validate_bom(result.bom)
        else:
            from app.application.use_cases.bom import expand_bom
            if result.bom!=expand_bom(c.prepared):
                raise ValueError('Pipeline BOM quantities/coverage/issues differ from captured input')
    if result.procurement is not None:
        if result.procurement.input!=c.procurement_input or result.bom is None or result.bom.status!='COMPLETE':
            raise ValueError('Engine must use captured effective envelope after complete BOM')
    if result.comparison is not None and result.comparison.source!=result.procurement:
        raise ValueError('Comparison must retain actual procurement source')
    if result.selection is not None and result.selection.comparison!=result.comparison:
        raise ValueError('Selector must use actual comparison')
    if result.procurement is not None and (result.comparison is None or result.selection is None):
        raise ValueError('Validated engine output needs comparison and selector')
    if result.outcome!=pipeline_outcome(c,result.bom,result.procurement,result.selection):
        raise ValueError('Pipeline outcome cannot hide capture/numeric/error/search/eligibility facts')
    if c.status=='CAPTURED' and result.bom is None and not any(p.kind=='DATA_BLOCKER' for p in result.problems):
        raise ValueError('Skipped computation needs explicit blocker')
    if any(p not in result.problems for p in c.problems):
        raise ValueError('Capture issues/exclusions cannot disappear at pipeline boundary')
    t=result.timing
    if t.total_seconds<sum((t.capture_preparation_seconds,t.bom_seconds,t.engine_seconds,t.comparison_seconds,t.selector_seconds,t.output_revalidation_seconds)):
        raise ValueError('Total timing cannot hide phases')
