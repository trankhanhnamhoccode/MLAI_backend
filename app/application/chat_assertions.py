"""Reconcile proposed slots; independently inspect prose material predicates.

This is a bounded surface checker, not general language entailment. Unknown
material text regenerates/falls back; structured proposals alone never suffice.
Legacy full-clause grammar remains only for its supported non-numeric subset.
"""
from dataclasses import dataclass
from decimal import Decimal
import re
from app.application.assistant_chat_rendering import normalized
from app.application.chat_grounding import alternatives, norm, GroundingFailure
from app.application.conversational_evidence import display_fact
from app.application.contracts.chat_generation import SemanticOutput,ProposedAssertion
from app.application.contracts.assistant_chat import ChatClaim,AssistantResponse


UNAVAILABLE={'no_winner','failed','failed_unknown','blocked','purchase_unknown','cost_unknown','comparison_unknown','proof_unknown','detail_unknown'}


def proposal(card,text=None):
    return ProposedAssertion(fact_id=card.fact_id,value=card.display,unit=card.unit,entity_id=card.entity_id,path=card.path,
        option_role=card.option_role,polarity='unavailable' if card.kind in UNAVAILABLE else 'affirmed',text=text or display_fact(card)+'.')


@dataclass(frozen=True)
class Inspection:
    output: SemanticOutput | None
    disposition: str
    failures: tuple[str,...]


def surface_error(assertion,card,locale,*,wrong_number=False):
    if card.kind=='mechanistic' and card.label and card.path:
        # One full alternate grammatical construction, derived from this scoped
        # retained row. No wildcard/token stripping or slot-only acceptance.
        expected=display_fact(card,locale).rstrip('.')
        if locale=='vi':
            prefix=f'Mô phỏng {card.label}, {card.path}: '
            if expected.startswith(prefix):
                body=expected[len(prefix):].split('; ')
                if len(body)==3:
                    alternate=f'Mô phỏng cho {card.label}, {card.path}, {body[0]}, {body[1]} và {body[2]}'
                    if normalized(assertion.text).rstrip('.! ')==normalized(alternate).rstrip('.! '):return None
    if card.presentation is not None:
        # Group/label prose is checked as a complete clause independently from
        # typed slots. No fact-ID whitelist, partial-token or numeric-only pass.
        return None if normalized(assertion.text).rstrip('.! ')==normalized(card.presentation).rstrip('.! ') else 'UNVERIFIED_PRESENTATION'
    text=assertion.text.strip()
    if text.endswith('?'):return 'NOT_AN_ANSWER'
    q=normalized(text)
    # A scoped double negation affirms existence; do not reject a true amount
    # merely because it contains "không". Other/nested scopes remain unverified.
    if q.startswith('khong phai khong co '):q=q[len('khong phai khong co '):]
    expected_text=norm(display_fact(card,locale)).rstrip('.! ')
    # Presentation punctuation cannot change the retained option or negative
    # reason. Match the whole scoped clause; no token removal or fact-ID bypass.
    if card.kind=='rejection' and ': ' in expected_text:
        if norm(text).rstrip('.! ')==expected_text.replace(': ',' ',1):return None
    if card.kind=='detail_unknown':
        expected=normalized(display_fact(card,locale)).rstrip('.! ')
        prefix='evidence dang dung chua co bang chung nhan qua '
        # Within the already-resolved Run question, this scoped omission has a
        # bounded equivalent expression. Preserve the entire remaining clause,
        # including zero-purchase scope and proposal qualification.
        if expected.startswith(prefix) and normalized(text).rstrip('.! ')==expected.replace('evidence dang dung chua co ','khong co ',1):return None
    # Each proposed assertion must be atomic. Internal legacy proof punctuation
    # is handled by the supported grammar below, never by a wildcard.
    if card.display is None or card.kind in ('blocker','detail_unknown','gap','service','coverage'):
        if norm(text).rstrip('.! ')==norm(display_fact(card,locale)):return None
        # Bounded meaning-preserving presentation synonyms; all material values,
        # names, status, direction and negative/proof scope remain exact.
        def equivalent(value):
            value=normalized(value).rstrip('.! ')
            for source,target in (('it nhat','toi thieu'),('thoa man','dap ung'),
                                  ('theo danh gia da luu','theo danh gia duoc luu'),
                                  ('duoc luu','da luu')):
                value=value.replace(source,target)
            return value
        if equivalent(text)==equivalent(display_fact(card,locale)):return None
        try:
            if any(re.fullmatch(p,norm(text).rstrip('.! ')) for p in alternatives(card,locale)):return None
        except KeyError:pass
        return 'UNVERIFIED_MATERIAL_PROSE'
    numeric={'total','purchase_cost','fees','budget','purchase_quantity','stock_lot','daily_shortage','daily_ending','pair_cost','pair_service'}
    if card.kind not in numeric:
        if any(re.fullmatch(p,norm(text).rstrip('.! ')) for p in alternatives(card,locale)):return None
        return 'UNVERIFIED_MATERIAL_PROSE'
    if re.search(r'\b(khong|chua|not|no|never|khong phai|vi|because|nen|therefore|xac suat|probability|toi uu|optimal|da nhan|received|thuc te|actually)\b',q):return 'POLARITY_OR_EXTRA_CLAIM'
    if card.option_role!='recommended' and ('khuyen nghi' in q or 'recommended' in q):return 'WRONG_OPTION_ROLE'
    if card.kind in ('stock_lot','daily_shortage','daily_ending') and ('hien tai' in q or 'current' in q):return 'CAPTURED_IS_NOT_CURRENT'
    predicates={
        'total':('tong','ton','total','outlay','het','khoan tien phai chi'), 'purchase_cost':('chi phi mua','tien mua','tien hang','purchase cost'),
        'fees':('phi','fees'), 'budget':('ngan sach','budget'), 'purchase_quantity':('mua','purchase','buy'),
        'stock_lot':('ton','stock'), 'daily_shortage':('thieu','shortage'), 'daily_ending':('cuoi ngay','ending'),
        'pair_cost':('chenh','delta','cao hon','thap hon'), 'pair_service':('phuc vu','fulfilled'),
    }
    if not any(p in q for p in predicates[card.kind]):return 'WRONG_PREDICATE'
    if card.kind.startswith('pair_'):
        value=Decimal(card.display)
        if any(w in q.split() for w in ('tang','increase')) and value<=0:return 'WRONG_PAIR_DIRECTION'
        if any(w in q.split() for w in ('giam','decrease')) and value>=0:return 'WRONG_PAIR_DIRECTION'
        if 'cao hon' in q and value<=0:return 'WRONG_PAIR_DIRECTION'
        if 'thap hon' in q and value>=0:return 'WRONG_PAIR_DIRECTION'
        if card.kind=='pair_service' and not any(w in q for w in ('chenh','delta','tang','giam','increase','decrease','cao hon','thap hon')):return 'DELTA_NOT_ABSOLUTE'
        if 'da' in q.split() and not any(w in q for w in ('mo phong','simulated')):return 'ACTUAL_NOT_SIMULATED'
    # Do not accept "budget" as total outlay or purchase quantity as stock.
    forbidden={ 'total':('ngan sach','budget','tien mua','purchase cost','phi phai tra'),
        'budget':('tong chi','total cost','phi phai tra'), 'purchase_quantity':('ton kho','stock','tong chi','budget'),
        'fees':('tien mua','purchase cost','ngan sach','budget'), 'purchase_cost':('ngan sach','budget','tong chi'),
        'stock_lot':('mua','purchase','buy'),'daily_shortage':('cuoi ngay','ending'),'daily_ending':('thieu','shortage')}
    if any(p in q for p in forbidden.get(card.kind,())):return 'CONTRADICTORY_PREDICATE'
    # Bind every material identity/path/label before scanning numbers or words.
    for value,mandatory in ((card.entity_id,card.kind!='purchase_quantity'),(card.path,True),(card.label,False)):
        if not value:continue
        value=normalized(value)
        if mandatory and value not in q:
            if card.kind=='pair_cost':continue # server binds the one sealed pair below
            if card.kind=='pair_service' and card.label and normalized(card.label) in q and value==normalized(card.entity_id):continue
            return 'MISSING_ENTITY_OR_PATH'
        q=q.replace(value,' ')
    units={'VND':('vnd','dong')}.get(card.unit,(normalized(card.unit or ''),))
    amounts=list(re.finditer(r'(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])',q.rstrip('.')))
    if len(amounts)!=1:return 'EXTRA_OR_MISSING_NUMBER'
    found=amounts[0]
    expected=card.display
    if card.kind.startswith('pair_') and (any(w in q.split() for w in ('giam','decrease')) or 'thap hon' in q):expected=format(abs(Decimal(expected)),'f')
    if not wrong_number and found.group()!=expected:return 'WRONG_VALUE'
    # Unit is tied to that quantity, not merely present somewhere in the text.
    tail=q[found.end():].lstrip()
    unit=next((u for u in units if u and re.match(re.escape(u)+r'\b',tail)),None)
    if unit is None:return 'WRONG_UNIT'
    if re.match(re.escape(unit)+r'\b',tail[len(unit):].lstrip()):return 'DUPLICATE_UNIT'
    q=q[:found.start()]+' '+q[found.end():]
    q=re.sub(r'\b'+re.escape(unit)+r'\b',' ',q,count=1)
    # Role/scope and numeric predicates are checked above; residual tokens must
    # belong to a small non-authoritative connective/presentation vocabulary.
    allowed=set(('tong chi phi tien mua hang ngan sach gioi han can de xuat luong so phai tra cua cho la bang co voi '
        'phuong an ke hoach nay dang xem duoc khuyen nghi nguyen lieu ban nen se het ton kho lo chup da luu '
        'mo phong du kien thieu cuoi ngay theo con o tai vao tuong ung rieng muc do khoan '
        'the this viewed option plan proposed purchase quantity cost total outlay budget limit fee fees is of for '
        'to buy need should amount captured stock lot simulated shortage ending retained available').split())
    if card.kind.startswith('pair_'):
        allowed.update('chenh lech phuc vu mon duong tren tang giam sau tru truoc delta fulfilled product path increase decrease minus cao thap hon dat'.split())
    tokens=set(re.findall(r'\w+',q))
    if tokens-allowed:return 'UNVERIFIED_EXTRA_WORDS'
    if card.kind=='stock_lot' and not any(p in normalized(text) for p in ('chup','captured','da luu')):return 'MISSING_CAPTURE_SCOPE'
    if card.kind.startswith('daily_') and not any(p in normalized(text) for p in ('mo phong','simulated')):return 'MISSING_SIMULATION_SCOPE'
    return None


def inspect_output(output,plan,locale,*,allow_repair=True):
    if plan.version=='chat_evidence/7':
        from app.application.chat_assertions_v7 import inspect_output as legacy
        return legacy(output,plan,locale,allow_repair=allow_repair)
    if plan.version=='chat_evidence/6':
        from app.application.chat_assertions_v6 import inspect_output as legacy
        return legacy(output,plan,locale,allow_repair=allow_repair)
    if plan.version=='chat_evidence/5':
        from app.application.chat_assertions_v5 import inspect_output as legacy
        return legacy(output,plan,locale,allow_repair=allow_repair)
    if plan.version=='chat_evidence/4':
        from app.application.chat_assertions_v4 import inspect_output as legacy
        return legacy(output,plan,locale,allow_repair=allow_repair)
    if plan.version!='chat_evidence/8':
        from app.application.chat_assertions_v3 import inspect_output as legacy
        return legacy(output,plan,locale,allow_repair=allow_repair)
    output=SemanticOutput.model_validate(output);facts={f.fact_id:f for f in plan.facts}
    accepted=[];covered=set();failures=[];repaired=False;trimmed=False
    for index,a in enumerate(output.assertions):
        card=facts.get(a.fact_id)
        if card is None:return Inspection(None,'FALLBACK',tuple((*failures,f'{index}:UNKNOWN_FACT')))
        expected=proposal(card)
        slots=('unit','entity_id','path','option_role','polarity')
        error=next(('WRONG_'+k.upper() for k in slots if getattr(a,k)!=getattr(expected,k)),None)
        if card.kind.startswith('pair_') and 'phuong an dat hon' in normalized(a.text):
            cost=next((f for f in plan.facts if f.kind=='pair_cost'),None)
            if cost is None or Decimal(cost.display)<=0:error=error or 'WRONG_PAIR_COST_ROLE'
        error=error or surface_error(a,card,locale)
        if a.value!=card.display:error=error or 'WRONG_VALUE'
        if error=='WRONG_VALUE' and allow_repair and card.display is not None and surface_error(a,card,locale,wrong_number=True) is None:
            # Identity/role/unit must already be exact. Exactly one amount token
            # is replaced from that one sealed fact; never nearest-number search.
            if all(getattr(a,k)==getattr(expected,k) for k in slots):
                text=a.text
                for entity in (card.entity_id,card.path,card.label):
                    if entity and any(c.isdigit() for c in entity):break
                else:
                    text=re.sub(r'(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])',card.display,text,count=1)
                    fixed=a.model_copy(update={'value':card.display,'text':text})
                    if surface_error(fixed,card,locale) is None:
                        failures.append(f'{index}:WRONG_VALUE_REPAIRED');a=fixed;error=None;repaired=True
        if error:
            # Public diagnostics retain position/reason/scoped fact, never raw
            # rejected prose. Opt-in evaluation artifacts join these to raw output.
            failures.append(f'{index}:{error}:fact={a.fact_id}')
            if allow_repair and a.fact_id not in plan.required:
                trimmed=True;continue
            return Inspection(None,'FALLBACK',tuple(failures))
        if a.fact_id in covered:
            if allow_repair:trimmed=True;failures.append(f'{index}:REDUNDANT_ASSERTION_TRIMMED');continue
            return Inspection(None,'FALLBACK',tuple((*failures,f'{index}:DUPLICATE')))
        accepted.append(a);covered.add(a.fact_id)
    missing=set(plan.required)-covered
    if missing:return Inspection(None,'FALLBACK',tuple((*failures,*(f'{k}:MISSING_MAIN_OBLIGATION' for k in sorted(missing)))))
    if not accepted:return Inspection(None,'FALLBACK',tuple((*failures,'EMPTY_ANSWER')))
    final=SemanticOutput(assertions=tuple(accepted))
    if allow_repair and (repaired or trimmed):
        checked=inspect_output(final,plan,locale,allow_repair=False)
        if checked.output is None:return checked
    return Inspection(final,'REPAIRED' if repaired else 'TRIMMED' if trimmed else 'ACCEPTED',tuple(failures))


def semantic_answer(output,plan,diagnostics):
    if plan.version=='chat_evidence/7':
        from app.application.chat_assertions_v7 import semantic_answer as legacy
        return legacy(output,plan,diagnostics)
    if plan.version=='chat_evidence/6':
        from app.application.chat_assertions_v6 import semantic_answer as legacy
        return legacy(output,plan,diagnostics)
    if plan.version=='chat_evidence/5':
        from app.application.chat_assertions_v5 import semantic_answer as legacy
        return legacy(output,plan,diagnostics)
    if plan.version=='chat_evidence/4':
        from app.application.chat_assertions_v4 import semantic_answer as legacy
        return legacy(output,plan,diagnostics)
    if plan.version!='chat_evidence/8':
        from app.application.chat_assertions_v3 import semantic_answer as legacy
        return legacy(output,plan,diagnostics)
    checked=inspect_output(output,plan,plan.fallback.locale,allow_repair=False)
    if checked.output is None:raise GroundingFailure('GROUNDING_REJECTED')
    facts={f.fact_id:f for f in plan.facts}
    claims=tuple(ChatClaim(text=a.text,evidence_ids=facts[a.fact_id].evidence_ids) for a in checked.output.assertions)+plan.safety_claims
    if any(facts[a.fact_id].kind=='purchase_quantity' for a in checked.output.assertions) and not any(
        p in normalized(' '.join(c.text for c in claims)) for p in ('de xuat','proposed')):
        ids=tuple(dict.fromkeys(i for a in checked.output.assertions for i in facts[a.fact_id].evidence_ids))
        claims+=(ChatClaim(text='Đây là lượng mua đề xuất theo phương án đang xem.' if plan.fallback.locale=='vi' else 'These are proposed purchases for the viewed option.',evidence_ids=ids),)
    refs={i for c in claims for i in c.evidence_ids}
    # Optional supporting facts need references too, beyond fallback main claims.
    return AssistantResponse(**{**plan.fallback.model_dump(),'source':'model','answer':'\n\n'.join(c.text for c in claims),
        'claims':claims,'references':tuple(r for r in plan.fallback.references if r.evidence_id in refs),'diagnostics':diagnostics})
