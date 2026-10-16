"""Codex-authored regression for observed raw10 omission; no paid provider."""
from app.application.chat_assertions import inspect_output,proposal
from app.application.contracts.chat_generation import SemanticOutput
from tests.unit.test_chat_l32 import current


def test_correct_typed_slots_do_not_excuse_missing_simulation_prose():
    plan,_,_=current('Sữa cần mua bao nhiêu?')
    for question in ('Sữa tươi','Vì sao lượng đó?','Còn sữa đặc?'):
        plan,_,_=current(question,context=plan.fallback.context)
    cards=[f for f in plan.facts if f.fact_id in plan.required]
    valid=SemanticOutput(assertions=tuple(proposal(f) for f in cards))
    assert inspect_output(valid,plan,'vi').output is not None
    # Exact live wording form, rebound to current synthetic scoped fact IDs.
    omitted=valid.model_copy(update={'assertions':tuple(
        a.model_copy(update={'text':'Các yếu tố được ghi nhận cho Sữa đặc là: LOW / 2026-10-08.'})
        if f.kind=='mechanistic' else a for f,a in zip(cards,valid.assertions))})
    check=inspect_output(omitted,plan,'vi')
    assert check.output is None and any('UNVERIFIED_MATERIAL_PROSE' in f for f in check.failures)
    # Correct numbers/path with the previous Ingredient name still cannot pass.
    wrong_entity=valid.model_copy(update={'assertions':tuple(
        a.model_copy(update={'text':a.text.replace('Sữa đặc','Sữa tươi')})
        if f.kind=='mechanistic' else a for f,a in zip(cards,valid.assertions))})
    assert inspect_output(wrong_entity,plan,'vi').output is None
