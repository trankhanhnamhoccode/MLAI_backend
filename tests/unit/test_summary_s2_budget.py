"""Write-ahead S2 caps and unknown usage; no provider or DB required."""
import json
from decimal import Decimal
import pytest
from scripts.summary_s2_live import reserve,ledger,BOUND


def test_unknown_usage_keeps_reservation_and_stops_before_money_cap(tmp_path):
    for n in range(5):assert reserve({'case':'A'},tmp_path)[0]==n+1
    with pytest.raises(ValueError,match='budget exhausted'):reserve({'case':'A'},tmp_path)
    rows,used=ledger(tmp_path)
    assert len(rows)==5 and used==BOUND*5 and used<Decimal('.30')


def test_known_cost_releases_only_verified_difference_and_attempt_cap_still_applies(tmp_path):
    for n in range(14):
        _,path=reserve({'case':'A'},tmp_path)
        row=json.loads(path.read_text(encoding='utf8'));row['cost_usd']='.001';row['transport_attempts']=1
        path.write_text(json.dumps(row),encoding='utf8')
    assert ledger(tmp_path)[1]==Decimal('.014')
    with pytest.raises(ValueError,match='budget exhausted'):reserve({'case':'A'},tmp_path)


def test_lock_stop_and_corrupt_credit_fail_closed(tmp_path):
    (tmp_path/'ledger.lock').write_text('interrupted')
    with pytest.raises(FileExistsError):reserve({'case':'A'},tmp_path)
    (tmp_path/'ledger.lock').unlink()
    (tmp_path/'STOP.json').write_text('{}')
    with pytest.raises(ValueError,match='stopped'):reserve({'case':'A'},tmp_path)
    (tmp_path/'STOP.json').unlink()
    _,path=reserve({'case':'A'},tmp_path)
    row=json.loads(path.read_text(encoding='utf8'));row['cost_usd']='-1'
    path.write_text(json.dumps(row),encoding='utf8')
    with pytest.raises(AssertionError):ledger(tmp_path)


@pytest.mark.parametrize('choices',[
    [dict(finish_reason='length',message=dict(content='{"headline":'))],
    [dict(finish_reason='stop',message=dict(content='{malformed'))],
])
def test_truncated_or_malformed_output_falls_back_without_retry(choices):
    from tests.unit.test_plan_summary import Transport,summary_case
    from app.infrastructure.plan_summary_provider import OpenRouterSummaryProvider,payload_for
    from app.application.contracts.plan_summary import SummaryProfile
    from app.application.summary_narrative import render_narrative
    from pydantic import SecretStr
    e,r,f=summary_case('purchase')
    profile=SummaryProfile(enabled=True,model='synthetic-qwen',providers=('SYNTHETIC_PROVIDER',),max_tokens=1200,version='summary_profile/2')
    transport=Transport({},choices=choices)
    presented=OpenRouterSummaryProvider(SecretStr('synthetic'),opener=transport).present(payload_for(e,r,f,profile),profile)
    assert presented.diagnostics.reason=='SCHEMA_REJECTED' and transport.calls==1
    final=render_narrative(e,r,presented.diagnostics)
    assert final.source=='deterministic_fallback' and len(final.claims)==6
