"""Explicit synthetic /2 inputs; no API resolver or operational-fact defaults."""
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2, OperationalFactsV2
from scripts.decision_capture_demo_cases import synthetic_case
from scripts.procurement_v2_demo_cases import upgrade, path


def synthetic_case_v2():
    old,facts=synthetic_case()
    data=old.model_dump()
    del data['product_ids'];del data['day_start_provenance']
    # Caller/demo chooses effective rules explicitly, never an engine default.
    config=upgrade(dict(prepared={},policy=data['procurement']['policy']),[path('BASE','.8')])
    data.update(semantics_version='operational_decision/2',requirements=config['requirements'])
    data['procurement'].update(policy=config['policy'],budget_version='SYNTHETIC-budget-v1',
        budget_ceiling=data['procurement']['budget'],
        payable_fee_coverage='COMPLETE',payable_fee_coverage_provenance='SYNTHETIC complete NONE fee mode, no payable fees')
    wrapped=OperationalFactsV2(facts=facts,catalog=tuple(dict(store_id=p.store_id,product_id=p.product_id,
        name='SYNTHETIC product',selling_unit=p.selling_unit,active=True) for p in facts.products),
        ingredient_scope_ids=tuple(i.ingredient_id for i in facts.ingredients),
        supplier_term_scope=tuple(dict(store_id=t.store_id,term_id=t.id,ingredient_id=t.ingredient_id,supplier_id=t.supplier_id) for t in facts.supplier_terms),problems=())
    return OperationalDecisionInputV2.model_validate(data),wrapped


class SyntheticSnapshotSourceV2:
    """By-value test source; no PostgreSQL/isolation claims."""
    def __init__(self,facts):self.facts=facts;self.reads=0
    def read(self,request,clock):
        self.reads+=1
        return self.facts
