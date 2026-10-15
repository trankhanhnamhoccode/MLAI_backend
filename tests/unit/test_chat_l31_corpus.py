"""Report bounded-checker errors separately; do not relabel legitimate wording."""
import json
from pathlib import Path
from tests.unit.test_chat_l31 import case
from app.application.chat_assertions import proposal,inspect_output
from app.application.contracts.chat_generation import SemanticOutput


def test_hand_labelled_wording_corpus_with_explicit_remaining_false_rejection():
    corpus=json.loads(Path('tests/fixtures/decision_assistant/l31_wording_corpus.json').read_text(encoding='utf8'))
    rows=[]
    for item in corpus['cases']:
        plan,_,_=case(item['question'])
        card=next(f for f in plan.facts if f.kind==item['kind'])
        assert (card.display,card.unit)==(item['expected_value'],item['expected_unit'])
        inspected=inspect_output(SemanticOutput(assertions=(proposal(card,item['text']),)),plan,'vi')
        accepted=inspected.output is not None
        rows.append(dict(id=item['id'],tier=item['tier'],expected_valid=item['expected_valid'],accepted=accepted,
            false_acceptance=accepted and not item['expected_valid'],false_rejection=not accepted and item['expected_valid'],
            main_answer_complete=accepted,failures=inspected.failures))
    report=dict(mode='OFFLINE_HAND_LABELLED_NO_PROVIDER',cases=rows,
        false_acceptances=sum(r['false_acceptance'] for r in rows),false_rejections=sum(r['false_rejection'] for r in rows),
        note='This finite corpus is not proof of general entailment. Main obligations/context and repair/regeneration have separate unit/SQL tests.')
    out=Path('runtime/assistant-test/l31/wording-corpus.json');out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    assert not any(r['false_acceptance'] for r in rows)
    # Intentionally documented unsupported phrasing; not changed to an invalid
    # label, silently xfailed or used to tune the checker after viewing the probe.
    assert {r['id'] for r in rows if r['false_rejection']}=={'probe-new-phrasing'}
