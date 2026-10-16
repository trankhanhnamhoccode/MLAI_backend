"""Budget/frozen order and retained challenger boundary; no forecast inference."""
import json
from pathlib import Path
import pytest
from scripts import benchmark_adapter_reuse as tool


def test_consumed_marker_rejects_before_computation(tmp_path,monkeypatch):
    marker=tmp_path/'compute-claim.json';marker.write_text('original')
    monkeypatch.setattr(tool,'BASE',tmp_path)
    with pytest.raises(RuntimeError,match='F4_2_BUDGET_CONSUMED'):tool.run()
    assert marker.read_text()=='original'


def test_paired_order_reverses_first_arm_and_stays_three_per_arm():
    assert tool.ORDER==['baseline','candidate','candidate','baseline','baseline','candidate']
    assert tool.ORDER.count('baseline')==tool.ORDER.count('candidate')==3


def test_retained_native_output_validation_without_inference():
    from app.application.contracts.forecast_challenger import ChallengerInput,ChallengerOutput
    from app.application.forecast_challenger_validation import validate_output
    root=Path('runtime/challenger/f4_1/completion/experiments/540bb41e97f5d95092362e17fb7e91d3162c0894d2a4791a9c0010b4e12d6850')
    plan=json.loads((root/'setup.json').read_bytes())
    value=ChallengerInput.model_validate_json((Path(plan['preflight_directory'])/'native-input.json').read_bytes())
    output=ChallengerOutput.model_validate_json((root/'native-output.json').read_bytes())
    validate_output(value,output)
