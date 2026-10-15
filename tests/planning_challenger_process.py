"""Spawn targets: guarded fresh-process retained read and actual owner death."""


def retained_read(url,store,run,queue):
    from app.config import Settings
    from scripts.dev import validate_reset_target
    from app.infrastructure.database.engine import create_database_engine
    from app.application.use_cases.planning_run import PlanningRunUseCases
    settings=Settings(_env_file=None,environment='test',database_url=url)
    validate_reset_target(settings)
    assert '/shelfcash_challenger_test' in url
    engine=create_database_engine(settings)
    try:
        # No serving instance, storage or inference dependency is composed here.
        record=PlanningRunUseCases(engine).read(store,run).record
        queue.put(dict(status=record.status,result_digest=record.result_digest,input_digest=record.input_digest,
            model=record.public_capture.forecast.model_type))
    finally:engine.dispose()


def hold_claim(url,store,run,clock_iso,queue,release):
    from tests.planning_process_cases import child_public_claim
    child_public_claim(url,store,run,clock_iso,queue)
    release.wait(60)
