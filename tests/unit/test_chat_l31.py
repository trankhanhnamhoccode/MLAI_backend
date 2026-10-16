"""Hand-labelled facts/obligations, not labels derived from the validator."""
from uuid import UUID
from decimal import Decimal
import pytest
from tests.assistant_cases import realistic_record,retained_record,row_for
from app.application.planning_public_projection import project_run
from app.application.decision_evidence_projection import project_evidence
from app.application.chat_context import resolve_context
from app.application.conversational_evidence import select_evidence
from app.application.chat_assertions import proposal,inspect_output,semantic_answer
from app.application.contracts.chat_generation import SemanticOutput
from app.application.contracts.assistant_chat import ChatRequest,ChatDiagnostics


def case(question='Kế hoạch này tốn bao nhiêu?',*,context=None,ingredient=None,option=None,kind='realistic',history=()):
    r=realistic_record() if kind=='realistic' else retained_record(kind)
    v=project_run(r,response_version=row_for(r).record_digest)
    req=ChatRequest(expected_evidence_version=v.response_version,option_id=option,locale='vi',detail_level='simple',question=question,
        ingredient_id=ingredient,history=history,context=context)
    e=project_evidence(r,v,option_id=v.result.winner_option_id if v.result else None,include_comparisons=True)
    effective,s,c=resolve_context(req,e)
    if not s.clarification and s.ingredient_id:e=project_evidence(r,v,ingredient_id=s.ingredient_id,option_id=s.option_id,include_comparisons=True)
    return select_evidence(e,effective,s,c),req,e


def test_current_question_explicit_identity_conflicts_clarify_not_answer_wrong_scope():
    p,_,_=case('Sữa đặc cần mua bao nhiêu?',ingredient=UUID(int=200))
    assert p.fallback.kind=='clarification' and p.fallback.clarification.code=='ENTITY_CONTEXT_MISMATCH'
    _,_,e=case();other=next(o.option_id for o in e.overview.options if o.option_id!=e.option.option_id)
    p,_,_=case('Chi phí phương án '+other+'?',option=e.option.option_id)
    assert p.fallback.kind=='clarification' and p.fallback.clarification.code=='ENTITY_CONTEXT_MISMATCH'


def valid(plan):return SemanticOutput(assertions=tuple(proposal(c) for c in plan.facts if c.fact_id in plan.required))


def test_multi_turn_milk_clarification_original_question_stock_and_entity_switch():
    p,_,_=case('Sữa cần mua bao nhiêu?')
    assert p.fallback.kind=='clarification'
    assert {i.name for i in p.fallback.clarification.candidates}=={'Sữa tươi','Sữa đặc'}
    ctx=p.fallback.context
    p,_,_=case('Sữa tươi',context=ctx)
    assert p.ingredient_id==UUID(int=200) and {f.kind for f in p.facts}=={'purchase_quantity'}
    assert p.fallback.context.pending is None and '20 g' in p.fallback.answer
    p,_,_=case('Còn nó đang tồn bao nhiêu?',context=p.fallback.context)
    assert {f.kind for f in p.facts}=={'stock_lot'} and 'mua' not in p.fallback.answer
    p,_,_=case('Đổi sang sữa đặc thì sao?',context=p.fallback.context)
    assert p.ingredient_id==UUID(int=201) and {f.kind for f in p.facts}=={'stock_lot'}


def test_context_foreign_run_unknown_id_multiple_antecedents_and_explicit_priority():
    p,_,_=case('Sữa tươi cần mua bao nhiêu?');ctx=p.fallback.context
    p,_,_=case('Còn nó?',context=ctx.model_copy(update={'run_id':UUID(int=123)}))
    assert p.fallback.kind=='clarification'
    with pytest.raises(Exception) as e:case('Còn nó?',context=ctx.model_copy(update={'ingredient_id':UUID(int=999)}))
    assert e.value.code=='INGREDIENT_NOT_IN_RUN'
    p,_,_=case('Còn nó cần mua bao nhiêu?',history=({'role':'user','content':'Sữa tươi và sữa đặc'},))
    assert p.fallback.kind=='clarification'
    p,_,_=case('Sữa đặc cần mua bao nhiêu?',context=ctx)
    assert p.ingredient_id==UUID(int=201)


def test_two_options_actual_pair_deltas_independent_oracle_and_direction():
    p,_,e=case('Phương án khác đắt hơn được lợi gì?')
    assert len(e.overview.options)==2
    pair=e.overview.comparisons[0]
    assert pair.total_outlay_delta.decimal_view==Decimal('5')
    assert {(d.unit,d.fulfilled.decimal_view) for d in pair.products}=={('cup',Decimal('5')),('cup',Decimal('10'))}
    assert len(p.required)==7 and inspect_output(valid(p),p,'vi').output


def test_main_cost_obligation_does_not_require_all_optional_facts_or_disclaimer():
    p,_,_=case()
    assert {f.kind for f in p.facts if f.fact_id in p.required}=={'total'}
    assert inspect_output(valid(p),p,'vi').output
    assert '0 cảnh báo' not in p.fallback.answer and 'xác suất' not in p.fallback.answer


@pytest.mark.parametrize('text',[
    'Tổng số tiền cần chi cho phương án này là 10 VND.',
    'Theo phương án đang xem, tổng chi là 10 đồng.',
    'Kế hoạch này tốn 10 VND.',
    'Không phải không có tổng chi 10 VND.',
])
def test_independently_authored_cost_paraphrases(text):
    p,_,_=case();c=next(f for f in p.facts if f.kind=='total')
    checked=inspect_output(SemanticOutput(assertions=(proposal(c,text),)),p,'vi')
    assert checked.output is not None,checked.failures


@pytest.mark.parametrize('text',[
    'Ngân sách là 10 VND.', 'Tổng chi là 10 kg.',
    'Tổng chi không phải là 10 VND.', 'Tổng chi là 10 VND vì sữa tăng giá.',
    'Tổng chi là 10 VND; phương án này tối ưu toàn cục.',
    'Tổng chi là 10 VND và xác suất hết hàng là 0%.',
    'Tổng chi là 10 VND; dữ liệu đã được cung cấp.',
    'Tổng chi là 10 VND cho Sữa đặc.',
])
def test_correct_number_wrong_assertion_or_extra_material_is_rejected(text):
    p,_,_=case();c=next(f for f in p.facts if f.kind=='total')
    assert inspect_output(SemanticOutput(assertions=(proposal(c,text),)),p,'vi').output is None


def test_exact_slot_numeric_repair_optional_trim_and_missing_main_fallback():
    p,_,_=case();c=next(f for f in p.facts if f.kind=='total');fees=next(f for f in p.facts if f.kind=='fees')
    bad=proposal(c,'Tổng chi là 11 VND.').model_copy(update={'value':'11'})
    checked=inspect_output(SemanticOutput(assertions=(bad,)),p,'vi')
    assert checked.disposition=='REPAIRED' and '10 VND' in checked.output.assertions[0].text
    assert inspect_output(checked.output,p,'vi',allow_repair=False).output
    checked=inspect_output(SemanticOutput(assertions=(proposal(c),proposal(fees,'Phí là 10 kg.'))),p,'vi')
    assert checked.disposition=='TRIMMED' and len(checked.output.assertions)==1
    assert inspect_output(SemanticOutput(assertions=(proposal(fees),)),p,'vi').output is None
    wrong=bad.model_copy(update={'unit':'kg'})
    assert inspect_output(SemanticOutput(assertions=(wrong,)),p,'vi').output is None
    multi=proposal(c,'Tổng chi là 10 VND. Theo phương án đang xem.')
    assert inspect_output(SemanticOutput(assertions=(multi,)),p,'vi').output


def test_no_winner_positive_selection_and_unproven_certification_rejected():
    p,_,_=case('Không có winner, vướng điều kiện nào?',kind='infeasible')
    assert any(f.kind=='gap' for f in p.facts)
    assert inspect_output(valid(p),p,'vi').output
    out=valid(p);bad=out.assertions[0].model_copy(update={'text':'Run này đã có phương án được khuyến nghị.'})
    assert inspect_output(out.model_copy(update={'assertions':(bad,*out.assertions[1:])}),p,'vi').output is None
    p,_,_=case('Vì sao chọn phương án này?');out=valid(p)
    bad=out.assertions[-1].model_copy(update={'text':'Đã chứng nhận tối ưu toàn cục.'})
    assert inspect_output(out.model_copy(update={'assertions':(*out.assertions[:-1],bad)}),p,'vi').output is None


def test_proof_obligations_include_retained_eligibility_and_numeric_requirements():
    p,_,_=case('Vì sao chọn phương án này?')
    kinds=[f.kind for f in p.facts if f.fact_id in p.required]
    assert kinds.count('eligibility')==1 and kinds.count('requirement')==2
    assert {f.meaning.split(': ')[-1] for f in p.facts if f.kind=='requirement'}=={'tối thiểu 95%, trạng thái PASS; thiếu 0 cup'}
    out=valid(p);assert inspect_output(out,p,'vi').output
    i=next(i for i,a in enumerate(out.assertions) if '95%' in a.text)
    changed=out.assertions[i].model_copy(update={'text':out.assertions[i].text.replace('95%','100%')})
    assert inspect_output(out.model_copy(update={'assertions':(*out.assertions[:i],changed,*out.assertions[i+1:])}),p,'vi').output is None


def test_missing_detailed_no_winner_explanation_is_unknown_not_invented():
    # Hand-authored projection contract for an unavailable detailed C08 payload;
    # not a new persisted Run or a claim about the complete static fixture.
    _,request,e=case('Không có winner, vướng gì?',kind='infeasible')
    explanation=e.overview.explanation.model_copy(update={'options':(),'blockers':()})
    e=e.model_copy(update={'overview':e.overview.model_copy(update={'explanation':explanation})})
    effective,scope,context=resolve_context(request,e)
    p=select_evidence(e,effective,scope,context)
    assert {f.kind for f in p.facts}=={'no_winner','detail_unknown'}
    assert inspect_output(valid(p),p,'vi').output
    assert 'Chưa lưu gap' in p.fallback.answer


def test_causal_or_probability_question_does_not_pass_as_quantity_only_answer():
    p,_,_=case('Vì sao Sữa tươi cần mua?')
    assert any(f.kind=='detail_unknown' for f in p.facts)
    assert inspect_output(valid(p),p,'vi').output
    only_quantity=SemanticOutput(assertions=tuple(proposal(f) for f in p.facts if f.kind=='purchase_quantity'))
    assert inspect_output(only_quantity,p,'vi').output is None
    p,_,_=case('Xác suất thiếu Sữa tươi là bao nhiêu?')
    assert {f.kind for f in p.facts}=={'detail_unknown'}
    assert 'xác suất' in p.fallback.answer and inspect_output(valid(p),p,'vi').output


def test_proposal_slots_do_not_authorize_wrong_entity_or_path():
    p,_,_=case('Sữa tươi cần mua bao nhiêu?');c=p.facts[0]
    out=SemanticOutput(assertions=(proposal(c,'Đề xuất mua 20 g Sữa đặc.'),))
    assert inspect_output(out,p,'vi').output is None
    p,_,_=case('Phương án khác đắt hơn được lợi gì?');out=valid(p)
    a=out.assertions[1].model_copy(update={'path':'OTHER'})
    assert inspect_output(out.model_copy(update={'assertions':(out.assertions[0],a,*out.assertions[2:])}),p,'vi').output is None


def test_live_development_pair_form_is_scoped_delta_not_absolute_or_wrong_direction():
    p,_,_=case('Phương án khác đắt hơn được lợi gì?')
    rows=[]
    for c in p.facts:
        text=f'Chênh lệch tổng chi là {c.display} {c.unit}.' if c.kind=='pair_cost' else f'Lượng phục vụ món "{c.label}" trên đường "{c.path}" tăng {c.display} {c.unit}.'
        rows.append(proposal(c,text))
    out=SemanticOutput(assertions=tuple(rows))
    assert inspect_output(out,p,'vi').output
    for bad in ('giảm','đã tăng','vì tăng'):
        a=rows[1].model_copy(update={'text':rows[1].text.replace('tăng',bad)})
        assert inspect_output(out.model_copy(update={'assertions':(rows[0],a,*rows[2:])}),p,'vi').output is None
    a=rows[1].model_copy(update={'text':rows[1].text.replace('tăng ','')})
    assert inspect_output(out.model_copy(update={'assertions':(rows[0],a,*rows[2:])}),p,'vi').output is None


def test_product_labels_candidates_resumption_scope_and_foreign_product():
    p,_,_=case('Món SYNTHETIC 0 và SYNTHETIC 1 đáp ứng bao nhiêu?')
    assert p.fallback.kind=='clarification' and len(p.fallback.clarification.product_candidates)==2
    p,_,_=case('SYNTHETIC 0',context=p.fallback.context)
    assert p.fallback.kind=='answer'
    assert {f.entity_id for f in p.facts}=={str(UUID(int=100))}
    assert p.fallback.context.product_id==UUID(int=100)
    p,_,_=case('Còn nó đáp ứng bao nhiêu?',context=p.fallback.context)
    assert {f.entity_id for f in p.facts}=={str(UUID(int=100))}
    with pytest.raises(Exception) as e:case('Còn nó đáp ứng bao nhiêu?',context=p.fallback.context.model_copy(update={'product_id':UUID(int=999)}))
    assert e.value.code=='RESOURCE_NOT_FOUND'
