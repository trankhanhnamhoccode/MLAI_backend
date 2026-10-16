import pytest
from tests.l4_cases import build


@pytest.mark.parametrize('version',['chat_evidence/6','chat_evidence/7'])
@pytest.mark.parametrize('variant,amount',[('negative_pair','-5'),('zero_pair','0')])
def test_reversed_and_zero_pair_actually_exercise_signed_known_deltas(version,variant,amount):
    plan,_,_=build({'question':'So sánh hai phương án?','fixture':variant},version)
    assert next(f.display for f in plan.facts if f.kind=='pair_cost')==amount
    assert not any(f.kind=='comparison_unknown' for f in plan.facts)
    members=[m for f in plan.facts if getattr(f,'group',None) for m in f.group.members]
    services=[f for f in plan.facts if f.kind=='pair_service']+[m for m in members if m.kind=='pair_service']
    assert len(services)==6 and {f.path for f in services}=={'LOW','BASE','HIGH'}
    assert {f.display for f in services}==({'-5','-10'} if amount=='-5' else {'0'})
