"""Controlled actual-engine retained read before/after; no production SLA."""
from datetime import date
from pathlib import Path
from time import perf_counter
from uuid import UUID,uuid4
import json
from sqlalchemy import event
from sqlalchemy.orm import Session
from tests.integration.test_planning_public import flow,config,env,submit
from app.models import Product,Recipe,RecipeLine,SalesDaily,PlanningRun


def test_fifty_product_actual_retained_read_after_profile(flow):
    c,ingredient,_,worker=flow
    with Session(c[0][1]) as s:
        for i in range(49):
            product,recipe=uuid4(),uuid4()
            s.add(Product(id=product,store_id=c[1].store_id,name='Bounded Product '+str(i),selling_unit='cup',active=True));s.flush()
            s.add(Recipe(id=recipe,store_id=c[1].store_id,product_id=product,version=1,effective_from=date(2026,10,1),effective_to=None,yield_quantity=1,process_loss_rate=0));s.flush()
            s.add(RecipeLine(id=uuid4(),store_id=c[1].store_id,recipe_id=recipe,ingredient_id=ingredient,quantity=1,unit='ml'))
            s.add(SalesDaily(id=uuid4(),store_id=c[1].store_id,product_id=product,sales_date=date(2026,10,9),quantity=0))
        s.commit()
    response=submit(c);assert response.status_code==202,response.text
    started=perf_counter();record=worker.run_one();worker_seconds=perf_counter()-started
    assert record.status=='completed' and record.outcome=='recommendation_available',record.error_code
    queries=[]
    def count(conn,cursor,statement,parameters,context,executemany):queries.append(statement)
    engine=c[0][5].app.state.planning_public.engine
    event.listen(engine,'before_cursor_execute',count);started=perf_counter()
    try:read=c[0][5].get(response.headers['Location'])
    finally:event.remove(engine,'before_cursor_execute',count)
    elapsed=perf_counter()-started
    assert read.status_code==200,read.text
    assert len(queries)<=12 and len(read.content)<1000000
    assert read.json()['data']['scope']['computed_count']==50
    out=Path('runtime/s410');out.mkdir(parents=True,exist_ok=True)
    cold_queries=len(queries);queries.clear()
    event.listen(engine,'before_cursor_execute',count);started=perf_counter()
    try:warm=c[0][5].get(response.headers['Location'])
    finally:event.remove(engine,'before_cursor_execute',count)
    warm_seconds=perf_counter()-started
    assert warm.status_code==200 and warm.json()==read.json() and len(queries)<=12
    (out/'retained_read_http_after.json').write_text(json.dumps(dict(active_products=50,ingredients=1,offers=0,lots=0,
        cold_queries=cold_queries,warm_queries=len(queries),bytes=len(read.content),cold_http_seconds=elapsed,warm_http_seconds=warm_seconds,worker_seconds=worker_seconds)),encoding='utf-8')
    (out/'c03_after.json').write_text(read.text,encoding='utf-8')
    with Session(engine) as s:
        row=s.get(PlanningRun,UUID(record.run_id.hex))
        (out/'retained_50_after_input.json').write_text(json.dumps(dict(record_json=row.record_json,record_digest=row.record_digest,revision=row.revision)),encoding='utf-8')
