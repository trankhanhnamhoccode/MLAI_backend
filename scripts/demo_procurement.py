"""Manual SYNTHETIC internal procurement, no DB/API/persistence or winner."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.application.contracts.procurement import ProcurementInput
from app.application.use_cases.procurement import execute_procurement
from app.infrastructure.procurement_milp import NativeSearch
from scripts.procurement_demo_cases import simple, representative


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--products',type=int,choices=(1,5,10),default=1)
    parser.add_argument('--seconds',default='30')
    parser.add_argument('--example',choices=('numeric-miss','target-met','zero-purchase'),default='numeric-miss',
        help='One-Product SYNTHETIC example; --products 5/10 use representative topology')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.products!=1:
        data=representative(args.products,args.seconds)
    elif args.example=='zero-purchase':
        data=simple(stock='10',budget='0',seconds=args.seconds)
    else:
        data=simple(budget='.3',target='.3' if args.example=='target-met' else '.3000000000000000000000000001',seconds=args.seconds)
    result=execute_procurement(ProcurementInput.model_validate(data),NativeSearch)
    text=result.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    summary=dict(classification='SYNTHETIC mechanics only; not accuracy or recommendation',execution=result.execution,
        seconds=result.elapsed_seconds,overrun=result.deadline_overrun_seconds,strategies=[])
    for row in result.strategies:
        candidate=row.best_target_met or row.best_available
        summary['strategies'].append(dict(strategy=row.rule.strategy,path=row.rule.path,execution=row.execution,
            target_met=row.target_met,proof=row.proof,reason=row.termination,
            basket=None if candidate is None else [b.model_dump(mode='json') for b in candidate.basket],
            spend=None if candidate is None else candidate.outlay.model_dump(mode='json'),
            services=[] if candidate is None else [m.model_dump(mode='json') for m in candidate.services if m.product_id is None],
            solver=[s.model_dump(mode='json') for s in row.solver]))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
