"""Data sufficiency and explicit declarations; never fits a model or runs procurement."""
from collections import Counter
from datetime import date,timedelta
from decimal import Decimal
from bisect import bisect_right

from app.application.contracts.demo_workbooks import AdmissionFinding
from app.application.contracts.forecast_benchmark import BenchmarkOrigin, BenchmarkDataset, BenchmarkPlan, ARMS
from app.application.demo_workbook_normalization import evidence_at, Table, day
from app.application.forecast_benchmark_admission import next_run, admit_plan
from app.application.forecast_challenger_serialization import challenger_digest
from app.domain.forecasting.stockout import Observation,reconstruct

OP_TABLES={
    'usage':('usage','NL_thực_dùng',('Ngày sử dụng','Tên NL','Lượng thực dùng','ĐVT','Hao hụt','Nguồn')),
    'inventory':('stock_vendor','KiemKe_27-07',('Ngày kiểm kê','Mặt hàng tồn','SL cuối ngày','ĐV','HSD','Mã lô','Vị trí')),
    'purchase_history':('stock_vendor','PNK tháng 7',('NCT','Tên hàng','SLN','ĐVT','Giá nhập','Thành tiền','NCC','Hạn dùng','Batch','Số PO')),
    'vendor_terms':('stock_vendor','Vendor rules',('Vendor','Material','MOQ','Order UOM','Pack Size','Base UOM','Lead time (days)','Giá mua','Lịch giao')),
    'recipes':('recipes_rules','Định lượng món',('Món bán','Thành phần','Lượng / 1 SP','Đơn vị NL','Yield','Đơn vị SP','Ver','Áp dụng từ')),
    'constraints':('recipes_rules','Điều kiện vận hành',('Loại điều kiện','Áp dụng cho NL','Giá trị','Unit','Currency','Bắt đầu','Ghi chú')),
}


def source_tables(books):
    lookup={b.role:b for b in books};result=[]
    for kind,(role,sheet,headers) in OP_TABLES.items():
        table=Table(lookup[role],sheet,headers)
        result.append(dict(kind=kind,file_sha256=lookup[role].sha256,sheet=sheet,headers=headers,
            rows=tuple(tuple(table.evidence(row,c) for c in range(len(headers))) for row in table.rows())))
    return tuple(result)


def proposed_windows(last_sales_date,protocol):
    # Translate the E1 template as a block; preserve partitions, spacing and all offsets.
    templates=tuple(BenchmarkOrigin.model_validate(t) for t in protocol['tasks'])
    shift=(last_sales_date-timedelta(days=7))-templates[-1].origin
    return tuple(BenchmarkOrigin(**{k:v+shift if isinstance(v,date) else v for k,v in task.model_dump().items()}) for task in templates)


def postprocess_population(observed,products,start,end,prior_fit_end,holdout):
    """Task/date support only, conditional on known-at declarations; never model predictions."""
    eligible=Counter();purged=quarantined=unscoreable=0
    for i in range((end-start).days+1):
        target=start+timedelta(days=i)
        for product in products:
            row=observed.get((product.product_id,target))
            for horizon in range(1,8):
                if target-timedelta(days=horizon)<prior_fit_end:purged+=1
                elif target in holdout:quarantined+=1
                elif row is None or row.quantity is None or row.is_stockout is not False:unscoreable+=1
                else:eligible[str(horizon)]+=1
    return dict(eligible_known_false_tasks_by_horizon_upper_bound=dict(eligible),purged_tasks=purged,
                holdout_quarantined_tasks=quarantined,unscoreable_tasks=unscoreable,
                availability='CONDITIONAL_ON_DECLARED_VINTAGES_NOT_CURRENT_PROOF')


def forecast_projection(data,declarations,findings,tasks):
    if not declarations.timezone or not declarations.accept_five_single_item_scope or declarations.observation_availability=='UNDECLARED':
        return None,None
    if any(f.classification=='BLOCKER' and f.area in ('DATA','IDENTITY') for f in findings): return None,None
    value=BenchmarkDataset(classification='SYNTHETIC',use_authority='user_authorized:workspace_demo_workbook_preparation/1',
        source_revision=data.source_revision,availability_basis='retrospective_current_revision',
        limitations=('DEMO_GENERATED_EXPOSED, not real/unseen evidence; no promotion.',
            'Explicit retrospective next-run label availability assumption; not recovered historical vintages.',
            'Five single-item benchmark scope only; source Menu status unchanged.',
            'No sourced calendar issue/availability times. Calendar facts retained in staging; runtime C remains blocked.'),
        store_id=data.store_id,timezone=declarations.timezone,
        products=tuple(dict(product_id=p.product_id,selling_unit=p.selling_unit) for p in data.products),
        observations=tuple(dict(store_id=data.store_id,product_id=r.product_id,sales_date=r.sales_date,quantity=r.quantity,
            selling_unit=next(p.selling_unit for p in data.products if p.product_id==r.product_id),is_stockout=r.is_stockout,
            available_at=next_run(r.sales_date,declarations.timezone),source=challenger_digest('source-cells',r.sources))
            for r in data.sales if r.quantity is not None),calendar=())
    plan=BenchmarkPlan(dataset_digest=challenger_digest('dataset',value),tasks=tasks)
    admit_plan(value,plan)
    return value,plan


def assess(data,books,declarations,normalization_issues,protocol):
    lookup={b.role:b for b in books}
    tables=source_tables(books)
    by_kind={t['kind']:t for t in tables}
    findings=list(normalization_issues)
    def fact(code,classification,area,detail,*sources):
        findings.append(AdmissionFinding(code=code,classification=classification,area=area,detail=detail,sources=sources))
    def cell(role,sheet,address): return evidence_at(lookup[role],sheet,address)
    if not data.products or not data.sales: raise ValueError('NO_NORMALIZED_POS_SCOPE')
    profiles={}
    for kind,column in (('usage',0),('inventory',0),('purchase_history',0),('recipes',7),('constraints',5)):
        rows=by_kind[kind]['rows'];role=OP_TABLES[kind][0]
        dates=[]
        for row in rows:
            try: dates.append(day(row[column].raw,lookup[role].parsed.excel_date_system))
            except ValueError:
                fact('OPERATIONAL_DATE_INVALID','BLOCKER','E4','Required operational date is absent/invalid; not replaced by upload date.',row[column])
        distinct=set(dates)
        profiles[kind]=dict(rows=len(rows),first=min(distinct,default=None),last=max(distinct,default=None),distinct_dates=len(distinct))
    unit_variants={}
    for kind,name_column,unit_column in (('usage',1,3),('inventory',1,3),('purchase_history',1,3),
                                        ('vendor_terms',1,5),('recipes',1,3),('constraints',1,3)):
        for row in by_kind[kind]['rows']:
            if kind=='constraints' and row[0].raw not in ('safety_stock','maximum_stock'):
                # Duration/ratio/aggregate-volume units are distinct measured fields,
                # never aliases for an Ingredient's physical quantity unit.
                continue
            name,unit=row[name_column].raw,row[unit_column].raw
            if name and unit: unit_variants.setdefault(name,{}).setdefault(unit,row[unit_column])
    conflicts={name:tuple(units.values()) for name,units in unit_variants.items() if len(units)>1}
    if conflicts:
        fact('INGREDIENT_UNIT_ALIASES_UNDECLARED','BLOCKER','E4',
            'Same Ingredient names use distinct unit spellings. Preserve units; dimensional aliases/conversions require explicit declarations.',
            *(v for units in conflicts.values() for v in units))
    for row in by_kind['recipes']['rows']:
        try: valid=row[4].raw is not None and Decimal(row[4].raw).is_finite() and Decimal(row[4].raw)>0
        except Exception: valid=False
        if not valid: fact('RECIPE_YIELD_MISSING_OR_INVALID','BLOCKER','E4','Yield requires an explicit positive source value; no default yield is applied.',row[4])
    first,last=min(r.sales_date for r in data.sales),max(r.sales_date for r in data.sales)
    tasks=proposed_windows(last,protocol)
    observed={(r.product_id,r.sales_date):r for r in data.sales}
    days={r.sales_date for r in data.sales};calendar={r.day:r for r in data.calendar}
    missing={(p.product_id,first+timedelta(days=i)) for p in data.products for i in range((last-first).days+1)}-set(observed)
    stats=dict(products=len(data.products),rows=len(data.sales),distinct_dates=len(days),first=first,last=last,
        missing_product_days=len(missing),blank_quantities=sum(r.quantity is None for r in data.sales),
        explicit_zero=sum(r.quantity==0 for r in data.sales),
        stockout=dict(Counter('true' if r.is_stockout is True else 'false' if r.is_stockout is False else 'unknown' for r in data.sales)),
        calendar_first=min(calendar,default=None),calendar_last=max(calendar,default=None),calendar_dates=len(calendar),
        calendar_sales_overlap=len(set(calendar)&days),
        calendar_missing_over_sales_history=len(days-set(calendar)))
    pos_note=cell('pos','POS_T7_2026','A2')
    demo_declared=pos_note.raw is not None and 'demo' in pos_note.raw.casefold() and any(w in pos_note.raw.casefold() for w in ('giả lập','mô phỏng','synthetic'))
    fact('DEMO_NOT_REAL_UNSEEN' if demo_declared else 'DEMO_SOURCE_CLASSIFICATION_UNCONFIRMED',
        'CURRENT_FACT' if demo_declared else 'BLOCKER','DATA',
        'POS explicitly declares generated demo data; no real/unseen or promotion evidence.' if demo_declared else 'Source content does not establish generated DEMO classification.',pos_note)
    fact('FIVE_SINGLE_ITEM_SCOPE','PROPOSAL','IDENTITY','Benchmark only the five single items by unique Menu code/name/unit; do not mutate source active statuses.',cell('menu','06_Menu','A2'))
    if len(data.products)!=5:
        fact('EXPECTED_FIVE_SINGLE_ITEMS','BLOCKER','IDENTITY','This named DEMO adapter requires exactly five single items.')
    if not declarations.timezone:
        fact('STORE_TIMEZONE_REQUIRED','BLOCKER','FORECAST_AB','Workbook business dates have no Store timezone; declare it before aware cutoff/availability projection.')
    if not declarations.accept_five_single_item_scope:
        fact('SINGLE_ITEM_SCOPE_DECLARATION_REQUIRED','BLOCKER','FORECAST_AB','Explicitly accept the five single-item codes/names as benchmark-only scope; active combos remain unchanged.')
    if declarations.observation_availability=='UNDECLARED':
        fact('OBSERVATION_VINTAGE_REQUIRED','BLOCKER','FORECAST_AB','Provide historical revision availability or explicitly declare retrospective next-run assumption for DEMO only.')
    fact('CALENDAR_HISTORY_AND_VINTAGE_MISSING','BLOCKER','FORECAST_C',
        'C requires sourced dense prefix calendar at each feature origin plus D+1..D+7 known-ahead facts. Missing dates are not default-open; issue times are absent.',
        cell('calendar','Calendar + Weather','A2'),cell('calendar','Calendar + Weather','A4'))
    if any(c.closed is True and r.quantity is not None and r.quantity>0 for r in data.sales if (c:=calendar.get(r.sales_date)) is not None):
        fact('POS_POSITIVE_ON_CLOSED_DATE','BLOCKER','DATA','Resolve positive sales contradicting explicit closure before C admission.')
    menu=lookup['menu'];sheet=next(s for s in menu.parsed.sheets if s.name=='06_Menu')
    combos=[]
    for row in sheet.rows:
        if row.row_number<=3: continue
        b=cell('menu','06_Menu','B'+str(row.row_number));j=cell('menu','06_Menu','J'+str(row.row_number))
        if b.raw=='Combo' and j.raw=='Đang bán':combos.append(j)
    menu_note=cell('menu','06_Menu','A2')
    if combos and menu_note.raw and ('tạm dừng' in menu_note.raw.casefold() or 'paused' in menu_note.raw.casefold()):
        fact('MENU_COMBO_STATUS_CONFLICT','CURRENT_FACT','IDENTITY','Description says combos paused; some literal row statuses remain active. No source status rewritten.',
             cell('menu','06_Menu','A2'),*combos)
    usage_note=cell('usage','NL_thực_dùng','A2')
    derived=usage_note.raw is not None and all(w in usage_note.raw.casefold() for w in ('pos','recipe'))
    fact('USAGE_DERIVED_NOT_INDEPENDENT_TRUTH' if derived else 'USAGE_INDEPENDENCE_UNESTABLISHED',
        'CURRENT_FACT' if derived else 'BLOCKER','E4',
        'Usage description explicitly ties quantities to POS + recipe; not independent realized-demand/consumption evidence.' if derived else 'Independent usage truth not established.',
        usage_note,cell('usage','NL_thực_dùng','F4'))
    inventory=by_kind['inventory']['rows']
    inventory_dates=sorted({day(row[0].raw,lookup['stock_vendor'].parsed.excel_date_system) for row in inventory})
    fact('SINGLE_STOCK_SNAPSHOT','BLOCKER','E4',
        'Only snapshot dates '+','.join(map(str,inventory_dates))+'. No historical stock at the proposed July/August origins; current balance cannot silently become historical stock.',
        cell('stock_vendor','KiemKe_27-07','A1'),cell('stock_vendor','KiemKe_27-07','A4'))
    fact('VENDOR_PRICE_MOQ_BASIS_REQUIRED','BLOCKER','E4',
        'Declare price denominator/currency and MOQ unit for each offer. Retain raw price and pack fields; do not infer pack_cost from purchase history.',
        *(cell('stock_vendor','Vendor rules',a) for a in ('C3','D3','E3','H3','C4','D4','E4','F4','H4')))
    fact('FEES_SHELF_LIFE_AND_EFFECTIVITY_REQUIRED','BLOCKER','E4',
        'Vendor rows omit payable fees, future purchased-lot shelf life and effective-from/known-at times. Receipt expiry and shelf_life_target are not future offer shelf life.',
        cell('stock_vendor','Vendor rules','A3'),cell('stock_vendor','Vendor rules','I3'),cell('recipes_rules','Điều kiện vận hành','A11'))
    fact('DELIVERY_SCHEDULE_NOT_FIXED_LEAD_ONLY','BLOCKER','E4',
        'Weekday delivery schedules are explicit. Existing lead-days-only arrivals cannot silently ignore them; supply effective dated arrivals/semantics or implement an authorized policy.',
        cell('stock_vendor','Vendor rules','G4'),cell('stock_vendor','Vendor rules','I4'))
    fact('RECIPE_LOSS_NOT_USAGE_WASTE','BLOCKER','E4',
        'Recipe yield is explicit; process_loss_rate and historical revision availability are not. Usage Hao hụt is not a recipe loss rate.',
        cell('recipes_rules','Định lượng món','E4'),cell('recipes_rules','Định lượng món','G4'),cell('recipes_rules','Định lượng món','H4'),cell('usage','NL_thực_dùng','E3'))
    constraint_rows=by_kind['constraints']['rows']
    safety=[r for r in constraint_rows if r[0].raw=='safety_stock']
    if safety:
        fact('SAFETY_STOCK_UNSUPPORTED','BLOCKER','E4','Captured safety constraints remain unsupported by host; declarations cannot turn them into supported policy or discard them.',
            *(v for r in safety for v in (r[0],r[1],r[2],r[3],r[6])))
    fact('BUDGET_CAPACITY_REQUIREMENT_SEMANTICS_REQUIRED','BLOCKER','E4',
        'Weekly budget is not automatically a one-order limit; aggregate storage volume is not independent Ingredient capacities; service_level_target does not specify paths/per-Product/horizon overrides. Unit aliases remain proposals.',
        *(cell('recipes_rules','Điều kiện vận hành',a) for a in ('A4','C4','G4','A5','C5','D5','G5','A9','C9','D9','A12','C12','G12')))
    missing_expiry=[r[4] for r in inventory if r[4].raw in (None,'')]
    if missing_expiry:
        fact('EXPIRY_TRACKING_DECLARATION_REQUIRED','BLOCKER','E4','Expiry-tracking flags are absent; unknown lot expiry cannot be made untracked without a declaration.',*missing_expiry)
    fact('PURCHASE_HISTORY_NOT_CURRENT_STOCK_OR_INBOUND','CURRENT_FACT','E4','Purchase rows remain history; do not add them to snapshot balances or scheduled inbound.',cell('stock_vendor','PNK tháng 7','A2'))
    fact('LOT_RECEIPT_DATE_UNKNOWN','CURRENT_FACT','E4','Count date is not lot receipt date; do not parse receipt dates from batch codes. Unknown receipt remains optional-warning/null under ADR-010.',
        cell('stock_vendor','KiemKe_27-07','A3'),cell('stock_vendor','KiemKe_27-07','F4'))
    window_reports=[]
    holdout_dates={t.origin+timedelta(days=h) for t in tasks if t.partition=='holdout' for h in range(1,8)}
    for t in tasks:
        prefixes={p.product_id:tuple(Observation(r.sales_date,r.quantity,r.is_stockout) for r in data.sales
            if r.product_id==p.product_id and r.sales_date<=t.origin and r.quantity is not None) for p in data.products}
        counts=[sum(e.usable for e in reconstruct(rows,t.origin)) for rows in prefixes.values()]
        supervised=[]
        for product in data.products:
            known_false=sorted(r.sales_date for r in data.sales if r.product_id==product.product_id and
                               r.sales_date<=t.origin and r.quantity is not None and r.is_stockout is False)
            # Conservative lower bound: only sourced known-false labels/support, never reconstructed labels.
            supervised.append(sum(bisect_right(known_false,target-timedelta(days=h))>=28
                for target in known_false if target not in holdout_dates for h in range(1,8)))
        target_rows=[observed.get((p.product_id,t.origin+timedelta(days=h))) for p in data.products for h in range(1,8)]
        masks=Counter('missing' if r is None or r.quantity is None else 'censored_lower_bound' if r.is_stockout is True else
                      'primary_known_false' if r.is_stockout is False else 'supplementary_unknown' for r in target_rows)
        window_reports.append(dict(windows=t,host_usable_prefix_min=min(counts),host_supervised_known_false_rows_min=len(supervised) and min(supervised),
            host_data_readiness_under_declared_availability=
            'A_BASELINE_AND_B_MIN_HISTORY_MET' if min(counts)>=28 and min(supervised)>=14 else 'INSUFFICIENT_HOST_HISTORY',target_masks=dict(masks),
            native_minimum_distinct_training_dates=protocol['arm_configuration'][ARMS[2]]['forecast_config']['walk_forward_minimum_train_days'],
            native_training_calendar_dates=sum(first<=d<=t.train_end for d in calendar),
            native_calendar_missing_prefix_dates=sum(first+timedelta(days=i) not in calendar for i in range((t.origin-first).days+8)),
            point_known_false_dates_upper_bound=len({r.sales_date for r in data.sales if t.point_start<=r.sales_date<=t.point_end and r.quantity is not None and r.is_stockout is False}),
            point_task_population=postprocess_population(observed,data.products,t.point_start,t.point_end,t.train_end,holdout_dates),
            cqr_task_population=postprocess_population(observed,data.products,t.calibration_start,t.calibration_end,t.point_end,holdout_dates),
            cqr_known_false_dates_upper_bound=len({r.sales_date for r in data.sales if t.calibration_start<=r.sales_date<=t.calibration_end and r.sales_date not in holdout_dates and r.quantity is not None and r.is_stockout is False})))
    projection,plan=forecast_projection(data,declarations,findings,tasks)
    data_blocked=any(f.classification=='BLOCKER' and f.area in ('DATA','IDENTITY') for f in findings)
    declarations_needed=[dict(id='forecast_timezone',required_for='A/B retrospective input',
        declaration='Store business timezone, not inferred from interface/user timezone.',sources=()),
        dict(id='benchmark_scope',required_for='A/B retrospective input',declaration='Explicit benchmark-only selection of the five single items, leaving all Menu rows unchanged.',
             sources=tuple(v for p in data.products for v in p.sources)),
        dict(id='retrospective_observation_availability',required_for='A/B retrospective input',
             declaration='Historical revision availability evidence, or explicit acceptance of next-run dates as a DEMO-only retrospective assumption.',
             sources=(cell('pos','POS_T7_2026','A2'),)),
        dict(id='vendor_price_moq_arrivals',required_for='Future E4; insufficient by itself',
             declaration='Price denominator/currency, MOQ basis and dated delivery/lead/schedule semantics per offer.',
             sources=tuple(v for row in by_kind['vendor_terms']['rows'] for v in row)),
        dict(id='fees_shelf_life_effectivity',required_for='Future E4; insufficient by itself',
             declaration='Complete payable fees including explicit none if true, purchased-lot shelf life, expiry-tracking flags, additional supplier limits/completeness and term effective/known-at times.',
             sources=tuple(missing_expiry)),
        dict(id='recipe_loss_known_at',required_for='Future E4; insufficient by itself',
             declaration='Process loss rate per recipe and version known-at; preserve sourced yield/effectivity, do not infer from usage waste.',
             sources=(cell('recipes_rules','Định lượng món','E4'),cell('recipes_rules','Định lượng món','G4'),cell('recipes_rules','Định lượng món','H4'))),
        dict(id='operational_basis_and_requirements',required_for='Future E4; insufficient by itself',
             declaration='Historical operational snapshots or explicitly counterfactual stock basis; inventory completeness/committed inbound/no additional orders, one-order/weekly budget meaning, unit aliases, capacity units/checkpoints and customer paths/per-Product requirements. Unsupported constraints remain blocking.',
             sources=tuple(v for row in constraint_rows for v in row))]
    resolved={'forecast_timezone':bool(declarations.timezone),'benchmark_scope':declarations.accept_five_single_item_scope,
              'retrospective_observation_availability':declarations.observation_availability!='UNDECLARED'}
    declarations_needed=[d for d in declarations_needed if not resolved.get(d['id'],False)]
    manifest=dict(schema_version=1,evidence_class=data.evidence_class,normalization='BLOCKED' if data_blocked else 'READY',
        forecast_AB='BLOCKED_DATA' if data_blocked else 'BLOCKED_INSUFFICIENT_HOST_HISTORY' if any(w['host_data_readiness_under_declared_availability']=='INSUFFICIENT_HOST_HISTORY' for w in window_reports)
            else 'READY_DEMO_EXPLORATORY_INPUT' if projection else 'PARTIAL_DECLARATIONS_REQUIRED',
        forecast_C='BLOCKED',paired_ABC='BLOCKED',E4='BLOCKED',real_unseen='NOT_ESTABLISHED_DEMO_EXPOSED',production='LOCKED',
        scope_status=data.scope_status,statistics=stats,windows=window_reports,findings=findings,
        planned_workload=dict(origins=4,products=len(data.products),horizon=7,arms=list(ARMS),tasks_per_arm=4*len(data.products)*7,
            host_B_boosters=12,native_C_boosters_if_admitted=12,point_CQR_fits_if_admitted=8,
            runnable_C_fits=0,executed_fits=0,executed_planning_solves=0,
            resource_policy='Existing E3 max24 boosters/8 postprocess/300s is a ceiling, not a runtime estimate for this larger corpus; no execution authorized.'),
        inventory_dates=inventory_dates,operational_table_counts={t['kind']:len(t['rows']) for t in tables},
        operational_date_profiles=profiles,required_user_declarations=declarations_needed,
        operational_unit_conflicts=conflicts,
        additional_source_data_required=('C: sourced calendar for missing prefix dates and known-ahead availability vintages; no invented open dates.',
            'E4: historical operational population/independent eligible realized targets; safety-stock and aggregate constraints require separately authorized supported semantics, not a declaration to discard them.'))
    return manifest,tables,projection,plan
