"""S2.1 is independent of S2 and caps unknown/internal route attempts."""
import json
import pytest
from scripts.summary_s21_live import reserve,ledger,BOUND


def test_unknown_usage_reserves_three_slots_and_stops(tmp_path):
    for n in range(3):reserve(dict(case=str(n),source='frozen'),tmp_path)
    assert ledger(tmp_path)[1]==BOUND*3
    with pytest.raises(ValueError,match='budget exhausted'):reserve(dict(case='next',source='frozen'),tmp_path)


def test_same_case_source_and_closed_ledger_are_not_retried(tmp_path):
    reserve(dict(case='A',source='first'),tmp_path)
    with pytest.raises(ValueError,match='unchanged source'):reserve(dict(case='A',source='first'),tmp_path)
    (tmp_path/'STOP.json').write_text('{}')
    with pytest.raises(ValueError,match='closed'):reserve(dict(case='B',source='first'),tmp_path)


def test_money_cap_is_independent_of_observed_attempt_count(tmp_path):
    for n in range(6):
        _,path=reserve(dict(case=str(n),source='frozen'),tmp_path)
        row=json.loads(path.read_text(encoding='utf8'));row.update(cost_usd=str(BOUND),transport_attempts=1)
        path.write_text(json.dumps(row),encoding='utf8')
    assert ledger(tmp_path)[1]==BOUND*6
    with pytest.raises(ValueError,match='budget exhausted'):reserve(dict(case='next',source='frozen'),tmp_path)
