"""Explicit E4 freeze/smoke/run/replay; owned private runtime, no DB or training."""
import argparse
from pathlib import Path
import json

from app.application.use_cases.planning_impact import PlanningImpact
from app.application.forecast_challenger_serialization import canonical_bytes


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable',action='store_true')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('freeze').add_argument('--e3-experiment',required=True)
    for name in ('smoke','run','replay'): sub.add_parser(name).add_argument('--experiment',required=True)
    args=parser.parse_args(argv)
    if not args.enable:
        print('{"status":"DISABLED","code":"PLANNING_IMPACT_OPT_IN_REQUIRED"}')
        return 2
    service=PlanningImpact(Path(__file__).resolve().parents[1])
    try:
        if args.command=='freeze': report=service.freeze(args.e3_experiment)
        elif args.command=='replay': report=service.replay(args.experiment)
        else: report=service.run(args.experiment,smoke=args.command=='smoke')
        print(canonical_bytes({k:v for k,v in report.items() if k!='results'}).decode())
        return 2 if report['status']=='INCOMPLETE' else 0
    except Exception as error:
        print(json.dumps(dict(status='BLOCKED',code='IMPACT_'+type(error).__name__)))
        return 2


if __name__=='__main__': raise SystemExit(main())
