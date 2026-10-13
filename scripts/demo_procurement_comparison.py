"""Read a retained SYNTHETIC fixture and compare facts. No solver/simulator/DB calls."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.application.contracts.procurement_comparison import ProcurementComparisonInput
from app.application.contracts.procurement import ProcurementResult
from app.application.use_cases.procurement_comparison import compare_procurement
from app.application.procurement_comparison_facts import q


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/procurement_comparison_synthetic.json'
    source=ProcurementResult.model_validate_json(fixture.read_text(encoding='utf-8'))
    result=compare_procurement(ProcurementComparisonInput(procurement=source))
    labels={o.token:'/'.join(o.source_strategies) for o in result.options}
    print('SYNTHETIC offline fixed-basket fixture; NOT an optimization result or recommendation.')
    print('All searches INCOMPLETE, cost optimality UNPROVEN. Delta(A -> B) = B - A.')
    for o in result.options:
        print(f'{labels[o.token]}: purchase={q(o.outlay.purchase)}, payable fees={q(o.outlay.payable_fees)}, total={q(o.outlay.total)} {o.outlay.currency}; fee type not captured')
    for d in result.deltas:
        print(f'{labels[d.from_token]} -> {labels[d.to_token]}: spend delta={q(d.total_outlay)} {d.currency}')
        for p in d.products:
            print(f'  {p.path} Product {p.product_id}: fulfilled delta={q(p.fulfilled)} {p.unit}; lost delta={q(p.lost)}')
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(result.model_dump_json(indent=2),encoding='utf-8')


if __name__=='__main__':main()
