"""Real PostgreSQL snapshot/session contention observed by the native FE."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier,Lock
from uuid import UUID

from sqlalchemy import event

from tests.integration.test_auth_public import env,login
from tests.integration.test_import_staging import imp,analyzed
from app.application.use_cases.auth import now_utc
from app.application.use_cases.import_history import ImportHistoryReads


def test_parallel_calendar_and_history_retry_fresh_authority_snapshot(imp):
    analyzed(imp)
    imp[0][2].clock=now_utc
    assert login(imp[0]).status_code==200
    token=imp[0][5].cookies.get('__Host-shelfcash_session')
    service=ImportHistoryReads(imp[2])
    barrier=Barrier(2);lock=Lock();started=[]
    def synchronize(conn,cursor,statement,parameters,context,many):
        if 'FROM auth_sessions' not in statement or 'FOR UPDATE' in statement:return
        with lock:
            wait=len(started)<2
            if wait:started.append(1)
        if wait:barrier.wait(timeout=10)
    event.listen(imp[0][1],'after_cursor_execute',synchronize)
    try:
        def read(kind):
            from datetime import date
            if kind=='calendar':return service.calendar(token,imp[1].store_id,'2026-10',None,None,None,'parallel-calendar')
            return service.history(token,imp[1].store_id,date(2026,10,10),None,None,None,50,None,'parallel-history')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(read,('calendar','history')))
        assert len(started)==2
        assert results[0].data.matched_import_count==1 and len(results[1].data.items)==1
        assert results[0].model_dump(mode='json')['meta']['warnings']==[]
        assert results[1].model_dump(mode='json')['meta']['warnings']==[]
        assert results[1].data.items[0].import_id is not None
    finally:
        event.remove(imp[0][1],'after_cursor_execute',synchronize)
