"""Scoped, optional elapsed observation; no application computation or policy changes."""
from contextlib import contextmanager
from functools import wraps
import sys
from time import perf_counter


class Observer:
    def __init__(self, *, enabled=True, clock=perf_counter):
        self.enabled=enabled
        self.clock=clock
        self.phase='startup'
        self.stack=[]
        self.rows={}
        self.events=[]
        self.restores=[]
        self.planning_executions=0
        self.native_inferences=0
        self.cache={'hit':0,'miss':0}

    @contextmanager
    def span(self,name):
        if not self.enabled:
            yield;return
        frame=[self.clock(),0.]
        self.stack.append(frame)
        try:yield
        finally:
            elapsed=self.clock()-frame[0]
            self.stack.pop()
            if self.stack:self.stack[-1][1]+=elapsed
            key=self.phase+' / '+name
            row=self.rows.setdefault(key,dict(calls=0,inclusive_seconds=0.,exclusive_seconds=0.))
            row['calls']+=1;row['inclusive_seconds']+=elapsed
            row['exclusive_seconds']+=max(0.,elapsed-frame[1])

    def wrap(self,function,name,*,before=None,after=None):
        if not self.enabled:return function
        @wraps(function)
        def observed(*args,**kwargs):
            with self.span(name):
                if before:before(*args,**kwargs)
                result=function(*args,**kwargs)
                if after:after(result,*args,**kwargs)
                return result
        return observed

    def aliases(self,function,name,**options):
        if not self.enabled:return
        replacement=self.wrap(function,name,**options)
        for module_name,module in tuple(sys.modules.items()):
            if module_name.startswith('app.') and module is not None:
                for attribute,value in tuple(vars(module).items()):
                    if value is function:
                        self.restores.append((module,attribute,value))
                        setattr(module,attribute,replacement)

    def method(self,owner,attribute,name,**options):
        if self.enabled:
            original=getattr(owner,attribute)
            self.restores.append((owner,attribute,original))
            setattr(owner,attribute,self.wrap(original,name,**options))

    def restore(self):
        for owner,attribute,value in reversed(self.restores):setattr(owner,attribute,value)
        self.restores.clear()

    def resource(self,kind):
        if kind=='planning':
            if self.planning_executions>=3:raise RuntimeError('PLANNING_CAP')
            self.planning_executions+=1
        elif kind=='native':
            if self.native_inferences>=2:raise RuntimeError('NATIVE_INFERENCE_CAP')
            self.native_inferences+=1
        else:raise ValueError('Unknown resource')

    def snapshot(self):
        return dict(timings=self.rows,events=self.events,planning_executions=self.planning_executions,
            native_inferences=self.native_inferences,cache=self.cache,
            accounting='Inclusive rows overlap; exclusive rows subtract only observed child spans. Never sum inclusive rows.')


def install(observer,persist):
    """Patch aliases only for this dedicated offline profiling process; restore all."""
    from app.application.use_cases import bom,serving,procurement_v2,procurement_selection
    from app.application import procurement_v2_validation,serving_validation
    from app.application import forecast_challenger_validation
    from app.application.use_cases import forecast_challenger
    from app.domain.decision import serving as domain_serving
    from app.infrastructure import procurement_milp,procurement_milp_v2
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    import lightgbm

    def native_before(*args,**kwargs):observer.resource('native');persist()
    def native_solve_after(result,*args,**kwargs):
        observer.events.append(dict(phase=observer.phase,kind='native_search_call',strategy=args[1],stage=args[2],
            evidence=result.evidence.model_dump(mode='json')))
        persist()
    def cache_after(result,*args,**kwargs):observer.cache['miss' if result is None else 'hit']+=1
    for function,name in (
        (bom.expand_bom,'BOM'),(serving.simulate_serving,'exact_serving_application'),
        (domain_serving.simulate,'exact_serving_FEFO_domain'),
        (procurement_v2.execute_procurement_v2,'procurement_orchestration'),
        (procurement_v2_validation.validate_result,'semantic_procurement_revalidation'),
        (serving_validation.validate_result,'semantic_serving_revalidation'),
        (procurement_selection.compare_procurement_v2,'comparison'),
        (procurement_selection.select_winner,'selector'),
        (procurement_selection.validate_comparison,'semantic_comparison_revalidation'),
        (forecast_challenger_validation.validate_output,'forecast_output_validation'),
        (procurement_milp.milp,'scipy_milp_native_elapsed')):
        observer.aliases(function,name)
    observer.aliases(forecast_challenger.infer_native,'native_forecast_inference',before=native_before)
    observer.method(forecast_challenger.ForecastChallenger,'_admit','input_admission_runtime_pin')
    observer.method(procurement_milp_v2.NativeProductSearch,'solve','native_search_solve',after=native_solve_after)
    observer.method(procurement_milp.Model,'solve','MILP_build_conversion_solve')
    observer.method(lightgbm.Booster,'__init__','booster_loading')
    observer.method(ChallengerStorage,'load_artifact','artifact_IO_hash_loading')
    observer.method(ChallengerStorage,'load_evidence','forecast_retained_read',after=cache_after)
    observer.method(ChallengerStorage,'retain','forecast_serialization_storage')
