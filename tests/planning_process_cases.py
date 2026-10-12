"""Windows-spawn entry points for real guarded Planning/PDF process tests.

Keep bootstrap free of pytest fixtures and app composition. Child targets retain
the same service calls, local test guards and transaction/process behavior.
"""

def child_claim_export(url,ident,now,queue,release):
    from datetime import datetime
    from app.config import Settings
    from scripts.dev import validate_reset_target
    from app.infrastructure.database.engine import create_database_engine
    from app.application.use_cases.auth import AuthUseCases
    from app.application.use_cases.planning_public import PublicPlanning
    from app.application.use_cases.planning_exports import PlanningExports
    settings=Settings(_env_file=None,environment='test',database_url=url);validate_reset_target(settings)
    assert settings.database_url.endswith('/shelfcash_test')
    engine=create_database_engine(settings)
    try:
        service=PlanningExports(PublicPlanning(AuthUseCases(engine,clock=lambda:datetime.fromisoformat(now)),None),None,None)
        record=service.claim(ident);queue.put(record.claim.model_dump(mode='json'));release.wait(20)
    finally:engine.dispose()



def child_public_claim(url,store,run,clock_iso,queue):
    from app.application.use_cases.planning_worker import PlanningExecution
    from datetime import datetime
    from sqlalchemy.engine import make_url
    from sqlalchemy import text
    from app.config import Settings
    from scripts.dev import validate_reset_target
    from app.infrastructure.database.engine import create_database_engine
    from app.application.use_cases.auth import AuthUseCases
    from app.application.use_cases.planning_run import PlanningRunUseCases
    parsed=make_url(url)
    assert parsed.database=='shelfcash_test' and parsed.host in {'127.0.0.1','localhost','::1'}
    settings=Settings(_env_file=None,environment='test',database_url=url);validate_reset_target(settings)
    engine=create_database_engine(settings)
    try:
        with engine.connect() as conn:assert conn.scalar(text('select current_database()'))=='shelfcash_test'
        clock=lambda:datetime.fromisoformat(clock_iso)
        execution=PlanningExecution(AuthUseCases(engine,clock=clock),None)
        record=execution.runs.read(store,run).record
        cases=PlanningRunUseCases(engine,clock=clock,transition_fence=lambda s:execution.authority(s,record))
        claimed=cases.claim(store,run)
        queue.put(claimed.claim.model_dump(mode='json'))
    finally:engine.dispose()



def child_claim(url,store,run_id,queue):
    """A real short-lived owner claims on guarded PostgreSQL, then exits."""
    from sqlalchemy import text
    from app.infrastructure.database.engine import create_database_engine
    from app.application.use_cases.planning_run import PlanningRunUseCases
    from sqlalchemy.engine import make_url
    from app.config import Settings
    from scripts.dev import validate_reset_target
    parsed=make_url(url)
    assert parsed.database=='shelfcash_test' and parsed.host in {'127.0.0.1','localhost','::1'}
    settings=Settings(_env_file=None,environment='test',database_url=url)
    validate_reset_target(settings)
    engine=create_database_engine(settings)
    try:
        with engine.connect() as c:assert c.scalar(text('select current_database()'))=='shelfcash_test'
        record=PlanningRunUseCases(engine).claim(store,run_id)
        queue.put(record.claim.model_dump(mode='json'))
    finally:engine.dispose()
