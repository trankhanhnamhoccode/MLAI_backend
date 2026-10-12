"""Small synthetic S3.6.1 timing evidence, not accuracy/global-optimality proof."""
from pathlib import Path
import argparse
import json
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.application.contracts.procurement_v2 import ProcurementInputV2
from app.application.use_cases.procurement_v2 import execute_procurement_v2
from app.application.use_cases.procurement_selection import compare_procurement_v2,select_winner
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from scripts.procurement_demo_cases import representative,pid
from scripts.procurement_v2_demo_cases import upgrade,path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--permissive',action='store_true',help='Explicit synthetic 1% path minima, no override')
    options=parser.parse_args()
    folder=ROOT/('runtime/verification/procurement_v2/permissive' if options.permissive else 'runtime/verification/procurement_v2')
    folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    for products in (5,10):
        # Explicit experimental requirements, never inferred customer defaults.
        paths=([path('BASE','.01'),path('HIGH','.01')] if options.permissive else
               [path('BASE','.2',[(pid(0),'.25')]),path('HIGH','.1')])
        request=ProcurementInputV2.model_validate(upgrade(representative(products,seconds='10'),paths))
        start=time.perf_counter()
        result=execute_procurement_v2(request,NativeProductSearch)
        engine_wall=time.perf_counter()-start
        comparison=compare_procurement_v2(result)
        selected=select_winner(comparison)
        end=time.perf_counter()
        record=dict(synthetic=True,requirements=request.requirements.model_dump(mode='json'),
            products=products,ingredients=len(request.prepared.ingredients),
            recipes=len(request.prepared.recipes),lots=len(request.prepared.lots),
            offers=len(request.offers),domain_size=result.strategies[0].domain_size,
            deadline_seconds=float(request.policy.computation_seconds),engine_wall_seconds=engine_wall,
            recorded_elapsed_seconds=result.elapsed_seconds,deadline_overrun_seconds=result.deadline_overrun_seconds,
            comparison_selector_seconds=end-start-engine_wall,total_wall_seconds=end-start,
            execution=result.execution,winner_token=selected.winner_token,
            unique_exact_evaluations=result.unique_exact_evaluations,
            strategies=[dict(strategy=r.strategy,execution=r.execution,termination=r.termination,
                customer_pass=r.customer_pass,construction_pass=r.construction_pass,
                selection_kind=r.selection_kind,proof=r.proof,search_complete=r.search_complete,
                customer_feasibility=r.customer_feasibility,construction_feasibility=r.construction_feasibility,
                counts=None if r.candidate is None else r.candidate.counts,
                outlay=None if r.candidate is None else r.candidate.outlay.model_dump(mode='json'),
                solver=[s.model_dump(mode='json') for s in r.solver],diagnostic=r.diagnostic)
                for r in result.strategies])
        rows.append(record)
        # Full typed result is raw evidence including input, rejected vectors and metadata.
        (folder/f'native_{products}p.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
        (folder/f'selection_{products}p.json').write_text(selected.model_dump_json(indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True)
    summary=dict(python=platform.python_version(),cases=rows,
        limits='SYNTHETIC; certification disabled; native float statuses not exact proof. '
               'Engine deadline cooperative; comparison/selector separately timed. No DB/HTTP.')
    (folder/'benchmark_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')


if __name__=='__main__':main()
