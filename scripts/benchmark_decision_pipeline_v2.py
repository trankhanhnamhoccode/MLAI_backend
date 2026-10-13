"""Full internal /2 synthetic timing; no DB/HTTP/accuracy or optimality claim."""
import json
import platform
from pathlib import Path
import sys
import time
from datetime import timedelta
from uuid import UUID

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.application.contracts.decision_capture import OperationalFacts
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2, OperationalFactsV2
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.decision_pipeline_v2 import execute_operational_pipeline_v2
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from scripts.procurement_demo_cases import representative
from scripts.procurement_v2_demo_cases import upgrade,path
from scripts.decision_capture_v2_demo_cases import SyntheticSnapshotSourceV2


def benchmark_case(products):
    data=upgrade(representative(products,seconds='10'),[path('BASE','.01'),path('HIGH','.01')])
    p=data['prepared'];r=p['request'];start=r['cutoff_date']
    # Explicit synthetic retained input; not a real trained-model forecast run.
    retained=PreparedForecastInput(request=dict(store_id=r['store_id'],product_ids=r['product_ids'],cutoff_date=start,history_start_date=start),timezone=p['timezone'],products=tuple(dict(product_id=x['product_id'],selling_unit=x['selling_unit']) for x in p['products']),observations=(),forecast_dates=tuple(start+timedelta(days=n) for n in range(1,8)))
    digest=serialize_prepared(retained).digest
    forecast=dict(id=r['forecast_run_id'],store_id=r['store_id'],status='COMPLETED',training_start_date=start,training_end_date=start,forecast_start_date=start+timedelta(days=1),forecast_end_date=start+timedelta(days=7),input_fingerprint=digest,model_type=p['forecast']['model_type'],model_version=p['forecast']['model_version'],artifact_key=None,completed_at=p['inventory_as_of']-timedelta(hours=1),predictions=tuple(dict(id=UUID(int=5000+n),store_id=r['store_id'],forecast_run_id=r['forecast_run_id'],**{k:v for k,v in point.items() if k!='unit'}) for n,point in enumerate(p['forecast']['predictions'])),retained=retained,retained_digest=digest,execution=None)
    facts=OperationalFacts(captured_at=p['inventory_as_of'],store=dict(id=r['store_id'],timezone=p['timezone'],currency=p['currency']),forecast=forecast,products=p['products'],ingredients=p['ingredients'],recipes=p['recipes'],lots=p['lots'],supplier_terms=p['supplier_terms'],constraints=p['constraints'],source_times=())
    wrapped=OperationalFactsV2(facts=facts,catalog=tuple(dict(store_id=r['store_id'],product_id=x.product_id,name=x.sku or 'SYNTHETIC',selling_unit=x.selling_unit,active=True) for x in facts.products),ingredient_scope_ids=tuple(i.ingredient_id for i in facts.ingredients),supplier_term_scope=tuple(dict(store_id=t.store_id,term_id=t.id,ingredient_id=t.ingredient_id,supplier_id=t.supplier_id) for t in facts.supplier_terms),problems=())
    request=OperationalDecisionInputV2(semantics_version='operational_decision/2',store_id=r['store_id'],forecast_run_id=r['forecast_run_id'],cutoff_date=start,requirements=data['requirements'],inventory_scope=tuple(dict(ingredient_id=i.ingredient_id,state='COMPLETE_CURRENT_LOTS',provenance='SYNTHETIC complete current stock') for i in facts.ingredients),committed_inbound_state='CONFIRMED_NONE',committed_inbound_provenance='SYNTHETIC explicit none',no_additional_orders_provenance='SYNTHETIC one order',snapshot_policy=p['policy'],procurement=dict(policy=data['policy'],offers=data['offers'],budget=data['budget'],budget_ceiling=data['budget'],budget_version='SYNTHETIC-explicit-budget/1',supplier_fees=data['supplier_fees'],capacities=data['capacities'],supplier_limits=data['supplier_limits'],capacity_state='DECLARED' if data['capacities'] else 'EXPLICIT_NOT_CONFIGURED',supplier_limit_state='DECLARED' if data['supplier_limits'] else 'EXPLICIT_NOT_CONFIGURED',provenance='SYNTHETIC explicit configuration',payable_fee_coverage='COMPLETE',payable_fee_coverage_provenance='SYNTHETIC full generic payable fees, no additional fees'))
    return request,wrapped


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-name',choices=('benchmark','benchmark_optimized','benchmark_final'),default='benchmark_final')
    args=parser.parse_args()
    folder=ROOT/'runtime/verification/decision_pipeline'/args.output_name;folder.mkdir(parents=True,exist_ok=True);cases=[]
    for size in (5,10):
        request,facts=benchmark_case(size)
        print(json.dumps(dict(stage='starting',products=size,synthetic=True)),flush=True)
        start=time.perf_counter()
        result=execute_operational_pipeline_v2(request,SyntheticSnapshotSourceV2(facts),NativeProductSearch,lambda:facts.facts.captured_at)
        wall=time.perf_counter()-start
        (folder/f'pipeline_{size}p.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
        row=dict(synthetic=True,products=size,computed_products=len(result.capture.computed_product_ids),ingredients=len(result.capture.prepared.ingredients),recipes=len(result.capture.prepared.recipes),lots=len(result.capture.prepared.lots),offers=len(result.procurement.input.offers),domain_size=str(result.procurement.strategies[0].domain_size),input_requirements=request.requirements.model_dump(mode='json'),outcome=result.outcome,winner_token=result.selection.winner_token,phase_timing=result.timing.model_dump(),external_wall_seconds=wall,proof=[dict(strategy=s.strategy,execution=s.execution,proof=s.proof,customer_pass=s.customer_pass,construction_pass=s.construction_pass,search_complete=s.search_complete,domain_size=str(s.domain_size)) for s in result.procurement.strategies])
        cases.append(row)
        (folder/'summary.json').write_text(json.dumps(dict(python=platform.python_version(),cases=cases,limits='SYNTHETIC source; no PostgreSQL/HTTP, no accuracy or real savings. Cooperative engine deadline only; full revalidation measured; proof remains captured finite domain.'),indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)


if __name__=='__main__':main()
