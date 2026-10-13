"""N6/N8 real guarded PostgreSQL/public HTTP acceptance; synthetic sources."""
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env, setup, login
from app.application.use_cases.public_reads import PublicReads
from app.application.use_cases.stock_writes import StockWrites
from app.models import Ingredient, InventoryLot, InventoryMovement
from app.models.operational_import import InventoryReceiptRecord, InventoryAudit, InventoryThreshold

@pytest.fixture
def stock(env):
    receipt=setup(env); wire=login(env).json()["data"]
    reads=PublicReads(env[2]);env[5].app.state.public_reads=reads
    env[5].app.state.stock_writes=StockWrites(env[2],reads)
    ingredient=uuid4()
    with Session(env[1]) as s:
        s.add(Ingredient(id=ingredient,store_id=receipt.store_id,name="Synthetic milk",base_unit="l",expiry_tracking=False,active=True));s.commit()
    headers={"Origin":"https://fe.example.test","X-CSRF-Token":wire["session"]["csrf_token"],"Idempotency-Key":str(uuid4())}
    return env,receipt,ingredient,headers

def detail(stock):
    env,receipt,ingredient,_=stock
    response=env[5].get(f"/api/v1/stores/{receipt.store_id}/inventory/{ingredient}")
    assert response.status_code==200,response.text
    return response.json()

def request(stock,origin="OPENING_STOCK",identity="lot-1",quantity="12"):
    value=detail(stock)
    return dict(origin=origin,receipt_identity=dict(source_system_key="synthetic-opening",source_record_id=identity),
        ingredient_id=str(stock[2]),supplier_id=None,lot_code="LOT",quantity=quantity,unit="l",received_date=None,
        expiry_date=None,unit_cost=None,currency="VND",observed_at=stock[0][4][0].isoformat(),reason="Physical stock recorded",
        expected_inventory_version=value["meta"]["data_version"])

def receive(stock,body,headers=None):
    return stock[0][5].post(f"/api/v1/stores/{stock[1].store_id}/inventory/receipts",json=body,headers=headers or stock[3])

def test_opening_and_actual_receipt_keep_distinct_movements_identity_and_read_origins(stock):
    body=request(stock);first=receive(stock,body)
    assert first.status_code==201,first.text
    value=first.json()["data"]
    assert value["movement"]["kind"]=="count_correction" and value["lot"]["received_date"] is None
    assert value["lot"]["origin"]=="OPENING_STOCK"
    assert receive(stock,body).status_code==200
    assert receive(stock,body,{**stock[3],"Idempotency-Key":str(uuid4())}).json()["data"]==value
    changed={**body,"quantity":"13"}
    assert receive(stock,changed).json()["error"]["code"]=="IDEMPOTENCY_KEY_REUSED"
    assert receive(stock,changed,{**stock[3],"Idempotency-Key":str(uuid4())}).json()["error"]["code"]=="RECEIPT_IDENTITY_CONFLICT"
    second=receive(stock,request(stock,"ACTUAL_RECEIPT","lot-2","5"),{**stock[3],"Idempotency-Key":str(uuid4())})
    assert second.status_code==201,second.text
    assert second.json()["data"]["movement"]["kind"]=="receipt"
    current=detail(stock)
    assert current["data"]["on_hand_quantity"]=="17" and current["data"]["stock_completeness"]=="UNKNOWN"
    assert {lot["origin"] for lot in current["data"]["lots"]}=={"OPENING_STOCK","ACTUAL_RECEIPT"}
    movement=stock[0][5].get(f"/api/v1/stores/{stock[1].store_id}/inventory/{stock[2]}/movements").json()["data"]["items"]
    assert len(movement)==2 and all(row["actor_user_id"]==str(stock[1].user_id) for row in movement)
    with Session(stock[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(InventoryReceiptRecord))==2
        assert s.scalar(select(func.count()).select_from(InventoryAudit))==2
        assert s.scalar(select(func.sum(InventoryLot.on_hand_quantity)))==17

def test_threshold_cas_null_zero_noop_and_inventory_revision(stock):
    initial=detail(stock);path=f"/api/v1/stores/{stock[1].store_id}/inventory/{stock[2]}/threshold"
    body=dict(minimum_usable_quantity="0",unit="l",reason="Owner chooses threshold")
    headers={**stock[3],"If-Match":'"'+initial["data"]["threshold_version"]+'"'}
    response=stock[0][5].put(path,json=body,headers=headers)
    assert response.status_code==200,response.text
    result=response.json()["data"]
    after=detail(stock)
    assert after["data"]["threshold_version"]==result["version"]
    assert after["data"]["low_stock_assessment"]["threshold"]=="0"
    assert after["meta"]["data_version"]!=initial["meta"]["data_version"]
    assert stock[0][5].put(path,json=body,headers=headers).json()["data"]==result
    assert stock[0][5].put(path,json=body,headers={**headers,"Idempotency-Key":str(uuid4())}).status_code==412
    fresh={**headers,"If-Match":'"'+result["version"]+'"',"Idempotency-Key":str(uuid4())}
    assert stock[0][5].put(path,json=body,headers=fresh).json()["data"]["version"]==result["version"]
    cleared=stock[0][5].put(path,json={**body,"minimum_usable_quantity":None},headers={**fresh,"Idempotency-Key":str(uuid4())})
    assert cleared.status_code==200 and cleared.json()["data"]["minimum_usable_quantity"] is None
    assert detail(stock)["data"]["low_stock_assessment"]["status"]=="unknown"

@pytest.mark.parametrize("change",[{"quantity":"0"},{"unit":"ml"},{"currency":"USD"},{"observed_at":"2099-01-01T00:00:00Z"},{"received_date":"2099-01-01"},{"ingredient_id":str(UUID(int=99))}])
def test_invalid_receipts_leave_no_canonical_rows(stock,change):
    response=receive(stock,{**request(stock),**change})
    assert response.status_code in (404,409,422),response.text
    with Session(stock[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(InventoryLot))==0
        assert s.scalar(select(func.count()).select_from(InventoryMovement))==0

def test_concurrent_same_identity_creates_one_durable_lot(stock):
    body=request(stock)
    token=stock[0][5].cookies.get("shelfcash_session")
    # Use the actual authenticated token from TestClient's cookie jar.
    if token is None:
        token=next(c.value for c in stock[0][5].cookies.jar)
    svc=stock[0][5].app.state.stock_writes
    from app.application.contracts.stock_writes import StockReceiptRequest
    def run(_):return svc.receive(token,stock[1].store_id,StockReceiptRequest(**body),str(uuid4()),stock[3]["X-CSRF-Token"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(run,range(2)))
    assert sum(replay for _,replay in outcomes)==1
    assert outcomes[0][0].receipt_id==outcomes[1][0].receipt_id
    with Session(stock[0][1]) as s:assert s.scalar(select(func.count()).select_from(InventoryLot))==1

def as_staff(stock,permissions):
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    with Session(stock[0][1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==stock[1].store_id));member.role="STAFF"
        s.add_all(MembershipGrant(membership_id=member.id,permission=p) for p in permissions);s.commit()

def test_staff_cannot_change_threshold_and_known_cost_requires_current_cost_right(stock):
    as_staff(stock,["inventory.read","ingredient.read","inventory.receive"])
    body=request(stock);body["unit_cost"]="0"
    assert receive(stock,body).status_code==403
    body["unit_cost"]=None
    assert receive(stock,body).status_code==201
    initial=detail(stock)
    response=stock[0][5].put(f"/api/v1/stores/{stock[1].store_id}/inventory/{stock[2]}/threshold",
        json=dict(minimum_usable_quantity="1",unit="l",reason="Not Owner"),
        headers={**stock[3],"Idempotency-Key":str(uuid4()),"If-Match":'"'+initial["data"]["threshold_version"]+'"'})
    assert response.status_code==403
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    with Session(stock[0][1]) as s:
        member=s.scalar(select(StoreMembership));s.delete(s.get(MembershipGrant,(member.id,"inventory.receive")));s.commit()
    assert receive(stock,body).status_code==403

def test_stale_receipt_snapshot_foreign_scope_and_tracked_expiry_fail_without_write(stock):
    old=request(stock);assert receive(stock,old).status_code==201
    stale={**old,"receipt_identity":dict(source_system_key="synthetic-opening",source_record_id="lot-2")}
    stale_response=receive(stock,stale,{**stock[3],"Idempotency-Key":str(uuid4())})
    assert stale_response.status_code==409 and stale_response.json()["error"]["code"]=="INVENTORY_VERSION_CONFLICT"
    with Session(stock[0][1]) as s:
        s.get(Ingredient,stock[2]).expiry_tracking=True;s.commit()
    assert receive(stock,request(stock,identity="missing-expiry"),{**stock[3],"Idempotency-Key":str(uuid4())}).status_code==422
    assert stock[0][5].post(f"/api/v1/stores/{uuid4()}/inventory/receipts",json=old,headers=stock[3]).status_code==404
    with Session(stock[0][1]) as s:assert s.scalar(select(func.count()).select_from(InventoryLot))==1

def test_receipt_ack_loss_proves_durable_state_and_replay_does_not_read_live_balance(stock,monkeypatch):
    original=Session.commit;lost=[]
    from app.models.operational_import import StockRequestReceipt
    def commit(session):
        success=any(isinstance(r,StockRequestReceipt) for r in session.new)
        original(session)
        if success and not lost:lost.append(True);raise RuntimeError("Synthetic committed ACK loss")
    monkeypatch.setattr(Session,"commit",commit)
    body=request(stock);response=receive(stock,body)
    assert response.status_code==200,response.text
    assert lost
    with Session(stock[0][1]) as s:
        from app.application.use_cases.inventory import InventoryUseCases
        from app.application.contracts.inventory import AdjustInventoryInput
        lot=s.scalar(select(InventoryLot));ident=lot.id;s.rollback()
        InventoryUseCases(s).adjust(AdjustInventoryInput(store_id=stock[1].store_id,lot_id=ident,quantity_delta=-2,
            unit="l",movement_type="COUNT_CORRECTION",occurred_at=stock[0][4][0],note="Synthetic later count"))
    assert receive(stock,body).json()["data"]==response.json()["data"]
    with Session(stock[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1
        assert s.scalar(select(func.count()).select_from(InventoryMovement))==2

def test_retained_receipt_masks_cost_availability_after_current_rights_change(stock):
    body=request(stock);response=receive(stock,body)
    assert response.status_code==201 and response.json()["data"]["lot"]["cost"]["availability"]=="unknown"
    as_staff(stock,["inventory.read","ingredient.read","inventory.receive"])
    replay=receive(stock,body)
    assert replay.status_code==200,replay.text
    assert replay.json()["data"]["receipt_id"]==response.json()["data"]["receipt_id"]
    assert replay.json()["data"]["lot"]["cost"]==dict(availability="forbidden",unit_cost=None,currency="VND")
    from sqlalchemy import event
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(stock[0][1],"before_cursor_execute",capture)
    try:
        detail(stock)
        response=stock[0][5].get(f"/api/v1/stores/{stock[1].store_id}/inventory/{stock[2]}/movements")
        assert response.status_code==200,response.text
    finally:event.remove(stock[0][1],"before_cursor_execute",capture)
    assert all("unit_cost" not in sql.lower() for sql in statements if sql.lstrip().upper().startswith("SELECT"))
