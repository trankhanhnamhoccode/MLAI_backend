"""PLAN14 atomic config mutations, fenced by current User/Store/membership locks."""
import hashlib
from uuid import UUID, uuid4
from app.application.contracts import planning_configuration as dto
from app.application.contracts.auth import AuthError
from app.application.import_identity import content_digest
from app.application.planning_configuration_values import resolve_save, detail
from app.application.recipe_schedule_plan import exact
from app.infrastructure.database.auth_session import auth_session
from app.models.planning_configuration import (SavedRequirement,PlanningBudget,PlanningConfigurationEvent,
    PlanningConfigurationRevision,PlanningConfigurationReceipt)
from app.repositories.planning_configuration import configuration_rows,default_record,saved_row,fence_save_products

READS=('planning.requirements.read','budget.read')


def headers(key, match, none, *, budget=False, create=False):
    try:
        if key is None or str(UUID(key)) != key:
            raise ValueError()
        if match is not None and none is not None:
            raise ValueError()
        if none is not None and (not budget or none != '*'):
            raise ValueError()
        if match is not None and (len(match)<3 or match[0]!='"' or match[-1]!='"' or any(c in match[1:-1] for c in ('"',',','*')) or len(match[1:-1])>128):
            raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise dto.ConfigurationError('INVALID_REQUEST',400) from None
    if not create and match is None and none is None:
        raise dto.ConfigurationError('PRECONDITION_REQUIRED',428)
    return hashlib.sha256(key.encode()).hexdigest(),match[1:-1] if match else None


class PlanningConfigurationWrites:
    def __init__(self,auth):
        self.auth,self.engine=auth,auth.engine

    def read(self,token,store,ident):
        with auth_session(self.engine) as s:
            self.auth.authorize_in_session(s,token,store,READS)
            row=saved_row(s,store,ident)
            if row is None:
                raise AuthError('RESOURCE_NOT_FOUND',404)
            defaults,cap,products=configuration_rows(s,store)
            result=detail(row,default_record(defaults),cap,products)
            s.commit()
            return result

    def _authorize(self,s,token,store,ident,budget,create,csrf):
        required=('budget.update','budget.read') if budget else (*READS,'planning.requirements.create' if create else 'planning.requirements.manage')
        actor,summary,_=self.auth.authorize_in_session(s,token,store,required,csrf=csrf)
        row=None if budget or create else saved_row(s,store,ident)
        if not budget and not create:
            if row is None:
                raise AuthError('RESOURCE_NOT_FOUND',404)
            if summary.role!='OWNER' and row.created_by!=actor.user_id:
                raise AuthError('PERMISSION_DENIED')
        return actor,summary,row

    @staticmethod
    def _replay(s,identity,digest,budget):
        receipt=s.get(PlanningConfigurationReceipt,identity)
        if receipt is None:
            return None
        if receipt.request_digest!=digest:
            raise dto.ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
        model=dto.BudgetResult if budget else dto.SavedDetail
        return model.model_validate(receipt.record_json),receipt.status_code

    def write(self,token,store,body,key,csrf,*,ident=None,match=None,none=None,request_id):
        budget=isinstance(body,dto.BudgetRequest)
        create=not budget and ident is None
        kd,version=headers(key,match,none,budget=budget,create=create)
        if create and (match is not None or none is not None):
            raise dto.ConfigurationError('INVALID_REQUEST',400)
        operation='PUT/budget' if budget else 'POST/saved' if create else 'PUT/saved/'+str(ident)
        digest=content_digest(dict(body=body.model_dump(mode='json',exclude_unset=True),match=match,none=none))
        try:
            with auth_session(self.engine) as s:
                actor,summary,row=self._authorize(s,token,store,ident,budget,create,csrf or '')
                identity=(actor.user_id,store,operation,kd)
                old=self._replay(s,identity,digest,budget)
                if old is not None:
                    s.commit()
                    return *old,True
                if not budget and not isinstance(body,dto.ArchiveRequest):
                    fence_save_products(s)
                defaults,cap,products=configuration_rows(s,store)
                now=self.auth.clock()
                before=None
                if budget:
                    if (none=='*' and cap is not None) or (none is None and (cap is None or version!=cap.version)):
                        raise dto.ConfigurationError('CONFIGURATION_VERSION_CHANGED',412)
                    before=dto.BudgetResult(store_id=store,budget_ceiling=dto.BudgetCeiling(amount=cap.amount,currency=summary.currency,version=cap.version,updated_at=cap.updated_at)) if cap else None
                    changed=cap is None or exact(body.amount)!=exact(cap.amount)
                    status=201 if cap is None else 200
                    if changed:
                        if cap is None:
                            cap=PlanningBudget(store_id=store)
                            s.add(cap)
                        cap.amount,cap.version,cap.updated_at,cap.updated_by=exact(body.amount),str(uuid4()),now,actor.user_id
                        s.flush()
                    result=dto.BudgetResult(store_id=store,budget_ceiling=dto.BudgetCeiling(amount=cap.amount,currency=summary.currency,version=cap.version,updated_at=cap.updated_at))
                    resource='budget'
                else:
                    defaults=default_record(defaults)
                    if not create and row.version!=version:
                        raise dto.ConfigurationError('CONFIGURATION_VERSION_CHANGED',412)
                    before=detail(row,defaults,cap,products) if row else None
                    status=201 if create else 200
                    if isinstance(body,dto.ArchiveRequest):
                        changed=row.state!='archived'
                        if changed:
                            row.state='archived'
                    else:
                        if row and row.state=='archived':
                            raise dto.ConfigurationError('SAVED_REQUIREMENTS_ARCHIVED',409)
                        requirements,reference=resolve_save(body,defaults,cap,products)
                        values=requirements.model_dump(mode='json')
                        ref=reference.model_dump(mode='json') if reference else None
                        changed=create or (row.name,row.requirements_json,row.default_reference_json)!=(body.name,values,ref)
                        if create:
                            row=SavedRequirement(id=uuid4(),store_id=store,state='active',created_at=now,created_by=actor.user_id)
                            s.add(row)
                        if changed:
                            row.name,row.requirements_json,row.default_reference_json=body.name,values,ref
                    if changed:
                        row.version,row.updated_at,row.updated_by=str(uuid4()),now,actor.user_id
                    s.flush()
                    result=detail(row,defaults,cap,products)
                    resource='saved/'+str(row.id)
                if changed:
                    output=result.model_dump(mode='json')
                    result_version=result.budget_ceiling.version if budget else result.version
                    s.add(PlanningConfigurationRevision(store_id=store,resource=resource,version=result_version,record_json=output))
                    s.add(PlanningConfigurationEvent(id=uuid4(),store_id=store,actor_id=actor.user_id,occurred_at=now,
                        record_json=dict(action=operation,resource=resource,request_id=request_id,before=before.model_dump(mode='json') if before else None,after=output)))
                s.add(PlanningConfigurationReceipt(actor_id=actor.user_id,store_id=store,operation=operation,key_digest=kd,
                    request_digest=digest,status_code=status,record_json=result.model_dump(mode='json')))
                s.flush()
                s.commit()
                return result,status,False
        except (AuthError,dto.ConfigurationError):
            raise
        except Exception:
            # Resolve uncertain commit acknowledgment using durable evidence, never
            # by executing the operation a second time in this request.
            try:
                with auth_session(self.engine) as fresh:
                    actor,_,_=self._authorize(fresh,token,store,ident,budget,create,csrf or '')
                    old=self._replay(fresh,(actor.user_id,store,operation,kd),digest,budget)
                    if old is not None:
                        fresh.commit()
                        return *old,True
            except (AuthError,dto.ConfigurationError):
                raise
            except Exception:
                pass
            raise dto.ConfigurationError('SERVICE_UNAVAILABLE',503) from None
