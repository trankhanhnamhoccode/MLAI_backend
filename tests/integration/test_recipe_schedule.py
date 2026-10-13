"""CAT12 real HTTP + PostgreSQL acceptance; guarded shelfcash_test only."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env, setup, login
from app.models import Product, Ingredient, Recipe, RecipeLine, Store, StoreMembership
from app.models.auth import MembershipGrant
from app.models.recipe_schedule import RecipeScheduleChange, RecipeScheduleRequestReceipt
from app.application.use_cases.recipe_schedule import RecipeSchedule
from app.application.use_cases.public_reads import PublicReads
from app.application.contracts.auth import AuthError


@pytest.fixture
def calendar(env):
    receipt = setup(env); wire = login(env).json()["data"]
    env[5].app.state.recipe_schedule = RecipeSchedule(env[2])
    env[5].app.state.public_reads = PublicReads(env[2])
    product, ingredient, recipe, line = (uuid4() for _ in range(4))
    with Session(env[1]) as s:
        s.add(Product(id=product,store_id=receipt.store_id,name="Synthetic latte",selling_unit="cup",active=False))
        s.add(Ingredient(id=ingredient,store_id=receipt.store_id,name="Synthetic milk",base_unit="ml",active=True))
        s.flush()
        s.add(Recipe(id=recipe,store_id=receipt.store_id,product_id=product,version=1,
            effective_from=date(2026,10,1),effective_to=None,yield_quantity=1,process_loss_rate=0))
        s.flush()
        s.add(RecipeLine(id=line,store_id=receipt.store_id,recipe_id=recipe,ingredient_id=ingredient,quantity=180,unit="ml"))
        s.commit()
    headers={"Origin":"https://fe.example.test","X-CSRF-Token":wire["session"]["csrf_token"]}
    return env,receipt,product,ingredient,recipe,line,headers


def path(c):
    return f"/api/v1/stores/{c[1].store_id}/products/{c[2]}/recipe-schedule"


def timeline(c, query=""):
    r=c[0][5].get(path(c)+query); assert r.status_code==200,r.text
    return r.json()["data"]


def proposal(c, *, start="2026-10-11", close="2026-10-10"):
    return dict(phase="preview",new_recipes=[dict(client_reference="next",yield_quantity="2",yield_unit="cup",
        process_loss_rate="0.1",ingredients=[dict(ingredient_id=str(c[3]),quantity="300",unit="ml")])],
        operations=[dict(kind="SET_PERIOD",recipe_ref=dict(recipe_id=str(c[4])),effective_from="2026-10-01",effective_to=close),
            dict(kind="SET_PERIOD",recipe_ref=dict(new_recipe_reference="next"),effective_from=start,effective_to=None)],
        reason="Reviewed recipe applies from tomorrow")


def change(c, body, match, key=None):
    return c[0][5].post(path(c)+"/changes",json=body,headers={**c[6],"If-Match":'"'+match+'"',"Idempotency-Key":key or str(uuid4())})


def preview(c, body=None):
    version=timeline(c)["schedule_version"]
    r=change(c,body or proposal(c),version); assert r.status_code==200,r.text
    return r.json()["data"]


def commit_body(p, **changes):
    return {**dict(phase="commit",change_id=p["change_id"],preview_digest=p["preview_digest"],confirm=True,
                  acknowledged_warning_codes=p["required_warning_acknowledgements"]), **changes}


def test_switch_is_atomic_inclusive_with_retained_reads_no_compute_and_no_product_activation(calendar,monkeypatch):
    c=calendar; p=preview(c)
    assert p["status"]=="preview_ready" and p["changed_ranges"]==[dict(from_date="2026-10-11",to_date=None)]
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(Recipe))==1
        assert s.get(Recipe,c[4]).effective_to is None
    key=str(uuid4());body=commit_body(p);r=change(c,body,p["schedule_version"],key)
    assert r.status_code==200,r.text
    receipt=r.json()["data"]
    assert receipt["changed"] and receipt["updated_resources"]==dict(menu=True,recipes=True,inventory=False,sales=False,forecast=False,retained_runs=False)
    assert change(c,body,p["schedule_version"],key).json()["data"]==receipt
    assert change(c,{**body,"preview_digest":"different"},p["schedule_version"],key).json()["error"]["code"]=="IDEMPOTENCY_KEY_REUSED"
    from app.repositories.recipe import RecipeRepository
    with Session(c[0][1]) as fresh:
        repo=RecipeRepository(fresh)
        assert repo.get_active_recipe(c[1].store_id,c[2],date(2026,10,9)).id==c[4]
        assert repo.get_active_recipe(c[1].store_id,c[2],date(2026,10,10)).id==c[4]
        assert repo.get_active_recipe(c[1].store_id,c[2],date(2026,10,11)).version==2
        assert fresh.get(Product,c[2]).active is False
        assert fresh.scalar(select(func.count()).select_from(RecipeLine))==2
        retained=fresh.get(RecipeScheduleChange,UUID(p["change_id"]))
        assert retained.audit_json["before"]==p["before"] and retained.audit_json["after"]==p["after"]
        assert retained.audit_json["reason"]==proposal(c)["reason"]
    def forbidden(*a,**kw): pytest.fail("GET recomputed recipe proposal")
    import app.application.use_cases.recipe_schedule as module
    monkeypatch.setattr(module,"propose",forbidden)
    retained=c[0][5].get(path(c)+"/changes/"+p["change_id"])
    assert retained.status_code==200 and retained.json()["data"]["preview"]==p
    assert retained.json()["data"]["receipt"]==receipt
    timeline(c)


def test_overlap_and_today_are_blocked_without_silent_closure(calendar):
    c=calendar;b=proposal(c);b["operations"]=b["operations"][1:]
    p=preview(c,b)
    assert p["status"]=="blocked" and "RECIPE_PERIOD_OVERLAP" in {n["code"] for n in p["blockers"]}
    assert change(c,commit_body(p),p["schedule_version"]).json()["error"]["code"]=="PREVIEW_BLOCKED"
    p=preview(c,proposal(c,start="2026-10-10",close="2026-10-09"))
    assert "HISTORY_CHANGE_NOT_ALLOWED" in {n["code"] for n in p["blockers"]}
    with Session(c[0][1]) as s:
        assert s.get(Recipe,c[4]).effective_to is None
        assert s.scalar(select(func.count()).select_from(Recipe))==1


def test_gap_requires_exact_ack_and_withdraw_retains_content(calendar):
    c=calendar;p=preview(c,proposal(c,start="2026-10-13"))
    assert p["required_warning_acknowledgements"]==["RECIPE_GAP_WARNING"]
    gap=p["warnings"][0]["details"]["affected_ranges"]
    assert gap==[dict(from_date="2026-10-11",to_date="2026-10-12")]
    assert change(c,commit_body(p,acknowledged_warning_codes=[]),p["schedule_version"]).status_code==422
    result=change(c,commit_body(p),p["schedule_version"]);assert result.status_code==200,result.text
    future=result.json()["data"]["created_recipe_ids"][0]
    withdrawn=preview(c,dict(phase="preview",new_recipes=[],operations=[dict(kind="WITHDRAW_FUTURE",recipe_ref=dict(recipe_id=future))],reason="Withdraw future version"))
    assert withdrawn["required_warning_acknowledgements"]==["RECIPE_GAP_WARNING"]
    assert change(c,commit_body(withdrawn),withdrawn["schedule_version"]).status_code==200
    unassigned=timeline(c,"?status=unassigned")["items"]
    assert len(unassigned)==1 and unassigned[0]["content"]["recipe_id"]==future and unassigned[0]["assignment"] is None
    from app.repositories.recipe import RecipeRepository
    with Session(c[0][1]) as s:
        assert s.get(Recipe,UUID(future)).assigned is False
        assert len(RecipeRepository(s).list_recipe_versions(c[1].store_id,c[2],assigned_only=True))==1
        assert RecipeRepository(s).get_active_recipe(c[1].store_id,c[2],date(2026,10,13)) is None


@pytest.mark.parametrize("field,value,code",[("yield_unit","bowl","INVALID_UNIT"),("yield_quantity","0","VALIDATION_ERROR"),
    ("process_loss_rate","1","VALIDATION_ERROR"),("ingredients",[],"VALIDATION_ERROR")])
def test_invalid_new_content_does_not_mutate(calendar,field,value,code):
    c=calendar;b=proposal(c);b["new_recipes"][0][field]=value
    r=change(c,b,timeline(c)["schedule_version"])
    assert r.status_code==422 and r.json()["error"]["code"]==code
    with Session(c[0][1]) as s: assert s.scalar(select(func.count()).select_from(RecipeScheduleChange))==0


def test_foreign_ingredient_unit_and_unknown_recipe_references(calendar):
    c=calendar;b=proposal(c);b["new_recipes"][0]["ingredients"][0]["ingredient_id"]=str(uuid4())
    assert change(c,b,timeline(c)["schedule_version"]).status_code==404
    b=proposal(c);b["new_recipes"][0]["ingredients"][0]["unit"]="l"
    assert change(c,b,timeline(c)["schedule_version"]).json()["error"]["code"]=="INVALID_UNIT"
    b=proposal(c);b["operations"][0]["recipe_ref"]["recipe_id"]=str(uuid4())
    assert change(c,b,timeline(c)["schedule_version"]).status_code==404


def test_catalog_stale_midnight_current_rights_and_store_isolation(calendar):
    c=calendar;p=preview(c)
    with Session(c[0][1]) as s:s.get(Ingredient,c[3]).active=False;s.commit()
    assert change(c,commit_body(p),p["schedule_version"]).json()["error"]["code"]=="PREVIEW_STALE"
    p=preview(c)
    c[0][4][0]+=timedelta(days=1)
    wire=login(c[0]).json()["data"];c[6]["X-CSRF-Token"]=wire["session"]["csrf_token"]
    assert change(c,commit_body(p),p["schedule_version"]).json()["error"]["code"]=="RECIPE_DATE_POLICY_CHANGED"
    with Session(c[0][1]) as s:
        membership=s.scalar(select(StoreMembership));membership.role="STAFF"
        s.add_all(MembershipGrant(membership_id=membership.id,permission=k) for k in ("menu.read","ingredient.read","recipe.read","recipe.create_version"));s.commit()
    assert change(c,proposal(c),timeline(c)["schedule_version"]).status_code==403
    assert c[0][5].get(path(c).replace(str(c[1].store_id),str(uuid4()))).status_code==404


def test_preview_and_commit_retry_normalization_and_noop(calendar):
    c=calendar;version=timeline(c)["schedule_version"];key=str(uuid4());b=proposal(c)
    p=change(c,b,version,key).json()["data"]
    b["new_recipes"][0]["yield_quantity"]="2.00"
    assert change(c,b,version,key).json()["data"]==p
    no=preview(c,dict(phase="preview",new_recipes=[],operations=[],reason="Calendar unchanged"))
    r=change(c,commit_body(no),no["schedule_version"])
    assert r.status_code==200,r.text
    value=r.json()["data"]
    assert not value["changed"] and value["created_recipe_ids"]==[] and value["affected_recipe_ids"]==[]
    assert value["schedule_version_after"]==no["schedule_version"]
    assert timeline(c)["schedule_version"]==version


def test_two_real_pg_concurrent_calendar_commits_have_single_winner(calendar):
    c=calendar;p1=preview(c);p2=preview(c)
    token=c[0][5].cookies.get("__Host-shelfcash_session");svc=c[0][5].app.state.recipe_schedule
    from app.application.contracts.recipe_schedule import CommitRequest
    def run(p):
        try: return svc.change(token,c[1].store_id,c[2],CommitRequest(**commit_body(p)),str(uuid4()),'"'+p["schedule_version"]+'"',c[6]["X-CSRF-Token"],"race")
        except AuthError as e: return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,(p1,p2)))
    assert sum(not isinstance(r,str) for r in results)==1
    assert "RECIPE_SCHEDULE_REVISION_CONFLICT" in results
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(Recipe))==2
        assert len([r for r in s.scalars(select(RecipeScheduleChange)) if r.receipt_json])==1


def test_failure_after_real_writer_flush_rolls_back_closed_period_content_lines_and_receipt(calendar,monkeypatch):
    c=calendar;p=preview(c)
    from app.application.use_cases.recipe import RecipeUseCases
    original=RecipeUseCases.create_in_transaction
    def fault(self,*args,**kwargs):
        original(self,*args,**kwargs)
        raise RuntimeError("Synthetic failure after actual header/line SQL")
    monkeypatch.setattr(RecipeUseCases,"create_in_transaction",fault)
    assert change(c,commit_body(p),p["schedule_version"]).status_code==503
    with Session(c[0][1]) as fresh:
        assert fresh.get(Recipe,c[4]).effective_to is None and fresh.get(Recipe,c[4]).assigned
        assert fresh.scalar(select(func.count()).select_from(Recipe))==1
        assert fresh.scalar(select(func.count()).select_from(RecipeLine))==1
        assert fresh.get(RecipeScheduleChange,UUID(p["change_id"])).receipt_json is None
        assert fresh.scalar(select(func.count()).select_from(RecipeScheduleRequestReceipt))==1 # preview only


def test_lost_commit_ack_proves_durable_receipt_without_second_mutation(calendar,monkeypatch):
    c=calendar;p=preview(c);old=Session.commit;lost=[]
    def lose(s):
        committing=any(isinstance(r,RecipeScheduleRequestReceipt) and r.phase=="commit" for r in s.new)
        old(s)
        if committing and not lost:lost.append(True);raise RuntimeError("Synthetic response loss after DB commit")
    monkeypatch.setattr(Session,"commit",lose)
    r=change(c,commit_body(p),p["schedule_version"])
    assert r.status_code==200,r.text
    assert lost
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(Recipe))==2
        assert s.scalar(select(func.count()).select_from(RecipeLine))==2


def test_pagination_pins_calendar_catalog_and_filter_and_etag(calendar):
    c=calendar;p=preview(c);assert change(c,commit_body(p),p["schedule_version"]).status_code==200
    first=c[0][5].get(path(c)+"?status=in_effect,scheduled&limit=1")
    assert first.status_code==200 and first.headers["ETag"]=='"'+first.json()["data"]["schedule_version"]+'"'
    page=first.json()["meta"]["pagination"];assert page["total_count"]==2 and page["next_cursor"]
    cursor=page["next_cursor"]
    second=c[0][5].get(path(c),params=dict(status="in_effect,scheduled",limit=1,cursor=cursor))
    assert second.status_code==200 and len(second.json()["data"]["items"])==1
    with Session(c[0][1]) as s:s.get(Ingredient,c[3]).name="Changed label";s.commit()
    stale=c[0][5].get(path(c),params=dict(status="in_effect,scheduled",limit=1,cursor=cursor))
    assert stale.status_code==409 and stale.json()["error"]["code"]=="LIST_VERSION_CHANGED"


def test_staff_manage_without_create_can_edit_future_assignment_but_revocation_blocks_replay(calendar):
    c=calendar;p=preview(c);r=change(c,commit_body(p),p["schedule_version"])
    future=r.json()["data"]["created_recipe_ids"][0]
    with Session(c[0][1]) as s:
        m=s.scalar(select(StoreMembership));m.role="STAFF"
        s.add_all(MembershipGrant(membership_id=m.id,permission=k) for k in ("menu.read","recipe.read","ingredient.read","recipe.manage_effectivity"));s.commit()
    version=timeline(c)["schedule_version"]
    assert change(c,proposal(c),version).status_code==403
    p=preview(c,dict(phase="preview",new_recipes=[],operations=[dict(kind="SET_PERIOD",recipe_ref=dict(recipe_id=future),
        effective_from="2026-10-12",effective_to=None)],reason="Move future recipe explicitly"))
    assert p["changed_ranges"]==[dict(from_date="2026-10-11",to_date="2026-10-11")]
    key=str(uuid4());body=commit_body(p)
    assert change(c,body,p["schedule_version"],key).status_code==200
    with Session(c[0][1]) as s:
        m=s.scalar(select(StoreMembership));s.delete(s.get(MembershipGrant,(m.id,"recipe.manage_effectivity")));s.commit()
    assert change(c,body,p["schedule_version"],key).status_code==403
    assert c[0][5].get(path(c)+"/changes/"+p["change_id"]).status_code==200


def test_midnight_uses_store_timezone_and_same_key_retained_replay_survives_day_rollover(calendar):
    c=calendar
    c[0][4][0]=c[0][4][0].replace(hour=16,minute=59) # 23:59 Asia/Ho_Chi_Minh
    wire=login(c[0]).json()["data"];c[6]["X-CSRF-Token"]=wire["session"]["csrf_token"]
    p=preview(c);key=str(uuid4());body=commit_body(p)
    r=change(c,body,p["schedule_version"],key);assert r.status_code==200,r.text
    c[0][4][0]+=timedelta(minutes=2)
    assert timeline(c)["as_of_date"]=="2026-10-11"
    assert change(c,body,p["schedule_version"],key).json()["data"]==r.json()["data"]
    p2=preview(c,dict(phase="preview",new_recipes=[],operations=[],reason="No change next day"))
    assert p2["minimum_change_date"]=="2026-10-12"


def test_history_past_and_current_withdraw_block_and_get_is_canonical_read_only(calendar,monkeypatch):
    c=calendar
    p=preview(c,dict(phase="preview",new_recipes=[],operations=[dict(kind="WITHDRAW_FUTURE",recipe_ref=dict(recipe_id=str(c[4])))],reason="Invalid current withdrawal"))
    assert p["status"]=="blocked"
    from sqlalchemy import event
    statements=[]
    def capture(conn,cursor,statement,params,context,executemany):statements.append(statement)
    event.listen(c[0][1],"before_cursor_execute",capture)
    try:
        timeline(c)
        assert c[0][5].get(path(c)+"/changes/"+p["change_id"]).status_code==200
    finally:event.remove(c[0][1],"before_cursor_execute",capture)
    canonical=("recipes","recipe_lines","recipe_schedule_changes","recipe_schedule_request_receipts")
    assert not any(sql.lstrip().upper().startswith(("UPDATE","INSERT","DELETE")) and any(table in sql for table in canonical) for sql in statements)
    assert c[0][5].request("GET",path(c),json={}).status_code==422


def test_recipe_change_does_not_rewrite_captured_forecast_or_historical_decision(calendar):
    c=calendar
    from app.models import ForecastRun, DecisionRun
    from tests.integration.test_forecast_decision_persistence import forecast_values, decision_values
    ids=dict(store=c[1].store_id,ingredient=c[3])
    fc,decision=uuid4(),uuid4()
    captured=dict(recipe=dict(recipe_id=str(c[4]),effective_from="2026-10-01",effective_to=None,
        quantity="180",yield_quantity="1",process_loss_rate="0"))
    with Session(c[0][1]) as s:
        s.add(ForecastRun(id=fc,**forecast_values(ids)));s.flush()
        s.add(DecisionRun(id=decision,**decision_values(ids,fc,input_snapshot_json=captured)));s.commit()
        before_fc=s.get(ForecastRun,fc).metrics_json
        before_package=s.get(DecisionRun,decision).decision_package_json
    p=preview(c);assert change(c,commit_body(p),p["schedule_version"]).status_code==200
    with Session(c[0][1]) as fresh:
        assert fresh.get(ForecastRun,fc).metrics_json==before_fc
        old=fresh.get(DecisionRun,decision)
        assert old.input_snapshot_json==captured and old.decision_package_json==before_package
        assert fresh.get(Recipe,c[4]).yield_quantity==1
        assert fresh.get(RecipeLine,c[5]).quantity==180


def test_import_recipe_and_editor_share_real_pg_fence_and_version_allocation(imp):
    # Existing current recipe is already explicitly closed; Import never closes it.
    from tests.integration.test_import_staging import analyzed, approved, previewed, csv_source
    from tests.integration.test_import_classification import confirm
    from tests.integration.test_import_commit import commit as import_commit
    from app.models.import_staging import ImportJob
    ingredient,recipe,line=(uuid4() for _ in range(3))
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=ingredient,store_id=imp[1].store_id,name="Race milk",base_unit="ml",active=True));s.flush()
        s.add(Recipe(id=recipe,store_id=imp[1].store_id,product_id=imp[4],version=1,
            effective_from=date(2026,10,1),effective_to=date(2026,10,10),yield_quantity=1,process_loss_rate=0));s.flush()
        s.add(RecipeLine(id=line,store_id=imp[1].store_id,recipe_id=recipe,ingredient_id=ingredient,quantity=180,unit="ml"));s.commit()
    imp[0][5].app.state.recipe_schedule=RecipeSchedule(imp[0][2])
    c=(imp[0],imp[1],imp[4],ingredient,recipe,line,imp[3])
    source=dict(product_id=str(imp[4]),version=2,effective_from="2026-10-12",effective_to=None,
        yield_quantity="1",yield_unit="cup",quantity_basis="WHOLE_BATCH",process_loss_rate="0",ingredient_id=str(ingredient),quantity="200",unit="ml")
    ident=analyzed(imp,csv_source("recipes",[source]));approved(imp,ident,report="recipe-race")
    read=previewed(imp,ident);confirmed=confirm(imp,ident,read);assert confirmed.status_code==200,confirmed.text
    accepted=import_commit(imp,ident,read,confirmed.json()["data"]["import_revision"]);assert accepted.status_code==202,accepted.text
    p=preview(c)
    token=imp[0][5].cookies.get("__Host-shelfcash_session")
    from app.application.contracts.recipe_schedule import CommitRequest
    def edit():
        try:return c[0][5].app.state.recipe_schedule.change(token,c[1].store_id,c[2],CommitRequest(**commit_body(p)),str(uuid4()),
            '"'+p["schedule_version"]+'"',c[6]["X-CSRF-Token"],"import-editor-race")
        except AuthError as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker=pool.submit(imp[2].run_one);editor=pool.submit(edit)
        worker.result(timeout=15);outcome=editor.result(timeout=15)
    with Session(c[0][1]) as fresh:
        versions=fresh.scalars(select(Recipe).where(Recipe.product_id==c[2])).all()
        assert len(versions)==2 and sorted(r.version for r in versions)==[1,2]
        job=fresh.get(ImportJob,UUID(accepted.json()["data"]["job_id"]))
        if isinstance(outcome,str):
            assert outcome=="RECIPE_SCHEDULE_REVISION_CONFLICT" and job.status=="completed"
        else:
            assert job.status=="failed" and job.error_json["code"]=="PREVIEW_STALE"


# Import fixture only used by the one cross-workflow race; it shares the same guarded DB.
from tests.integration.test_import_staging import imp
