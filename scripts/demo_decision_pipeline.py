"""Internal SYNTHETIC repository-port capture -> comparison; no database writes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.use_cases.decision_pipeline import execute_operational_pipeline
from app.infrastructure.procurement_milp import NativeSearch
from scripts.decision_capture_demo_cases import synthetic_case, SyntheticSnapshotSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    request, facts = synthetic_case()
    result = execute_operational_pipeline(request, SyntheticSnapshotSource(facts), NativeSearch, lambda: facts.captured_at)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # No overwrite of previously recorded evidence.
        with args.output.open('x', encoding='utf-8') as target:
            target.write(result.model_dump_json(indent=2))
    print(json.dumps(dict(classification='SYNTHETIC mechanics only; fake repository port, native solver; no PostgreSQL evidence',
        capture=result.capture.status, pipeline=result.status, decision_readiness=result.decision_readiness,
        options=[dict(basket=[dict(packs=line.packs,term_id=str(line.term_id)) for line in o.basket],
            outlay=str(o.outlay.total.decimal_view)) for o in result.comparison.options] if result.comparison else [],
        outcomes=[dict(strategy=o.rule.strategy,execution=o.execution,target_feasibility=o.target_feasibility,proof=o.proof)
            for o in result.comparison.outcomes] if result.comparison else []), indent=2))


if __name__ == '__main__':
    main()
