"""Public projection retains scopes and historical notification bytes."""
from uuid import UUID
from app.application.contracts.readiness import Issue,IssueDetails
from app.application.contracts.planning_public import PlanningNotification,PlanningNotificationDetails
from app.application.readiness_evaluation import ordered_issues,recipe_dependencies


def test_warning_dedup_preserves_distinct_products_and_dates():
    def warning(ident):
        return Issue(code='PRODUCT_HISTORY_MISSING',source='sales',scope='PRODUCT',entity_id=UUID(int=ident),affected_dates=(),details=IssueDetails())
    a,b=warning(1),warning(2)
    assert ordered_issues((b,a,b))==ordered_issues((a,b))
    assert len(ordered_issues((b,a,b)))==2


def test_notification_extensions_preserve_legacy_retained_serialization():
    old='{"code":"KNOWN","message":"Retained","details":{"field":"supplier_term"}}'
    assert PlanningNotification.model_validate_json(old).model_dump_json()==old
    assert PlanningNotificationDetails().model_dump_json()=='{}'


def test_unknown_graph_attribution_remains_global_readiness_failure():
    from datetime import date
    snapshot={'ingredients':[], 'recipes':[dict(id='r',product_id='p',assigned=True,effective_from='2026-10-01',effective_to=None,
        yield_quantity='1',process_loss_rate='0')], 'recipe_lines':[dict(recipe_id='r',ingredient_id='unknown',unit='ml',quantity='1')]}
    assert recipe_dependencies(snapshot,{'id':'p'},(date(2026,10,10),))==((),('SOURCE_FAILURE_SCOPE_UNKNOWN',),())
