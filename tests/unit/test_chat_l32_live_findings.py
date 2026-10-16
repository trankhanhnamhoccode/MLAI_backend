"""Codex-authored regressions from stored development calls; no paid calls."""
from app.application.contracts.chat_generation import SemanticOutput
from app.application.chat_assertions import proposal,inspect_output
from app.infrastructure.conversational_provider import payload_for
from tests.unit.test_chat_l32 import current


def test_compound_facts_send_exact_null_and_polarity_slots_not_extracted_numbers():
    p,r,_=current('Vì sao chọn phương án này?')
    payload=payload_for(p,r);slots={a['fact_id']:a for a in payload['assertion_contract']['slots_by_fact']}
    for f in p.facts:
        assert slots[f.fact_id]==proposal(f).model_dump(exclude={'text'})
        if f.kind=='requirement':assert slots[f.fact_id]['value'] is None and slots[f.fact_id]['unit'] is None
        if f.kind=='unproven':assert slots[f.fact_id]['polarity']=='affirmed'
    f=next(f for f in p.facts if f.kind=='requirement')
    bad=proposal(f).model_copy(update={'value':'95','unit':'%'})
    out=SemanticOutput(assertions=tuple(bad if c.fact_id==f.fact_id else proposal(c) for c in p.facts if c.fact_id in p.required))
    assert inspect_output(out,p,'vi').output is None


def test_observed_comparative_form_is_delta_not_absolute_and_v4_stays_pinned():
    p,_,_=current('Phương án đắt hơn được lợi gì?')
    rows=[]
    for f in p.facts:
        text=(f'Phương án đắt hơn có chi phí cao hơn {f.display} {f.unit}.' if f.kind=='pair_cost' else
            f'Phương án đắt hơn có lượng phục vụ mô phỏng cho món {f.label} trên đường {f.path} cao hơn {f.display} {f.unit}.')
        rows.append(proposal(f,text))
    out=SemanticOutput(assertions=tuple(rows))
    assert inspect_output(out,p,'vi').output
    assert inspect_output(out,p.model_copy(update={'version':'chat_evidence/4'}),'vi').output is None
    wrong=out.model_copy(update={'assertions':tuple(a.model_copy(update={'text':a.text.replace('cao hơn','thấp hơn')}) for a in out.assertions)})
    assert inspect_output(wrong,p,'vi').output is None
    # A more expensive option is the to-side only when this sealed cost delta is
    # positive. A valid service number cannot authorize a wrong pair cost role.
    inverted=p.model_copy(update={'facts':tuple(f.model_copy(update={'display':'-5'}) if f.kind=='pair_cost' else f for f in p.facts)})
    assert inspect_output(out,inverted,'vi').output is None


def test_missing_purchase_cause_does_not_imply_an_existing_proposal():
    from uuid import UUID
    p,_,e=current('Vì sao cần mua nguyên liệu này?',kind='infeasible',ingredient=UUID(int=200))
    assert any(f.kind=='purchase_unknown' for f in p.facts)
    unknown=next(f for f in p.facts if f.kind=='detail_unknown')
    assert 'không suy ra có một lượng mua đề xuất' in unknown.meaning
