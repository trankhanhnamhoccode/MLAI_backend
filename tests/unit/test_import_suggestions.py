"""Offline transport bounds; not live provider quality evidence."""

import io, json
from uuid import uuid4
from pydantic import SecretStr
from app.config import Settings
from app.application.import_analysis import discover
from app.infrastructure.import_parser import parse_source
from app.infrastructure import import_suggestions as gateway


def source():
    sheets, _, raw = discover(uuid4(), parse_source(b"sales.quantity\n0\n", "csv"))
    return sheets[0], raw[0]


def test_response_size_truncation_and_redirect_do_not_admit_partial_output(monkeypatch):
    sheet, raw = source()
    settings = Settings(_env_file=None, import_llm_suggestions_enabled=True, openrouter_api_key=SecretStr("SYNTHETIC-ONLY"))
    responses = [
        b"x" * 65537,
        json.dumps(
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        ).encode(),
    ]

    class Transport:
        def open(self, *a, **kw):
            return io.BytesIO(responses.pop(0))

    monkeypatch.setattr(gateway, "build_opener", lambda *a: Transport())
    assert gateway.suggest_sheet(settings, sheet, raw, "x", {}) == (
        None,
        "LLM_UNAVAILABLE",
    )
    assert gateway.suggest_sheet(settings, sheet, raw, "x", {}) == (
        None,
        "LLM_INVALID_OUTPUT",
    )
    assert (
        gateway.NoRedirect().redirect_request(
            None, None, 302, "", {}, "https://different-origin.test"
        )
        is None
    )


def test_overwide_profile_and_exhausted_deadline_do_not_send_request(monkeypatch):
    sheet, raw = source()
    settings = Settings(_env_file=None, import_llm_suggestions_enabled=True, openrouter_api_key=SecretStr("SYNTHETIC-ONLY"))
    monkeypatch.setattr(
        gateway,
        "build_opener",
        lambda *a: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    assert gateway.suggest_sheet(
        settings,
        sheet.model_copy(update={"headers": tuple("h" for _ in range(33))}),
        raw,
        "x",
        {},
    ) == (None, "LLM_INPUT_LIMIT")
    times = iter((0, 61))
    monkeypatch.setattr(gateway.time, "monotonic", lambda: next(times))
    assert gateway.suggest_sheet(settings, sheet, raw, "x", {}) == (
        None,
        "LLM_UNAVAILABLE",
    )
