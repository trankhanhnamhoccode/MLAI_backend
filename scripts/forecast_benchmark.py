"""E3 explicit offline synthetic setup/freeze/smoke/run/replay/rescore. No DB/providers."""
import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from app.application.contracts.forecast_benchmark import BenchmarkDataset, BenchmarkPlan
from app.application.forecast_challenger_serialization import canonical_bytes
from app.application.use_cases.forecast_benchmark import ForecastBenchmark
from app.application.contracts.forecast_challenger import ChallengerError

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable',action='store_true')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('synthetic-inputs')
    for name in ('freeze','smoke','run'):
        command=sub.add_parser(name)
        command.add_argument('--dataset',type=Path,required=True)
        command.add_argument('--plan',type=Path,required=True)
    for name in ('replay','rescore'):
        command=sub.add_parser(name)
        command.add_argument('--experiment',required=True)
    args=parser.parse_args(argv)
    if not args.enable:
        print('{"status":"DISABLED","code":"BENCHMARK_OPT_IN_REQUIRED"}')
        return 2
    service=ForecastBenchmark(ROOT)
    try:
        if args.command=='synthetic-inputs':
            from tests.fixtures.forecast_engine.benchmark_setup import write_private_inputs
            directory=write_private_inputs(ROOT)
            print(json.dumps({'dataset':str(directory.relative_to(ROOT)/'dataset.json'),
                              'plan':str(directory.relative_to(ROOT)/'plan.json')}))
            return 0
        if args.command in ('replay','rescore'):
            report=getattr(service,args.command)(args.experiment)
        else:
            # Explicit request files only, never discover/query/copy business data.
            data=BenchmarkDataset.model_validate_json(args.dataset.read_bytes())
            plan=BenchmarkPlan.model_validate_json(args.plan.read_bytes())
            if args.command=='freeze':
                identity,_,_=service.freeze(data,plan)
                report={'status':'FROZEN','experiment_identity':identity,'dataset_digest':plan.dataset_digest,
                        'budget':plan.budget,'origin_count':4,'planned_booster_fits':24,'planned_point_cqr_fits':8}
            else:
                report=service.run(data,plan,smoke=args.command=='smoke')
        safe={k:v for k,v in report.items() if k!='metrics'}
        print(canonical_bytes(safe).decode('utf-8'))
        return 0 if report['status']!='INCOMPLETE' else 2
    except (ChallengerError,ValidationError,ValueError,OSError) as error:
        print(json.dumps({'status':'BLOCKED','code':error.code if isinstance(error,ChallengerError) else 'INVALID_DATA_OR_PLAN'}))
        return 2


if __name__=='__main__':
    sys.exit(main())
