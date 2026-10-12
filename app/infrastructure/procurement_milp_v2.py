"""Per-Product v2 generator over unchanged progressive-serving/FEFO equations."""
from copy import deepcopy
from fractions import Fraction as F
import math
from app.infrastructure.procurement_milp import build, add, mul, var, exclude_vector
from app.application.contracts.procurement_v2 import SolverEvidenceV2
from app.application.procurement_solver_v2 import ProposalV2
from app.application.procurement_solver import NumericUnsupported
from app.application.use_cases.procurement_v2 import summary
from app.domain.decision.procurement_policy import PATH_FOR
from app.domain.decision.quantities import exact


def product_expressions(model,path):
    rows=[]
    for p in model.products:
        demand=sum((v for (s,d,product),v in model.demand.items() if s==path and product==p),F(0))
        if demand:
            served=add(*[e for (s,d,product),e in model.served.items() if s==path and product==p])
            rows.append((p,served,demand))
    return rows


def requirement_rows(model,requirements):
    rows=[]
    for r in requirements.paths:
        overrides={p.product_id:exact(p.target) for p in r.overrides}
        for p,served,demand in product_expressions(model,r.path):
            rows.append((served,demand*overrides.get(p,exact(r.minimum)),math.inf))
    return rows


class NativeProductSearch:
    def __init__(self,request,offers):
        self.base=build(request,offers)
        self.customer_rows=requirement_rows(self.base,request.requirements)
        self.target=deepcopy(self.base)
        self.fallback=deepcopy(self.base)
        self.minimum=None;self.mean=None

    def solve(self,strategy,phase,deadline):
        path=PATH_FOR[strategy]
        model=self.target if phase=='TARGET' else self.fallback
        extra=list(self.customer_rows)
        expressions=product_expressions(model,path)
        objective=model.money
        if phase=='TARGET':
            extra.extend((served,demand,math.inf) for p,served,demand in expressions)
        elif expressions:
            if self.minimum is None:
                z=model.v('minimum_product_fulfillment')
                for p,served,demand in expressions:model.row(add(mul(served,1/demand),mul(var(z),-1)),lower=0)
                self.minimum=z
            mean=mul(add(*[mul(served,1/demand) for p,served,demand in expressions]),F(1,len(expressions)))
            if phase=='FALLBACK_MIN':objective=mul(var(self.minimum),-1)
            elif phase=='FALLBACK_MEAN':objective=mul(mean,-1)
            elif phase!='FALLBACK_COST':raise ValueError('Unsupported v2 phase')
        x,evidence=model.solve(objective,deadline,extra)
        fields=evidence.model_dump();fields['phase']=phase
        try:counts=None if x is None else model.extract(x)
        except NumericUnsupported as error:
            error.solver_evidence=SolverEvidenceV2(**fields);raise
        fields['extracted_counts']=counts
        return ProposalV2(SolverEvidenceV2(**fields),counts)

    def accept(self,strategy,phase,candidate):
        if phase not in ('FALLBACK_MIN','FALLBACK_MEAN'):return
        minimum,mean=summary(candidate,PATH_FOR[strategy])
        if minimum is None:return
        # Freeze exact canonical incumbent levels, never a floating surrogate value.
        expressions=product_expressions(self.fallback,PATH_FOR[strategy])
        if phase=='FALLBACK_MIN':
            for p,served,demand in expressions:self.fallback.row(served,lower=demand*minimum)
        else:
            expr=mul(add(*[mul(served,1/demand) for p,served,demand in expressions]),F(1,len(expressions)))
            self.fallback.row(expr,lower=mean)

    def exclude(self,counts,*,phase,hard_invalid,customer_invalid):
        if phase=='TARGET':
            exclude_vector(self.target,counts)
            if hard_invalid or customer_invalid:exclude_vector(self.fallback,counts)
        else:
            exclude_vector(self.fallback,counts)
