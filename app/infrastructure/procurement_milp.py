"""Float64 HiGHS candidate generator; exact business truth stays outside the solver.

Progressive event/dated FEFO equations selectively ported from the S342 benchmark.
No runtime imports, synthetic identities, guessed caps or business epsilon.
"""
from datetime import date, timedelta
from fractions import Fraction as F
import math
import time
from copy import deepcopy
from zoneinfo import ZoneInfo
import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix
from scipy.optimize._highspy._core import HIGHS_VERSION_MAJOR, HIGHS_VERSION_MINOR, HIGHS_VERSION_PATCH

from app.application.contracts.procurement import ProcurementInput, ConstructionRule, SolverEvidence
from app.application.procurement_solver import NumericUnsupported, SolverProposal
from app.domain.decision.procurement import Offer

PATHS = ('LOW', 'BASE', 'HIGH')
SOLVER_VERSION = (f'SciPy/{scipy.__version__}; NumPy/{np.__version__}; '
                  f'HiGHS/{HIGHS_VERSION_MAJOR}.{HIGHS_VERSION_MINOR}.{HIGHS_VERSION_PATCH}')


def add(*terms):
    out = {}
    for term in terms:
        for j, value in term.items():
            out[j] = out.get(j, F(0)) + value
    return {j:v for j,v in out.items() if v}


def mul(term, value):
    return {j:v*F(value) for j,v in term.items() if v*F(value)}


def var(j):
    return {j:F(1)}


class Model:
    def __init__(self, guards):
        self.guards = guards
        self.names=[]; self.lb=[]; self.ub=[]; self.ints=[]
        self.rows=[]; self.low=[]; self.high=[]
        self.state={}; self.served={}; self.pack=[]; self.money={}; self.scales={}
        self.build_seconds=0

    def number(self, value, *, allow_infinity=False):
        if allow_infinity and value in (-math.inf, math.inf):
            return float(value)
        value = F(value)
        try:
            projected = float(value)
        except OverflowError as error:
            raise NumericUnsupported('FLOAT64_OVERFLOW') from error
        if not math.isfinite(projected) or (value and projected == 0):
            raise NumericUnsupported('FLOAT64_NONFINITE_OR_UNDERFLOW')
        return projected

    def v(self, name, upper=1, lower=0, integer=False):
        if integer and max(abs(upper),abs(lower)) > self.guards.integer_max:
            raise NumericUnsupported('INTEGER_FLOAT64_RANGE')
        j=len(self.names)
        self.names.append(name); self.lb.append(self.number(lower)); self.ub.append(self.number(upper)); self.ints.append(int(integer))
        return j

    def row(self, expr, lower=-math.inf, upper=math.inf):
        for a in expr.values():
            if a and not F(self.guards.coefficient_min) <= abs(a) <= F(self.guards.coefficient_max):
                raise NumericUnsupported('COEFFICIENT_DYNAMIC_RANGE')
        self.rows.append(expr); self.low.append(self.number(lower,allow_infinity=True)); self.high.append(self.number(upper,allow_infinity=True))

    def eq(self, expr, value=0):
        self.row(expr,value,value)

    def state_value(self, key, expr, constant=0):
        self.state[key]=(expr,F(constant))

    def solve(self, objective, deadline, extra=()):
        started=time.perf_counter()
        rows=self.rows+[r[0] for r in extra]
        low=self.low+[self.number(r[1],allow_infinity=True) for r in extra]
        high=self.high+[self.number(r[2],allow_infinity=True) for r in extra]
        ri=[];ci=[];values=[]
        for i,row in enumerate(rows):
            for j,value in row.items():
                if value and not F(self.guards.coefficient_min)<=abs(value)<=F(self.guards.coefficient_max):
                    raise NumericUnsupported('COEFFICIENT_DYNAMIC_RANGE')
                ri.append(i);ci.append(j);values.append(self.number(value))
        matrix=coo_matrix((values,(ri,ci)),shape=(len(rows),len(self.names))).tocsc()
        c=np.zeros(len(self.names))
        for j,value in objective.items():
            if value and not F(self.guards.coefficient_min)<=abs(value)<=F(self.guards.coefficient_max):
                raise NumericUnsupported('OBJECTIVE_DYNAMIC_RANGE')
            c[j]=self.number(value)
        remaining=max(0,deadline-time.perf_counter())
        if remaining <= 0:
            return None, SolverEvidence(phase='TARGET', status=1,message='Deadline before native solve',
                incumbent=False, objective=None,bound=None,gap=None,nodes=None,seconds=time.perf_counter()-started,
                variables=len(self.names),constraints=len(rows),solver_version=SOLVER_VERSION,time_limit=0)
        native=milp(c=c,integrality=np.array(self.ints),bounds=Bounds(self.lb,self.ub),
            constraints=LinearConstraint(matrix,low,high),options=dict(time_limit=remaining,mip_rel_gap=0,presolve=True))
        def finite(name):
            value=getattr(native,name,None)
            return float(value) if value is not None and math.isfinite(float(value)) else None
        evidence=SolverEvidence(phase='TARGET',status=int(native.status),message=str(native.message),
            incumbent=native.x is not None,objective=finite('fun'),bound=finite('mip_dual_bound'),gap=finite('mip_gap'),
            nodes=None if finite('mip_node_count') is None else int(native.mip_node_count),
            seconds=time.perf_counter()-started,variables=len(self.names),constraints=len(rows),
            solver_version=SOLVER_VERSION,time_limit=remaining)
        return native.x,evidence

    def extract(self, x):
        counts=[]
        for j in self.pack:
            value=float(x[j])
            if not math.isfinite(value) or abs(value)>self.guards.integer_max:
                raise NumericUnsupported('UNSAFE_PACK_INCUMBENT')
            nearest=round(value)
            if abs(value-nearest)>float(self.guards.integer_tolerance):
                raise NumericUnsupported('NONINTEGER_PACK_INCUMBENT')
            if nearest < 0 or nearest > self.ub[j]:
                raise NumericUnsupported('PACK_INCUMBENT_OUTSIDE_BOUNDS')
            counts.append(int(nearest))
        return tuple(counts)

    def project(self, x):
        return {k:float(c)+sum(float(a)*float(x[j]) for j,a in e.items()) for k,(e,c) in self.state.items()}


def build(request: ProcurementInput, offers: tuple[Offer, ...], fixed=None):
    started=time.perf_counter()
    prepared=request.prepared; guards=request.policy.numeric; m=Model(guards)
    D=prepared.request.cutoff_date
    dates=[D+timedelta(days=t+1) for t in range(7)]
    ingredients=[i.ingredient_id for i in prepared.ingredients];products=prepared.request.product_ids
    activation=[]
    for j,o in enumerate(offers):
        x=m.v(f'pack:{o.id}',o.upper,integer=True);y=m.v(f'activate:{o.id}',integer=True)
        m.pack.append(x);activation.append(y)
        m.row(add(var(x),mul(var(y),-o.upper)),upper=0)
        m.row(add(var(x),mul(var(y),-o.minimum)),lower=0)
        if fixed is not None:m.eq(var(x),fixed[j])
        m.money=add(m.money,mul(var(x),F(o.cost)))
        if request.policy.fee_mode=='PER_OFFER':m.money=add(m.money,mul(var(y),F(o.fee)))
    supplier_fees={f.supplier_id:f.amount for f in request.supplier_fees}
    for supplier in sorted({o.supplier for o in offers}):
        indices=[j for j,o in enumerate(offers) if o.supplier==supplier]
        z=m.v(f'supplier:{supplier}',integer=True)
        for j in indices:m.row(add(var(activation[j]),mul(var(z),-1)),upper=0)
        m.row(add(var(z),*[mul(var(activation[j]),-1) for j in indices]),upper=0)
        if request.policy.fee_mode=='PER_SUPPLIER_ORDER':m.money=add(m.money,mul(var(z),F(supplier_fees[supplier])))
    if request.budget.state=='KNOWN':m.row(m.money,upper=F(request.budget.amount))
    for limit in request.supplier_limits:
        m.row(add(*[mul(var(m.pack[j]),F(o.pack)) for j,o in enumerate(offers)
                    if o.supplier==limit.supplier_id and o.ingredient==limit.ingredient_id]),upper=F(limit.maximum_quantity))
    # Lot scale is total maximum physical quantity across all potential lots; no guessed big-M.
    lots=[]
    capture=prepared.inventory_as_of.astimezone(ZoneInfo(prepared.timezone)).date()
    for lot in prepared.lots:
        if lot.received_date is not None and lot.received_date>capture:continue
        activation = (lot.received_date if prepared.operational_basis is not None and
                      lot.received_date is not None and lot.received_date > dates[0] else None)
        lots.append(dict(id=lot.id,i=lot.ingredient_id,initial=F(0) if activation else F(lot.on_hand_quantity),
            arrival=activation,amount={},amount_constant=F(lot.on_hand_quantity) if activation else F(0),
            received=lot.received_date,expiry=lot.expiry_date,max=F(lot.on_hand_quantity)))
    for a in request.arrivals:
        day=a.arrival_day;expiry=a.expiry_date
        lots.append(dict(id=a.lot_id,i=a.ingredient_id,initial=F(0),arrival=day,
            amount=None,amount_constant=F(a.quantity),received=day,expiry=expiry,max=F(a.quantity)))
    for j,o in enumerate(offers):
        day=D+timedelta(days=1+o.lead)
        lots.append(dict(id=o.lot_id,i=o.ingredient,initial=F(0),arrival=day,
            amount=mul(var(m.pack[j]),F(o.pack)),received=day,
            expiry=None if o.shelf is None else day+timedelta(days=o.shelf),max=F(o.pack)*o.upper))
    for i in ingredients:
        scale=sum((lot['max'] for lot in lots if lot['i']==i),F(0)) or F(1)
        if not F(guards.scale_min)<=scale<=F(guards.scale_max):raise NumericUnsupported('LOT_SCALE_RANGE')
        m.scales[i]=scale
    recipes={};intensity={};demand={}
    for day in dates:
        for p in products:
            matches=[r for r in prepared.recipes if r.product_id==p and r.effective_from<=day and (r.effective_to is None or day<=r.effective_to)]
            if len(matches)!=1 or not matches[0].lines:raise ValueError('Dated recipe incomplete')
            r=recipes[day,p]=matches[0]
            intensity[day,p]={l.ingredient_id:F(l.quantity)/(F(r.yield_quantity)*(1-F(r.process_loss_rate))) for l in r.lines}
    for point in prepared.forecast.predictions:
        for path,field in zip(PATHS,('p25','p50','p75')):demand[path,point.forecast_date,point.product_id]=F(getattr(point,field))
    ordered=sorted(lots,key=lambda l:(l['expiry'] is None,l['expiry'] or date.max,l['received'] is None,l['received'] or date.max,l['id']))
    endings={}
    for path in PATHS:
        for t,day in enumerate(dates):
            available={};gross={};takes={};expired={};new_end={};usable_lots={}
            for lot in lots:
                i=lot['i'];scale=m.scales[i];lid=lot['id']
                opening=(var(endings[path,lid]),F(0)) if t else ({},lot['initial']/scale)
                arrival=((lot['amount'] or {}),lot.get('amount_constant',F(0))) if lot['arrival']==day else ({},F(0))
                arrival=(mul(arrival[0],1/scale),arrival[1]/scale)
                ge=add(opening[0],arrival[0]);gc=opening[1]+arrival[1]
                gross[i]=(add(gross.get(i,({},F(0)))[0],ge),gross.get(i,({},F(0)))[1]+gc)
                pre=lot['expiry'] is not None and lot['expiry']<day
                ue,uc=({},F(0)) if pre else (ge,gc)
                usable_lots[lid]=(ue,uc)
                take=m.v(f'take:{path}:{day}:{lid}',float(lot['max']/scale))
                m.row(add(var(take),mul(ue,-1)),upper=uc)
                end=m.v(f'end:{path}:{day}:{lid}',float(lot['max']/scale))
                close=lot['expiry']==day
                m.eq(var(end)) if close else m.eq(add(var(end),var(take),mul(ue,-1)),uc)
                takes[lid]=take;new_end[path,lid]=end
                available[i]=(add(available.get(i,({},F(0)))[0],ue),available.get(i,({},F(0)))[1]+uc)
                expired[i]=(add(expired.get(i,({},F(0)))[0],ge if pre else add(ue,mul(var(take),-1)) if close else {}),
                    expired.get(i,({},F(0)))[1]+(gc if pre else uc if close else 0))
                key=('lots',path,str(day),str(lid))
                for name,expr,const in [('opening',*opening),('arrivals',*arrival),('pre_service_expired',ge if pre else {},gc if pre else 0),
                    ('consumed',var(take),0),('close_expired',add(ue,mul(var(take),-1)) if close else {},uc if close else 0),
                    ('other_waste',{},0),('ending',var(end),0)]:m.state_value(key+(name,),mul(expr,scale),const*scale)
            for capacity in request.capacities:
                i=capacity.ingredient_id;cap=capacity.maximum_quantity
                ge,gc=gross.get(i,({},F(0)));m.row(ge,upper=F(cap)/m.scales[i]-gc)
            # FEFO priority: later positive take implies all prior usable balances exhausted.
            for k,lot in enumerate(ordered):
                if not lot['max']:continue
                lid=lot['id'];i=lot['i'];w=m.v(f'fefo:{path}:{day}:{lid}',integer=True)
                m.row(add(var(takes[lid]),mul(var(w),-lot['max']/m.scales[i])),upper=0)
                for prior in ordered[:k]:
                    if prior['i']!=i:continue
                    pe,pc=usable_lots[prior['id']];bound=prior['max']/m.scales[i]
                    m.row(add(pe,mul(var(takes[prior['id']]),-1),mul(var(w),bound)),upper=bound-pc)
            active_products=[p for p in products if demand[path,day,p]>0]
            fractions={p:{} for p in products}
            if active_products:
                n=len(active_products);active={p:var(m.v(f'active:{path}:{day}:{p}:0',integer=True)) for p in active_products}
                for a in active.values():m.eq(a,1)
                mu_prev={};fprev={p:{} for p in active_products}
                for k in range(n):
                    mu=var(m.v(f'mu:{path}:{day}:{k}'));delta=var(m.v(f'delta:{path}:{day}:{k}'))
                    m.eq(add(mu,mul(mu_prev,-1),mul(delta,-1)))
                    fnew={}
                    for p in active_products:
                        v=var(m.v(f'increment:{path}:{day}:{p}:{k}'))
                        m.row(add(v,mul(delta,-1)),upper=0);m.row(add(v,mul(active[p],-1)),upper=0)
                        m.row(add(v,mul(delta,-1),mul(active[p],-1)),lower=-1)
                        f=var(m.v(f'fulfilled_fraction:{path}:{day}:{p}:{k}'));m.eq(add(f,mul(fprev[p],-1),mul(v,-1)));fnew[p]=f
                    zs={}
                    for i in ingredients:
                        ae,ac=available.get(i,({},F(0)))
                        consumption=add(*[mul(fnew[p],intensity[day,p].get(i,F(0))*demand[path,day,p]/m.scales[i]) for p in active_products])
                        residual=add(ae,mul(consumption,-1));m.row(residual,lower=-ac)
                        users=[p for p in active_products if intensity[day,p].get(i,F(0))>0]
                        if users:
                            z=var(m.v(f'saturated:{path}:{day}:{i}:{k}',integer=True));zs[i]=z
                            m.row(add(residual,z),upper=1-ac)
                            m.row(add(z,*[mul(active[p],-1) for p in users]),upper=0)
                    done=var(m.v(f'done:{path}:{day}:{k}',integer=True));h=var(m.v(f'any_active:{path}:{day}:{k}',integer=True))
                    m.row(add(mu,mul(done,-1)),lower=0)
                    for a in active.values():m.row(add(a,mul(h,-1)),upper=0)
                    m.row(add(h,*[mul(a,-1) for a in active.values()]),upper=0)
                    m.row(add(*zs.values(),done,mul(h,-1)),lower=0)
                    anew={}
                    for p in active_products:
                        a=var(m.v(f'active:{path}:{day}:{p}:{k+1}',integer=True));anew[p]=a
                        used=[zs[i] for i in intensity[day,p] if i in zs and intensity[day,p][i]>0]
                        m.row(add(a,mul(active[p],-1)),upper=0);m.row(add(a,done),upper=1)
                        for z in used:m.row(add(a,z),upper=1)
                        m.row(add(a,mul(active[p],-1),done,*used),lower=0)
                        if k==n-1:m.eq(a)
                    active=anew;mu_prev=mu;fprev=fnew
                fractions.update(fprev)
            for p in products:
                served=mul(fractions[p],demand[path,day,p]);m.served[path,day,p]=served
                key=('products',path,str(day),str(p))
                m.state_value(key+('requested',),{},demand[path,day,p]);m.state_value(key+('fulfilled',),served)
                m.state_value(key+('lost',),mul(served,-1),demand[path,day,p])
                for i,coeff in intensity[day,p].items():m.state_value(('contributions',path,str(day),str(p),str(i),'quantity'),mul(served,coeff))
            for i in ingredients:
                cons=add(*[mul(m.served[path,day,p],intensity[day,p].get(i,F(0))/m.scales[i]) for p in products])
                m.eq(add(*[var(takes[l['id']]) for l in lots if l['i']==i],mul(cons,-1)))
                ae,ac=available.get(i,({},F(0)));need=sum((demand[path,day,p]*intensity[day,p].get(i,F(0)) for p in products),F(0))
                m.row(add(cons,mul(ae,-1)),upper=ac)
                end=add(*[var(new_end[path,l['id']]) for l in lots if l['i']==i]);ee,ec=expired.get(i,({},F(0)))
                key=('ingredients',path,str(day),str(i));scale=m.scales[i]
                for name,expr,const in [('requested',{},need/scale),('available',ae,ac),('consumed',cons,0),
                    ('expired',ee,ec),('other_waste',{},0),('ending',end,0)]:m.state_value(key+(name,),mul(expr,scale),const*scale)
                # max(full need - available,0); derive M from max(need,scale).
                shortage=var(m.v(f'shortage:{path}:{day}:{i}',max(1,float(need/scale))))
                z=var(m.v(f'shortage_positive:{path}:{day}:{i}',integer=True));bound=max(F(1),need/scale)
                diff=add(shortage,ae)
                m.row(diff,lower=need/scale-ac)
                m.row(add(shortage,mul(z,-bound)),upper=0)
                m.row(add(diff,mul(z,bound)),upper=need/scale-ac+bound)
                m.state_value(key+('shortage',),mul(shortage,scale))
            endings.update(new_end)
    m.demand=demand;m.products=products;m.dates=dates
    # Reject unsafe coefficient dynamics rather than erasing small business values.
    for row in m.rows:
        for coefficient in row.values():
            if coefficient and not F(guards.coefficient_min)<=abs(coefficient)<=F(guards.coefficient_max):raise NumericUnsupported('COEFFICIENT_DYNAMIC_RANGE')
    m.build_seconds=time.perf_counter()-started
    return m


def target_rows(model, rule: ConstructionRule):
    served=add(*[e for (path,day,p),e in model.served.items() if path==rule.path])
    demand=sum((v for (path,day,p),v in model.demand.items() if path==rule.path),F(0))
    rows=[(served,F(rule.target)*demand,math.inf)]
    for floor in rule.floors:
        expr=add(*[e for (path,day,p),e in model.served.items() if path==rule.path and p==floor.product_id])
        need=sum((v for (path,day,p),v in model.demand.items() if path==rule.path and p==floor.product_id),F(0))
        rows.append((expr,F(floor.target)*need,math.inf))
    return rows


def exclude_vector(model: Model, vector: tuple[int, ...]):
    """Bounded disjunction excludes only this integer vector, never a neighborhood."""
    if len(vector)!=len(model.pack):raise ValueError('Exclusion vector length mismatch')
    flags=[]
    for j,value in zip(model.pack,vector):
        bound=int(model.ub[j]);big=bound+1
        # Both xbar + M row bounds must remain exactly representable integers.
        # A pack alone within float64's integer range does not guarantee this.
        if 2*bound+1 > model.guards.integer_max:
            raise NumericUnsupported('EXCLUSION_INTEGER_ROW_RANGE')
        if not 0<=value<=bound:raise ValueError('Exclusion vector outside domain')
        left=var(model.v(f'exclude_left:{len(model.names)}',integer=True))
        right=var(model.v(f'exclude_right:{len(model.names)}',integer=True));flags.extend((left,right))
        model.row(add(var(j),mul(left,big)),upper=value-1+big)
        model.row(add(var(j),mul(right,-big)),lower=value+1-big)
    model.row(add(*flags),lower=1)


class NativeSearch:
    """One strategy's model/cuts. Composition passes a fresh instance per strategy."""
    def __init__(self, request: ProcurementInput, offers: tuple[Offer, ...]):
        self.model=build(request,offers)
        self.fallback_model=deepcopy(self.model)
        self.fallback_level=None

    def solve(self, rule, phase, deadline):
        model=self.model if phase=='TARGET' else self.fallback_model
        served=add(*[e for (path,day,p),e in model.served.items() if path==rule.path])
        requested=sum((v for (path,day,p),v in model.demand.items() if path==rule.path),F(0)) or F(1)
        extra=target_rows(model,rule) if phase=='TARGET' else ()
        objective=mul(served,-1/requested) if phase=='FALLBACK_SERVICE' else model.money
        if phase=='FALLBACK_COST':
            if self.fallback_level is None:raise ValueError('Fallback cost before service incumbent')
            extra=((served,self.fallback_level,math.inf),)
        x,evidence=model.solve(objective,deadline,extra)
        evidence=evidence.model_copy(update={'phase':phase})
        try:
            counts=None if x is None else model.extract(x)
        except NumericUnsupported as error:
            error.solver_evidence=evidence
            raise
        evidence=evidence.model_copy(update={'extracted_counts':counts})
        if x is not None and phase=='FALLBACK_SERVICE':
            self.fallback_level=F(str(sum(float(a)*float(x[j]) for j,a in served.items())))
        return SolverProposal(evidence,counts)

    def exclude(self, counts, *, phase, hard_invalid):
        if phase=='TARGET':
            exclude_vector(self.model,counts)
            if hard_invalid:exclude_vector(self.fallback_model,counts)
        else:
            exclude_vector(self.fallback_model,counts)
