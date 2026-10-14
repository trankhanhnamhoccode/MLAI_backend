"""The historical baseline must survive cleanup without substitution or corruption."""
import pytest

from scripts import integration_contract_snapshot as wire


def test_original_baseline_is_pinned_and_still_reports_real_changes(tmp_path, monkeypatch):
    assert len(wire.load_baseline()["paths"]) > 1
    monkeypatch.setattr(wire, "ROOT", tmp_path)
    delta = wire.snapshot()
    assert delta["baseline_operations"] == 32
    assert delta["current_operations"] == 69
    assert len(delta["added_operations"]) == 37
    assert delta["changed_operations"] == ["I01", "I02", "I03", "I04", "I05", "M04", "N5"]
    assert not delta["removed_operations"]


def test_changed_baseline_is_rejected_before_comparison(tmp_path, monkeypatch):
    path = tmp_path / "baseline.json"
    path.write_bytes(wire.BASELINE_PATH.read_bytes() + b"\n")
    monkeypatch.setattr(wire, "BASELINE_PATH", path)
    with pytest.raises(ValueError, match="baseline integrity mismatch"):
        wire.load_baseline()
