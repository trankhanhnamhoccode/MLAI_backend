"""Captured-value projection and internal identity; never executes an engine."""
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import json
from uuid import UUID
from app.application.contracts.serving import Quantity
from app.application.contracts.procurement_comparison import SignedQuantity, FeeComponent, OutlayBreakdown
from app.domain.decision.quantities import checked, display, exact
from app.domain.decision.comparison import total


def q(value):
    return F(int(value.numerator),int(value.denominator))


def quantity(value):
    value=checked(value)
    return Quantity(numerator=str(value.numerator),denominator=str(value.denominator),decimal_view=display(value))


def signed(value):
    value=checked(value)
    return SignedQuantity(numerator=str(value.numerator),denominator=str(value.denominator),decimal_view=display(value))


def _canonical(value):
    if isinstance(value,Decimal):
        number=exact(value)
        return ['decimal',str(number.numerator),str(number.denominator)]
    if isinstance(value,UUID):return ['uuid',str(value)]
    if isinstance(value,datetime):return ['instant',value.isoformat()]
    if isinstance(value,date):return ['date',value.isoformat()]
    if isinstance(value,dict):
        # capture_version=1 is the original schema's implicit value. Preserve old
        # comparison/1 identities; explicit v2 is included and cannot collide.
        old_capture=(value.get('capture_version')==1 and 'snapshot_schema_version' in value
                     and 'request' in value and 'products' in value)
        return {k:_canonical(v) for k,v in sorted(value.items())
                if not (old_capture and k=='capture_version')
                and not (k=='operational_basis' and v is None and 'snapshot_schema_version' in value)}
    if isinstance(value,(list,tuple)):return [_canonical(v) for v in value]
    if value is None or type(value) in (str,int,bool):return value
    raise TypeError('Unsupported comparison identity value: '+type(value).__name__)


def _serialized(value):
    return json.dumps(_canonical(value),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def digest(value):
    return hashlib.sha256(_serialized(value).encode('utf-8')).hexdigest()


def plan_identity(request,candidate):
    # All capture/configuration is scoped by this invocation. Never money/view alone.
    return _serialized(dict(version='comparison_plan/1',context=request.model_dump(),
        basket=[b.model_dump() for b in candidate.basket],arrivals=[a.model_dump() for a in candidate.arrivals]))


def evaluation_identity(candidate):
    body=candidate.evaluation.model_dump()
    def row_key(row):
        return tuple(str(row.get(k,'')) for k in ('path_id','day','product_id','recipe_id','ingredient_id','lot_id'))
    for name in ('products','contributions','lots','ingredients'):
        body[name]=sorted(body[name],key=row_key)
    body['issues']=sorted(body['issues'],key=digest)
    bom=body['bom']
    for name in ('contributions','totals'):
        bom[name]=sorted(bom[name],key=row_key)
    bom['issues']=sorted(bom['issues'],key=digest)
    bom['paths']=sorted(bom['paths'],key=lambda p:p['path_id'])
    for path in bom['paths']:path['demands']=sorted(path['demands'],key=row_key)
    return _serialized(dict(version='comparison_evaluation/1',evaluation=body))


def daily_products(evaluation):
    return tuple(sorted(evaluation.products,key=lambda r:(r.path_id,r.day,r.product_id)))


def daily_ingredients(evaluation):
    return tuple(sorted(evaluation.ingredients,key=lambda r:(r.path_id,r.day,r.ingredient_id)))


def issues(evaluation):
    return tuple(sorted(evaluation.issues,key=lambda i:digest(i.model_dump())))


def option_token(request,candidate):
    return 'cmp1_'+digest(dict(version='comparison_option/1',plan=plan_identity(request,candidate),
                              evaluation=evaluation_identity(candidate)))


def outlay_breakdown(request,candidate):
    terms={t.id:t for t in request.prepared.supplier_terms}
    active=[(o,n) for o,n in zip(request.offers,candidate.counts) if n]
    purchase=total(exact(terms[o.term_id].pack_cost)*n for o,n in active)
    components=[]
    mode=request.policy.fee_mode
    if mode=='PER_OFFER':
        components=[FeeComponent(basis='OFFER',entity_id=o.term_id,amount=quantity(exact(o.payable_fee))) for o,n in active]
    elif mode=='PER_SUPPLIER_ORDER':
        active_suppliers={terms[o.term_id].supplier_id for o,n in active}
        components=[FeeComponent(basis='SUPPLIER_ORDER',entity_id=f.supplier_id,amount=quantity(exact(f.amount)))
                    for f in request.supplier_fees if f.supplier_id in active_suppliers]
    fees=total(q(c.amount) for c in components)
    all_in=total((purchase,fees))
    if all_in!=q(candidate.outlay):raise ValueError('Captured fee/purchase breakdown does not reconcile with outlay')
    return OutlayBreakdown(purchase=quantity(purchase),payable_fees=quantity(fees),
        delivery_fees=quantity(F(0)) if mode=='NONE' else None,
        fee_classification='NO_PAYABLE_FEES' if mode=='NONE' else 'PAYABLE_FEE_TYPE_NOT_CAPTURED',total=quantity(all_in),
        currency=candidate.currency,fee_mode=mode,components=tuple(components))
