"""Versioned synthetic seed and real HTTP/native-worker S4.11 acceptance.

Bootstrap catalog uses existing typed application commands. Import history, sales,
configuration, invitations, stock and retained outputs use legitimate flows only.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import secrets
import time
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contracts.provisioning import ProvisionStoreCommand, VerifiedAccountCommand, IssueCredentialCommand
from app.application.contracts.model_serving import OperatorConfigurationCommand
from app.application.use_cases.provisioning import AssistedProvisioning
from app.application.use_cases.model_serving import ModelServingOperator
from app.application.use_cases.auth import now_utc
from app.infrastructure.database.engine import create_database_engine
from scripts.integration import PRIVATE, connected_guard, settings, write_json

ORIGIN = "http://localhost:5173"
URL = "http://localhost:18001"
VERSION = "s411-demo/1"


class WireFailure(Exception):
    """Only safe status/error codes are included; never request bodies or secrets."""


class Client:
    def __init__(self):
        self.http = httpx.Client(base_url=URL, timeout=120, headers={"Origin": ORIGIN})
        self.csrf = None

    def request(self, method, path, *, expected=(200,), body=None, match=None, key=None, **kwargs):
        headers = {"X-Request-ID": "s411-" + str(uuid4())}
        if method != "GET":
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
            headers["Idempotency-Key"] = key or str(uuid4())
        if match:
            headers["If-Match"] = '"' + match.strip('"') + '"'
        headers.update(kwargs.pop("headers", {}))
        r = self.http.request(method, path, json=body, headers=headers, **kwargs)
        if r.status_code not in expected:
            code = "NON_JSON_RESPONSE"
            try:
                code = (r.json().get("error") or {}).get("code", "UNEXPECTED_RESPONSE")
            except ValueError:
                pass
            raise WireFailure(f"{method} {path.split('?')[0]} HTTP {r.status_code} {code}")
        return r

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, body=None, **kwargs):
        return self.request("POST", path, body=body, **kwargs)

    def login(self, account):
        r = self.post("/api/v1/auth/login", {"email": account["email"], "password": account["password"]})
        self.csrf = r.json()["data"]["session"]["csrf_token"]
        assert "HttpOnly" in r.headers["set-cookie"] and "SameSite=lax" in r.headers["set-cookie"]
        assert r.headers["access-control-allow-origin"] == ORIGIN
        assert r.headers["access-control-allow-credentials"] == "true"
        return r

    def job(self, identifier):
        deadline = time.monotonic() + 180
        polls = 0
        while time.monotonic() < deadline:
            r = self.get("/api/v1/jobs/" + identifier)
            value = r.json()["data"]
            polls += 1
            if value["status"] in ("completed", "failed"):
                if value["status"] != "completed":
                    raise WireFailure("J01 terminal " + (value.get("error") or {}).get("code", "FAILED"))
                return value, polls
            time.sleep(2)
        raise WireFailure("J01 polling timeout UNVERIFIED")


def csv_bytes(domain, rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    keys = tuple(rows[0])
    writer.writerow([domain + "." + key for key in keys])
    for row in rows:
        writer.writerow([json.dumps(row[k]) if isinstance(row[k], (dict, list)) else
                         str(row[k]).lower() if isinstance(row[k], bool) else
                         str(row[k]) if row[k] is not None else "" for k in keys])
    return out.getvalue().encode()


def bootstrap_accounts(engine, config):
    state_path = PRIVATE / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    accounts_path = PRIVATE / "accounts.json"
    accounts = json.loads(accounts_path.read_text(encoding="utf-8")) if accounts_path.exists() else {}
    provision = AssistedProvisioning(engine, config)
    wire = Client()
    for name in ("owner", "staff", "other_owner"):
        if name in accounts:
            continue
        email = name + "@s411.example.test"
        values = dict(request_reference=VERSION + "/" + name, evidence_reference="Synthetic local holder; S4.11 operator fixture",
                      email=email, display_name="S4.11 " + name)
        cls = VerifiedAccountCommand if name == "staff" else ProvisionStoreCommand
        if name != "staff":
            values.update(store_name="S4.11 demo" if name == "owner" else "S4.11 isolated second Store")
        receipt = provision.provision(cls(**values), config.auth_operator_id, config.auth_operator_key)
        if receipt.store_id:
            state["store_allowlist"] = sorted(set(state["store_allowlist"] + [str(receipt.store_id)]))
            write_json(state_path, state)
        delivered = []
        delivery = provision.issue(IssueCredentialCommand(user_id=receipt.user_id, purpose="SETUP", verified_email=email,
                                    request_reference=str(uuid4()), evidence_reference="Synthetic holder private in-memory delivery"),
                                   config.auth_operator_id, config.auth_operator_key,
                                   lambda address, token: delivered.append((address, token.get_secret_value())))
        assert delivery.status == "delivered" and delivered[0][0] == email
        password = "S411!" + secrets.token_urlsafe(24)
        wire.post("/api/v1/auth/credentials/complete", {"token": delivered[0][1], "password": password})
        accounts[name] = dict(email=email, password=password, user_id=str(receipt.user_id),
                              store_id=str(receipt.store_id) if receipt.store_id else None)
        write_json(accounts_path, accounts)
    wire.http.close()
    return accounts


def seed():
    config = settings()
    engine = create_database_engine(config)
    try:
        connected_guard(engine)
        accounts = bootstrap_accounts(engine, config)
        owner = Client()
        owner.login(accounts["owner"])
        store = accounts["owner"]["store_id"]
        base = "/api/v1/stores/" + store
        manifest_path = PRIVATE / "dataset.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
            manifest = dict(version=VERSION, anchor_date=day.isoformat(), store_id=store, products=[], ingredient_id=None,
                            supplier_id=None, lots=[], phase="accounts")
            write_json(manifest_path, manifest)
        day = datetime.fromisoformat(manifest["anchor_date"]).date()
        sid = UUID(store)
        from app.application.contracts.catalog import CreateIngredientInput, CreateProductInput
        from app.application.contracts.recipe import CreateRecipeVersionInput
        from app.application.use_cases.catalog import IngredientUseCases, ProductUseCases
        from app.application.use_cases.recipe import RecipeUseCases
        from app.application.contracts import import_domains as domains
        from app.application.use_cases.operational_configuration import OperationalConfiguration
        from app.models import Product, Ingredient, Recipe

        if manifest["ingredient_id"] is None:
            with Session(engine) as s:
                existing = s.scalar(select(Ingredient).where(Ingredient.store_id == sid, Ingredient.sku == "S411-MILK"))
                if existing:
                    iid = existing.id
                else:
                    s.rollback()
                    iid = IngredientUseCases(s).create(CreateIngredientInput(store_id=sid, name="Sữa demo", base_unit="ml", sku="S411-MILK", expiry_tracking=True)).id
            manifest["ingredient_id"] = str(iid)
            write_json(manifest_path, manifest)
        iid = UUID(manifest["ingredient_id"])
        for number in range(len(manifest["products"]), 5):
            with Session(engine) as s:
                existing = s.scalar(select(Product).where(Product.store_id == sid, Product.sku == f"S411-P{number}"))
                if existing:
                    pid = existing.id
                else:
                    s.rollback()
                    pid = ProductUseCases(s).create(CreateProductInput(store_id=sid, name=f"Cà phê demo {number+1}", selling_unit="cup", sku=f"S411-P{number}", price="25000")).id
            manifest["products"].append(str(pid))
            write_json(manifest_path, manifest)
        for pid in manifest["products"]:
            with Session(engine) as s:
                if s.scalar(select(Recipe.id).where(Recipe.product_id == UUID(pid))) is None:
                    s.rollback()
                    RecipeUseCases(s).create_version(CreateRecipeVersionInput(store_id=sid, product_id=UUID(pid), version=1,
                        effective_from=day-timedelta(days=60), effective_to=None, yield_quantity="1", process_loss_rate="0",
                        lines=[dict(ingredient_id=iid, quantity="10", unit="ml")]))
        if manifest["supplier_id"] is None:
            from app.models import Supplier
            with Session(engine) as s:
                existing = s.scalar(select(Supplier).where(Supplier.store_id == sid))
                supplier = existing.id if existing else uuid4()
                if existing is None:
                    OperationalConfiguration(s,sid).supplier(domains.SupplierSource(source_supplier_key="S411-SUP",name="Nhà cung cấp demo",active=True),supplier,"S411",{"evidence":"Synthetic supplier baseline"},create=True)
                    s.commit()
            manifest["supplier_id"] = str(supplier)
            write_json(manifest_path, manifest)
        supplier = manifest["supplier_id"]
        from app.models.model_serving import ModelServingConfiguration
        from app.models.planning_configuration import PlanningDefault
        operator = ModelServingOperator(engine, config, now_utc)
        for action, cls in (("BASELINE", ModelServingConfiguration), ("DEFAULT_BASE95", PlanningDefault)):
            with Session(engine) as s:
                existing = s.get(cls,sid)
                version = existing.version if existing else None
            result = operator.configure(OperatorConfigurationCommand(store_id=sid,action=action,expected_version=version,
                                        evidence_reference=VERSION + ": explicit synthetic demo policy approved by operator"),
                                        config.auth_operator_id,config.auth_operator_key)
            if action == "DEFAULT_BASE95":
                manifest["default_version"] = result
        budget = owner.request("PUT",base+"/planning-budget",body={"amount":"1000000"},headers={"If-None-Match":"*"},expected=(201,412))
        for index in range(len(manifest["lots"]),2):
            detail = owner.get(base+"/inventory/"+str(iid)).json()
            body = dict(origin="OPENING_STOCK",receipt_identity=dict(source_system_key="S411",source_record_id=f"opening-{index}"),
                        ingredient_id=str(iid),supplier_id=supplier,lot_code=f"S411-L{index}",quantity="100" if index==0 else "5",unit="ml",
                        received_date=(day-timedelta(days=10)).isoformat(),expiry_date=(day+timedelta(days=10) if index==0 else day-timedelta(days=1)).isoformat(),
                        unit_cost=None,currency="VND",observed_at=now_utc().isoformat(),reason="Synthetic physically observed opening stock",
                        expected_inventory_version=detail["meta"]["data_version"])
            result = owner.post(base+"/inventory/receipts",body,expected=(200,201)).json()["data"]
            manifest["lots"].append(result["lot"]["lot_id"] if "lot_id" in result["lot"] else result["lot"]["id"])
            write_json(manifest_path,manifest)
        # Legitimate Owner offer -> internal delivery -> authenticated Staff consent.
        from app.models import StoreMembership
        with Session(engine) as s:
            member = s.scalar(select(StoreMembership).where(StoreMembership.user_id==UUID(accounts["staff"]["user_id"]),StoreMembership.store_id==sid))
        if member is None:
            offer = owner.post(base+"/staff-invitations",dict(email=accounts["staff"]["email"],grants=["menu.read"],
                                permission_catalog_version="permissions-v2",reason="Synthetic consent and denial case"),expected=(201,)).json()["data"]
            from app.application.use_cases.invitation_delivery import InvitationDispatcher
            delivered=[]
            result=InvitationDispatcher(engine,config,now_utc).dispatch(config.auth_operator_id,config.auth_operator_key,
                lambda address,ident,token:delivered.append((address,str(ident),token.get_secret_value())))
            assert result["delivered"]==1 and delivered[0][0]==accounts["staff"]["email"]
            staff=Client();staff.login(accounts["staff"])
            staff.post("/api/v1/staff-invitations/"+offer["invitation"]["invitation_id"]+"/accept",
                {"token":delivered[0][2],"accept":True},match=offer["invitation"]["version"],expected=(201,))
            staff.http.close()
        # Configuration/declarations and sales are committed only through import below.
        if manifest.get("phase") != "committed":
            rows=[]
            for index,pid in enumerate(manifest["products"]):
                for offset in range(14,0,-1):
                    rows.append(dict(product_id=pid,sales_date=(day-timedelta(days=offset)).isoformat(),quantity=str(0 if index==0 and offset==14 else 5+index),unit="cup",business_report_key=VERSION+"-sales"))
            declarations=[dict(source_declaration_key="inventory",declaration=dict(kind="INVENTORY",ingredient_id=str(iid),state="COMPLETE_CURRENT_LOTS",
                observed_at=now_utc().isoformat(),covered_lot_ids=manifest["lots"],evidence_reference="Synthetic complete physical observation including expired lot")),
                dict(source_declaration_key="sales",declaration=dict(kind="SALES_COVERAGE",product_ids=manifest["products"],from_date=(day-timedelta(days=14)).isoformat(),to_date=(day-timedelta(days=1)).isoformat(),state="COMPLETE",evidence_reference="Synthetic full 14-day report with an explicit zero")),
                dict(source_declaration_key="context",declaration=dict(kind="PROCUREMENT_CONTEXT",effective_from=day.isoformat(),effective_to=None,
                    committed_inbound_state="CONFIRMED_NONE",no_additional_orders_state="CONFIRMED_NONE",capacity_state="EXPLICIT_NOT_CONFIGURED",capacities=[],supplier_limit_state="EXPLICIT_NOT_CONFIGURED",supplier_limits=[],evidence_reference="Synthetic explicit context, no inferred defaults"))]
            sources=[("sales.csv",csv_bytes("sales",rows)),
                ("terms.csv",csv_bytes("supplier_terms",[dict(source_term_key="S411-TERM",supplier_id=supplier,ingredient_id=str(iid),effective_from=(day-timedelta(days=30)).isoformat(),effective_to=None,unit="ml",pack_size_base_quantity="100",pack_cost="1000",currency="VND",minimum_order_packs=1,lead_time_days=0,shelf_life_days=10,active=True,maximum_order_base_quantity="100000")])),
                ("fees.csv",csv_bytes("payable_fees",[dict(source_fee_key="S411-NONE",scope="STORE_PROCUREMENT",effective_from=day.isoformat(),effective_to=None,mode="NONE",coverage="COMPLETE",currency="VND",components=[],covered_source_term_keys=["S411-TERM"],covered_source_supplier_keys=["S411-SUP"],evidence_reference="Synthetic explicit complete no additional fees",reason="Reviewed synthetic fee schedule")])),
                ("declarations.csv",csv_bytes("scope_declarations",declarations))]
            # Versioned source corrections create a new batch; sealed files stay immutable.
            # observed_at is intentionally an actual fresh observation, not a fixed clock.
            old_sources=manifest.get("source_sha256",{})
            if "import_id" in manifest and old_sources.get("fees.csv") != hashlib.sha256(sources[2][1]).hexdigest():
                manifest.setdefault("superseded_import_ids",[]).append(manifest.pop("import_id"))
                write_json(manifest_path,manifest)
            if "import_id" not in manifest:
                def created(ident):
                    manifest["import_id"]=ident
                    manifest["source_sha256"]={name:hashlib.sha256(content).hexdigest() for name,content in sources}
                    write_json(manifest_path,manifest)
                analyze(owner,store,day,sources,on_created=created)
            ident=manifest["import_id"]
            complete_import(owner,store,ident,engine,expected_sales=0)
            manifest["phase"]="committed"
            manifest["expected"]={"products":5,"sales_daily":70,"inventory_lots":2,"supplier_terms":1,"fees":1,"declarations":3,"staff_grants":["menu.read"]}
            write_json(manifest_path,manifest)
        state=json.loads((PRIVATE/"state.json").read_text(encoding="utf-8"));state["dataset"]=VERSION;write_json(PRIVATE/"state.json",state)
        print("Synthetic dataset v1 seeded through application/HTTP flows: 5 Products, 70 sales, 2 lots; no credentials printed.")
        owner.http.close()
    finally:
        engine.dispose()


def analyze(client,store,day,sources,on_created=None):
    draft=client.post(f"/api/v1/stores/{store}/imports",{"data_date":day.isoformat()},expected=(201,)).json()["data"]
    ident=draft["import_id"]
    if on_created:
        on_created(ident)
    uploaded=client.post(f"/api/v1/imports/{ident}/files",files=[("files[]",(name,content,"text/csv")) for name,content in sources],
        data={"client_file_ids[]":[str(uuid4()) for _ in sources]}).json()["data"]
    refreshed=client.get(f"/api/v1/imports/{ident}").json()["data"]
    assert refreshed["quota"]["accepted_file_count"]==len(sources)
    response=client.post(f"/api/v1/imports/{ident}/analyze",dict(file_set_version=uploaded["file_set_version"],
        accepted_file_ids=[x["file_id"] for x in uploaded["items"] if x["upload_status"]=="uploaded"],acknowledged_rejected_client_file_ids=[]),
        match=uploaded["import_revision"],expected=(202,))
    client.job(response.json()["data"]["job_id"])
    return ident


def complete_import(client,store,ident,engine,expected_sales=None):
    base="/api/v1/imports/"+ident
    if client.get(base).json()["data"].get("completion_available"):
        return client.get(base+"/completion").json()["data"]
    issues=client.get(base+"/mappings?review_only=false&limit=100").json()["data"]["items"]
    for item in issues:
        if item.get("ignored") or item.get("resolution_origin")=="APPROVED_PROFILE":
            continue
        summary=client.get(base+"/mapping-summary?include_profile_details=true").json()["data"]
        if item["issue_type"]=="classification":
            sheet=next(x for x in summary["sheets"] if x["sheet_id"]==item["sheet_id"])
            body={"resolution":{"kind":"sheet_type","sheet_type":sheet["selected_type"],"reason":"Explicit synthetic sheet review"}}
        elif item["issue_type"]=="source_context":
            body={"resolution":dict(kind="source_context",source_system_key="S411",report_type="s411-demo",evidence_reference="Synthetic operator known fixture",sales_semantics="daily_total",inventory_semantics="lot_stock_count")}
        elif item["issue_type"]=="column" and item["target_field"]:
            body={"target_field":item["target_field"]}
        else:
            raise WireFailure("Manual review unresolved: "+item["code"])
        client.request("PATCH",base+"/mappings/"+item["mapping_id"],body=body,match=summary["mapping_revision"])
    while True:
        summary=client.get(base+"/mapping-summary?include_profile_details=true").json()["data"]
        remaining=[p for p in summary["profile_proposals"] if p["active_version"] is None]
        if not remaining:
            break
        p=remaining[0]
        client.post(f"/api/v1/stores/{store}/mapping-profiles/{p['profile_id']}/decisions",dict(decision="approve_activate",
                    proposal_revision=p["proposal_revision"],expected_active_version=None,reason="Explicit Owner reusable profile approval"),match=p["lifecycle_revision"])
    current=client.get(base).json()["data"]
    response=client.post(base+"/process",dict(phase="preview",mapping_revision=summary["mapping_revision"]),match=current["import_revision"],expected=(202,))
    client.job(response.json()["data"]["job_id"])
    read=client.get(base+"?include_preview=true").json()["data"]
    preview=read["preview"]["summary"]
    if preview["blockers"]:
        raise WireFailure("Preview blockers: "+",".join(x["code"] for x in preview["blockers"]))
    from app.models import SalesDaily
    if expected_sales is not None:
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(SalesDaily).where(SalesDaily.store_id==UUID(store)))==expected_sales
    summary=client.get(base+"/mapping-summary").json()["data"]
    confirmation=client.post(base+"/process",dict(phase="confirm_review",preview_id=preview["preview_id"],preview_digest=preview["digest"],mapping_revision=summary["mapping_revision"],confirm=True,reason="Synthetic per-import confirmation"),match=read["import_revision"]).json()["data"]
    key=str(uuid4())
    body=dict(phase="commit",preview_id=preview["preview_id"],preview_digest=preview["digest"],confirm=True,resolutions=[])
    # Pure insert / NO_OP deliberately has no reason (CA-002).
    committed=client.post(base+"/process",body,match=confirmation["import_revision"],key=key,expected=(202,))
    client.job(committed.json()["data"]["job_id"])
    result=client.get(base+"/completion").json()["data"]
    replay=client.post(base+"/process",body,match=confirmation["import_revision"],key=key,expected=(202,))
    assert replay.json()["data"]==committed.json()["data"]
    return result


def verify():
    config=settings();engine=create_database_engine(config)
    try:
        connected_guard(engine)
        accounts=json.loads((PRIVATE/"accounts.json").read_text(encoding="utf-8"))
        manifest=json.loads((PRIVATE/"dataset.json").read_text(encoding="utf-8"))
        assert manifest["phase"]=="committed"
        owner=Client();owner.login(accounts["owner"])
        base="/api/v1/stores/"+manifest["store_id"]
        evidence={"dataset":VERSION,"gates":{},"started_at":now_utc().isoformat()}
        def passed(name,value=True):
            evidence["gates"][name]=value;write_json(PRIVATE/"e2e.json",evidence);print(name+": PASS",flush=True)
        owner.get(base);passed("login_store_cookie_cors")
        from app.models import SalesDaily,Product,InventoryLot,PlanningRun
        from app.models.operational_import import PayableFeeRecord,ScopeDeclarationRecord
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(Product).where(Product.store_id==UUID(manifest["store_id"])))==5
            assert fresh.scalar(select(func.count()).select_from(SalesDaily).where(SalesDaily.store_id==UUID(manifest["store_id"])))==70
            assert fresh.scalar(select(func.count()).select_from(SalesDaily).where(SalesDaily.quantity==0))==1
            assert len(fresh.scalars(select(InventoryLot)).all())==2
            assert fresh.scalar(select(func.count()).select_from(PayableFeeRecord))==1
            assert fresh.scalar(select(func.count()).select_from(ScopeDeclarationRecord))==3
        passed("fresh_session_committed_seed")
        readiness=owner.get(base+"/readiness?actions=planning").json()["data"]
        action=readiness["actions"][0]
        if not action["can_execute"]:
            raise WireFailure("Readiness: "+",".join(x["code"] for x in action["blockers"]))
        assert readiness["scope_estimate"]["estimated_computable_product_count"]==5
        passed("readiness_known_five_products")
        key=str(uuid4());body=dict(requirements_mode="default",default_requirements_version=manifest["default_version"],forecast_start_date=manifest["anchor_date"])
        accepted=owner.post(base+"/procurement-plans",body,key=key,expected=(202,));run=accepted.json()["data"]["run_id"]
        assert owner.post(base+"/procurement-plans",body,key=key,expected=(202,)).json()["data"]==accepted.json()["data"]
        path="/api/v1/procurement-plans/"+run;deadline=time.monotonic()+180;polls=0
        while time.monotonic()<deadline:
            retained=owner.get(path);data=retained.json()["data"];polls+=1
            if data["status"] in ("completed","failed"):
                break
            time.sleep(2)
        assert data["status"]=="completed" and data["result"]["winner_option_id"]
        assert data["forecast"]["model_type"]=="historical_quantile_baseline"
        passed("C02_C03_real_worker_baseline",{"run_id":run,"polls":polls})
        timing={}
        for name,p in (("C04",path+"/ingredients"),("C05",path+"/ingredients/"+manifest["ingredient_id"]),("C08",path+"/explanation")):
            start=time.monotonic();r=owner.get(p);timing[name]=round(time.monotonic()-start,3)
            assert r.json()["data"] is not None
        passed("C04_C05_C08_retained_inspection",timing)
        owner.get(base+"/procurement-plans")
        day=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        calendar=owner.get(base+"/imports/calendar?month="+day.strftime("%Y-%m")).json()["data"]
        assert calendar["matched_import_count"]>=1
        history=owner.get(base+"/imports?import_date="+day.isoformat()).json()["data"]
        assert history["items"]
        passed("N9_H01_H02_retained_history")
        exports=owner.post(path+"/exports",dict(format="pdf",option_id=None,locale="vi"),expected=(202,)).json()["data"]
        job,polls=owner.job(exports["job_id"])
        pdf=owner.get(job["result"]["download_url"])
        sha=hashlib.sha256(pdf.content).hexdigest()
        assert pdf.content.startswith(b"%PDF-") and sha==job["result"]["sha256"]
        assert pdf.headers["etag"]=='"'+sha+'"' and int(pdf.headers["content-length"])==len(pdf.content)
        assert pdf.headers["cache-control"]=="private, no-store" and pdf.headers["x-content-type-options"]=="nosniff"
        assert "content-disposition" in pdf.headers["access-control-expose-headers"].lower()
        passed("N10_J01_N11_real_pdf",{"sha256":sha,"bytes":len(pdf.content),"polls":polls,"url":job["result"]["download_url"]})
        staff=Client();staff.login(accounts["staff"])
        staff.get(base+"/products")
        for p in (base+"/readiness?actions=planning",path,path+"/ingredients",job["result"]["download_url"]):
            staff.get(p,expected=(403,))
        membership=owner.get(base+"/memberships").json()["data"]["items"][0]
        permissions=base+"/memberships/"+membership["membership_id"]+"/permissions"
        granted=owner.request("PUT",permissions,body=dict(grants=sorted(("menu.read","planning.result.read","planning.export","budget.read","procurement.cost.read")),reason="Synthetic current-rights verification"),match=membership["version"]).json()["data"]["membership"]
        try:
            staff.get(path)
            assert staff.get(job["result"]["download_url"]).content==pdf.content
        finally:
            owner.request("PUT",permissions,body=dict(grants=["menu.read"],reason="Restore synthetic Staff baseline"),match=granted["version"])
        staff.get(path,expected=(403,))
        staff.get(job["result"]["download_url"],expected=(403,))
        staff.get("/api/v1/jobs/"+exports["job_id"],expected=(403,))
        passed("public_grant_revoke_existing_session_retained_pdf_job")
        other=Client();other.login(accounts["other_owner"])
        for p in (base,path,path+"/ingredients",job["result"]["download_url"]):
            other.get(p,expected=(403,404))
        # CSRF/Origin is enforced on actual native HTTP, not a TestClient bypass.
        response=owner.http.post(base+"/imports",json={"data_date":day.isoformat()},headers={"Idempotency-Key":str(uuid4())})
        assert response.status_code==403
        passed("current_rights_foreign_store_csrf_denial")
        otherbase="/api/v1/stores/"+accounts["other_owner"]["store_id"]
        missing=other.get(otherbase+"/readiness?actions=planning").json()["data"]
        assert not missing["actions"][0]["can_execute"]
        passed("empty_history_missing_configuration_not_ready")
        with Session(engine) as fresh:
            record=fresh.get(PlanningRun,UUID(run))
            assert record.status=="completed" and record.record_json["public_acceptance"]["serving"]["policy"]["mode"]=="BASELINE"
        passed("fresh_session_retained_run_identity")
        evidence["completed_at"]=now_utc().isoformat();evidence["status"]="PASS";write_json(PRIVATE/"e2e.json",evidence)
        for client in (owner,staff,other):client.http.close()
    except Exception as error:
        # Preserve safe diagnostic code only. Never dump credential-bearing bodies.
        if isinstance(error,WireFailure):print(str(error),flush=True)
        raise
    finally:
        engine.dispose()


def verify_restart():
    """Compare real retained data/storage using one authenticated client across restart."""
    import subprocess
    from scripts.integration import ROOT
    from app.models.import_staging import ImportBlob
    config = settings()
    engine = create_database_engine(config)
    client = Client()
    try:
        connected_guard(engine)
        evidence = json.loads((PRIVATE / "e2e.json").read_text(encoding="utf-8"))
        assert evidence["status"] == "PASS"
        accounts = json.loads((PRIVATE / "accounts.json").read_text(encoding="utf-8"))
        client.login(accounts["owner"])
        path = "/api/v1/procurement-plans/" + evidence["gates"]["C02_C03_real_worker_baseline"]["run_id"]
        pdf_path = evidence["gates"]["N10_J01_N11_real_pdf"]["url"]
        before_run = client.get(path).json()["data"]
        before_pdf = client.get(pdf_path).content
        def blobs():
            with Session(engine) as fresh:
                return sorted((str(row.store_id), row.digest, hashlib.sha256(row.content).hexdigest())
                              for row in fresh.scalars(select(ImportBlob)))
        def artifacts():
            return {str(p.relative_to(config.runtime_directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in config.runtime_directory.rglob("*") if p.is_file()}
        before_blobs, before_artifacts = blobs(), artifacts()
        assert before_blobs and before_artifacts
        with (PRIVATE / "restart-check.log").open("ab") as log:
            result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(ROOT / "scripts/local-integration.ps1"), "restart"],
                                    cwd=ROOT, stdout=log, stderr=log, timeout=120)
        if result.returncode:
            raise WireFailure("Owned local restart failed; no second process launched")
        client.get("/api/v1/auth/me")  # Same real cookie; no re-login.
        assert client.get(path).json()["data"] == before_run
        assert client.get(pdf_path).content == before_pdf
        assert blobs() == before_blobs and artifacts() == before_artifacts
        assert httpx.get("http://localhost:5173", timeout=10).status_code == 200
        evidence["restart"] = {"status": "PASS", "same_session": True,
                               "retained_run_equal": True, "pdf_bytes_equal": True,
                               "upload_blobs_equal": len(before_blobs),
                               "runtime_files_equal": len(before_artifacts)}
        write_json(PRIVATE / "e2e.json", evidence)
        print("Same-session FE/BE restart, retained Run/PDF/upload/runtime persistence: PASS")
    finally:
        client.http.close()
        engine.dispose()


def verify_cases():
    from scripts.integration_cases import cases
    config=settings();engine=create_database_engine(config)
    owner=Client()
    try:
        connected_guard(engine)
        evidence=json.loads((PRIVATE/"e2e.json").read_text(encoding="utf-8"))
        assert evidence["status"]=="PASS"
        accounts=json.loads((PRIVATE/"accounts.json").read_text(encoding="utf-8"))
        manifest=json.loads((PRIVATE/"dataset.json").read_text(encoding="utf-8"))
        owner.login(accounts["owner"])
        def passed(name,value=True):
            evidence.setdefault("case_gates",{})[name]=value
            write_json(PRIVATE/"e2e.json",evidence)
            print(name+": PASS",flush=True)
        path="/api/v1/procurement-plans/"+evidence["gates"]["C02_C03_real_worker_baseline"]["run_id"]
        cases(owner,manifest,engine,path,evidence["gates"]["N10_J01_N11_real_pdf"]["url"],passed,completed=evidence.get("case_gates",{}))
        evidence["cases_status"]="PASS";write_json(PRIVATE/"e2e.json",evidence)
    except WireFailure as error:
        print(str(error),flush=True)
        raise
    finally:
        owner.http.close();engine.dispose()
