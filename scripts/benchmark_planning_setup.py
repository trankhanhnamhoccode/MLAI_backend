"""Explicit BASE95 default on S362 synthetic topology; no DB/model-quality claim."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_decision_pipeline_v2 import benchmark_case
from scripts.decision_capture_v2_demo_cases import SyntheticSnapshotSourceV2
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations, prepare_planning_pipeline
from app.application.use_cases.decision_pipeline_v2 import execute_operational_pipeline_v2
from app.infrastructure.procurement_milp_v2 import NativeProductSearch


def declared_case(products):
    old, facts = benchmark_case(products)
    source = dict(store_id=old.store_id, currency=facts.facts.store.currency,
        timezone=facts.facts.store.timezone, read_at=facts.facts.captured_at,
        configuration_version='SYNTHETIC-default-config/1', provenance='SYNTHETIC explicit source bundle',
        consistency='UNSPECIFIED', defaults=dict(version='BASE95/1', updated_at=facts.facts.captured_at,
            requirements=dict(paths=[dict(path='BASE', min_fill_rate_percent='95', product_overrides=[])], budget_limit=None)),
        budget_ceiling=dict(amount=format(old.procurement.budget_ceiling.amount, 'f'),
            currency=facts.facts.store.currency, version=old.procurement.budget_version,
            updated_at=facts.facts.captured_at, provenance=old.procurement.budget_ceiling.provenance),
        saved=None, products=facts.catalog, policy=old.procurement.policy)
    request = dict(requirements_mode='default', forecast_start_date=facts.facts.forecast.forecast_start_date.isoformat(), default_requirements_version='BASE95/1')
    declarations = PlanningPipelineDeclarations(forecast_run_id=old.forecast_run_id,
        inventory_scope=old.inventory_scope, committed_inbound_state=old.committed_inbound_state,
        committed_inbound_provenance=old.committed_inbound_provenance,
        no_additional_orders_provenance=old.no_additional_orders_provenance,
        snapshot_policy=old.snapshot_policy,
        **old.procurement.model_dump(exclude={'policy', 'budget', 'budget_ceiling', 'budget_version'}))
    return request, source, declarations, facts


def main():
    folder = ROOT / 'runtime/verification/planning_setup/benchmark_BASE95'
    index = 1
    while folder.exists():
        index += 1; folder = ROOT / f'runtime/verification/planning_setup/benchmark_BASE95_{index}'
    folder.mkdir(parents=True, exist_ok=False)
    rows = []
    for size in (5, 10):
        request, config, declarations, facts = declared_case(size)
        print(json.dumps(dict(stage='starting', products=size, synthetic=True, required_percent='95')), flush=True)
        start = perf_counter(); resolved = resolve_planning_setup(request, config)
        resolution_seconds = perf_counter() - start
        if resolved.status != 'RESOLVED':
            raise ValueError('Explicit benchmark configuration did not resolve')
        before = perf_counter(); pipeline_input = prepare_planning_pipeline(resolved.resolution, declarations)
        bridge_seconds = perf_counter() - before
        result = execute_operational_pipeline_v2(pipeline_input, SyntheticSnapshotSourceV2(facts), NativeProductSearch, lambda:facts.facts.captured_at)
        wall = perf_counter() - start
        (folder / f'resolution_{size}p.json').write_text(resolved.model_dump_json(indent=2), encoding='utf-8')
        (folder / f'pipeline_{size}p.json').write_text(result.model_dump_json(indent=2), encoding='utf-8')
        strategies = result.procurement.strategies if result.procurement else ()
        row = dict(synthetic=True, products=size, computed_products=len(result.capture.computed_product_ids),
            resolver_seconds=resolution_seconds, bridge_seconds=bridge_seconds,
            external_total_seconds=wall, phase_timing=result.timing.model_dump(),
            effective_requirements=pipeline_input.requirements.model_dump(mode='json'),
            budget=pipeline_input.procurement.budget.model_dump(mode='json'),
            policy_seconds=str(config['policy'].computation_seconds),
            outcome=result.outcome, winner_token=result.selection.winner_token if result.selection else None,
            eligible_tokens=list(result.selection.eligible_tokens) if result.selection else [],
            strategies=[dict(strategy=s.strategy, execution=s.execution, termination=s.termination,
                customer_feasibility=s.customer_feasibility, construction_feasibility=s.construction_feasibility,
                customer_pass=s.customer_pass, construction_pass=s.construction_pass,
                candidate_present=s.candidate is not None, proof=s.proof, search_complete=s.search_complete,
                domain_size=str(s.domain_size), enumerated_vectors=s.enumerated_vectors) for s in strategies])
        rows.append(row)
        (folder / 'summary.json').write_text(json.dumps(dict(collected_at=datetime.now(timezone.utc).isoformat(),
            python=platform.python_version(), cases=rows,
            limits='Explicit BASE95 per Product; S362 synthetic topology, fake source, not customer data. No PG isolation, accuracy, savings, SLA or global-optimum claim. Cooperative deadlines may overrun.'), indent=2), encoding='utf-8')
        print(json.dumps(row), flush=True)
    print('Evidence folder: ' + str(folder), flush=True)


if __name__ == '__main__':
    main()
