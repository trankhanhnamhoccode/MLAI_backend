"""Finite read intents; no NLP truth extraction, model, live catalog or computation."""
import unicodedata
from dataclasses import dataclass
from uuid import UUID
from app.application.contracts.assistant_chat import (
    AssistantResponse, ChatClaim, ChatDiagnostics, Clarification, IngredientCandidate,OptionCandidate,
)
from app.application.contracts.plan_summary import SummaryDiagnostics
from app.application.plan_summary_rendering import render_summary


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.casefold().replace('đ','d'))
                   if unicodedata.category(c)!='Mn')


@dataclass(frozen=True)
class ChatScope:
    intent: str
    ingredient_id: UUID | None
    clarification: str | None = None
    candidates: tuple = ()
    option_id: str | None = None
    comparison_pair: tuple[str,str] | None = None
    option_candidates: tuple = ()
    product_candidates: tuple = ()


# Deliberately finite vocabulary. Unsupported/compound actions clarify, never execute.
INTENTS = (
    ('limitations',('thuc te','actual','xac suat','probability','loi nhuan','profit','nguyen nhan','cause','khong mua','zero-purchase')),
    ('ingredient',('nguyen lieu','ingredient','ton kho','stock','nhap','shortage','thieu','expiry','het han')),
    ('cost',('ngan sach','chi phi','tong chi','budget','cost','outlay','phi','fees','so sanh','compare')),
    ('requirements',('dap ung','yeu cau','service','requirements','fill rate')),
    ('coverage',('pham vi','menu','coverage','scope','bi loai','excluded')),
    ('proof',('toi uu','chung minh','proof','optimal','why selected','vi sao chon')),
    ('summary',('tom tat','summary','tong quan','overview')),
    ('outcome',('khuyen nghi','duoc chon','recommend','winner','selected','ket qua','result')),
)


def scope_question(request, evidence):
    question=normalized(request.question)
    all_rows=evidence.overview.ingredients
    if request.ingredient_id is not None and evidence.overview.scope is None:
        from app.application.contracts.planning_configuration import ConfigurationError
        raise ConfigurationError('COMPUTED_SCOPE_NOT_AVAILABLE',409)
    # Full retained names or canonical UUID only. Repeated names remain ambiguous.
    matched=tuple(i for i in all_rows if str(i.ingredient_id) in question or
                  (i.name and normalized(i.name) in question))
    explicit=request.ingredient_id
    if explicit is not None and not any(i.ingredient_id==explicit for i in all_rows):
        from app.application.contracts.planning_configuration import ConfigurationError
        raise ConfigurationError('INGREDIENT_NOT_IN_RUN',404)
    if explicit and matched and any(i.ingredient_id!=explicit for i in matched):
        return ChatScope('ingredient',explicit,'ENTITY_CONTEXT_MISMATCH',matched)
    if not explicit and len(matched)>1:
        return ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',matched)
    ingredient=explicit or (matched[0].ingredient_id if matched else None)
    mentioned=tuple(o for o in evidence.overview.options if o.option_id in request.question or
                    any(s in question.split() for s in o.source_strategies))
    if mentioned and any(evidence.option is None or o.option_id!=evidence.option.option_id for o in mentioned):
        return ChatScope('option',ingredient,'ENTITY_CONTEXT_MISMATCH')
    if any(s in question for s in ('dat hang','place order','thay doi','change budget','what-if','what if','neu tang','neu giam','ignore instructions','bo qua chi dan')):
        return ChatScope('unsupported',ingredient,'QUERY_UNSUPPORTED')
    intent=next((key for key,phrases in INTENTS if any(p in question for p in phrases)),None)
    if question in ('con no thi sao?','con no?','what about it?'):
        intent='ingredient'
    if ingredient and intent is None: intent='ingredient'
    # History is context only: user messages may identify an entity for a short
    # explicit follow-up. Assistant assertions are never imported as facts.
    if not ingredient and intent=='ingredient' and question in ('con no thi sao?','con no?','what about it?','ton kho thi sao?'):
        for message in reversed(request.history):
            if message.role!='user': continue
            text=normalized(message.content)
            rows=tuple(i for i in all_rows if str(i.ingredient_id) in text or (i.name and normalized(i.name) in text))
            if len(rows)==1: ingredient=rows[0].ingredient_id
            elif rows: return ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',rows)
            break
    if intent=='ingredient' and ingredient is None:
        return ChatScope('ingredient',None,'ENTITY_AMBIGUOUS',all_rows)
    return ChatScope(intent or 'unsupported',ingredient,None if intent else 'QUERY_UNSUPPORTED')


def render_chat(evidence, request, scope):
    vi=request.locale=='vi'
    identity=evidence.identity
    common=dict(run_id=identity.run_id,evidence_version=identity.aggregate_digest,
        result_digest=identity.result_digest,option_id=evidence.option.option_id if evidence.option else None,
        ingredient_id=scope.ingredient_id,locale=request.locale)
    if scope.clarification:
        question=((('Bạn muốn so sánh cặp phương án nào? Nêu hai option ID từ C03.' if vi else 'Which option pair do you mean? Provide two retained option IDs from C03.') if scope.intent=='option' else
                   ('Bạn muốn hỏi nguyên liệu nào? Chọn ID đã lưu trong Run.' if vi else 'Which retained Ingredient do you mean? Choose its ID.'))
                  if scope.clarification=='ENTITY_AMBIGUOUS' else
                  (('Phương án trong câu hỏi khác context hiện tại; hãy chọn option_id explicit.' if vi else 'The question and viewed option differ; choose an explicit option_id.') if scope.intent=='option' else
                   ('Nguyên liệu trong câu hỏi khác lựa chọn hiện tại; hãy xác nhận ID.' if vi else 'The question and selected Ingredient differ; confirm an ID.'))
                  if scope.clarification=='ENTITY_CONTEXT_MISMATCH' else
                  ('Tôi có thể giải thích kết quả, chi phí, yêu cầu, phạm vi, bằng chứng hoặc nguyên liệu của Run. Hãy chọn một câu hỏi trong phạm vi này.' if vi else
                   'I can explain this Run’s outcome, costs, requirements, scope, proof or Ingredients. Choose a question in that scope.'))
        clarification=Clarification(code=scope.clarification,question=question,
            candidates=tuple(IngredientCandidate(ingredient_id=i.ingredient_id,name=i.name) for i in scope.candidates if i.name),
            original_question=request.question,
            option_candidates=tuple(OptionCandidate(option_id=o.option_id,source_strategies=o.source_strategies) for o in scope.option_candidates))
        return AssistantResponse(**common,kind='clarification',source='deterministic_clarification',answer=question,
            claims=(),references=(),clarification=clarification,diagnostics=ChatDiagnostics(reason='EVIDENCE_INSUFFICIENT'))
    fallback=render_summary(evidence,request,SummaryDiagnostics(disposition='FALLBACK',reason='MODEL_DISABLED',requested_model=None))
    keys=('outcome','cost','requirements','coverage','proof','limitations') if scope.intent=='summary' else (scope.intent,'limitations')
    claims=[ChatClaim(text=c.text,evidence_ids=c.evidence_ids) for c in fallback.claims if c.family in keys]
    if scope.intent=='ingredient':
        row=evidence.ingredient
        assert row is not None and row.ingredient_id==scope.ingredient_id
        def claim(text,*pointers):
            ids=tuple(next(r.evidence_id for r in evidence.references if r.pointer==p) for p in pointers)
            claims.insert(0,ChatClaim(text=text,evidence_ids=ids))
        if row.purchases is None:
            text='Chưa có kết quả mua của phương án; không đồng nghĩa mua bằng không.' if vi else 'Option purchase evidence is unavailable; this does not mean zero purchases.'
        elif not row.purchases:
            text='Phương án đang xem không có dòng mua cho nguyên liệu này.' if vi else 'The viewed option has no purchase lines for this Ingredient.'
        else:
            lines='; '.join(f'{p.quantity.decimal_view} {p.unit}, '+('dự kiến đến ' if vi else 'planned arrival ')+str(p.arrival_date) for p in row.purchases)
            text=('Các dòng mua đề xuất: ' if vi else 'Proposed purchase lines: ')+lines+'.'
        claim(text,'/ingredient/purchases','/ingredient/selected_option_id')
        text=(f'Tồn chụp lúc {row.captured_stock.captured_at.isoformat()}: {len(row.captured_stock.lots)} lô, khai báo {row.captured_stock.scope_declaration}. Đây là ảnh chụp đã lưu, không phải tồn hiện tại. ' if vi else
              f'Retained stock captured at {row.captured_stock.captured_at.isoformat()}: {len(row.captured_stock.lots)} lots, declaration {row.captured_stock.scope_declaration}. This is retained stock, not live inventory. ')
        text+=('Số dư mô phỏng theo ngày chưa có.' if row.daily_balances is None else f'Có {len(row.daily_balances)} dòng số dư mô phỏng theo ngày/đường nhu cầu; xem C05 để giữ đúng ngày, đơn vị và đường.') if vi else (
            'Daily simulated balances are unavailable.' if row.daily_balances is None else f'{len(row.daily_balances)} daily/path simulated balance rows are retained; C05 preserves dates, units and paths.')
        claim(text,'/ingredient/captured_stock','/ingredient/daily_balances')
        if row.daily_balances:
            lines='; '.join(f'{d.day} / {d.path}: '+
                (f'thiếu {d.shortage.decimal_view} {d.unit}, cuối ngày {d.ending.decimal_view} {d.unit}' if vi else
                 f'shortage {d.shortage.decimal_view} {d.unit}, ending {d.ending.decimal_view} {d.unit}')
                for d in row.daily_balances)
            claim(('Mô phỏng đã lưu: ' if vi else 'Retained simulation: ')+lines+'.','/ingredient/daily_balances')
        if row.captured_stock.lots:
            lines='; '.join(f'{lot.lot_id}: {lot.quantity.decimal_view} {lot.unit}, '+
                ('hạn ' if vi else 'expiry ')+(str(lot.expiry_date) if lot.expiry_date else ('chưa biết' if vi else 'unknown'))
                for lot in row.captured_stock.lots)
            claim(('Các lô đã chụp: ' if vi else 'Captured lots: ')+lines+'.','/ingredient/captured_stock')
    used={r for c in claims for r in c.evidence_ids}
    for r in used: evidence.resolve(r)
    return AssistantResponse(**common,kind='answer',source='deterministic_fallback',
        answer='\n\n'.join(c.text for c in claims),claims=tuple(claims),
        references=tuple(r for r in evidence.references if r.evidence_id in used),clarification=None,
        diagnostics=ChatDiagnostics(reason='MODEL_DISABLED'))
