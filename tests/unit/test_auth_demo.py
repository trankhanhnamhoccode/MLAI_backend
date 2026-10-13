"""Demo safeguards and SMTP receipt checks without any network or real secrets."""
import json
import ssl
from types import SimpleNamespace

from pydantic import SecretStr
import pytest

from scripts import auth_demo


def test_demo_transport_never_sends_to_another_recipient():
    sent = []
    class Fake:
        available = True
        def __call__(self, address, token):
            sent.append((address, token))
    transport = auth_demo.SelfOnlyTransport(Fake(), "holder@example.test")
    assert transport.available
    with pytest.raises(RuntimeError):
        transport("someone-else@example.test", SecretStr("synthetic"))
    assert not sent
    transport("holder@example.test", SecretStr("synthetic"))
    assert len(sent) == 1


@pytest.mark.parametrize("failure", [None, "auth", "uncertain"])
def test_smoke_is_one_attempt_cert_verified_and_reports_only_receipt(monkeypatch, tmp_path, capsys, failure):
    monkeypatch.setattr(auth_demo, "PRIVATE", tmp_path)
    s = SimpleNamespace(auth_smtp_host="smtp.gmail.com", auth_smtp_port=465,
        auth_smtp_username="holder@example.test", auth_smtp_password=SecretStr("synthetic-password"),
        auth_delivery_sender="holder@example.test")
    monkeypatch.setattr(auth_demo, "settings", lambda: s)
    sent = []
    class FakeSMTP:
        def __init__(self, host, port, *, context, timeout):
            assert host == "smtp.gmail.com" and port == 465
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, username, password):
            if failure == "auth":
                raise auth_demo.smtplib.SMTPAuthenticationError(535, b"synthetic-password holder@example.test")
        def send_message(self, message, *, to_addrs):
            assert to_addrs == [s.auth_smtp_username]
            assert message["To"] == s.auth_smtp_username
            assert "synthetic-password" not in message.get_content()
            assert "#token=" not in message.get_content()
            sent.append(message)
            if failure == "uncertain":
                raise OSError("synthetic-password")
            return {}
    monkeypatch.setattr(auth_demo.smtplib, "SMTP_SSL", FakeSMTP)
    if failure:
        with pytest.raises(RuntimeError): auth_demo.smoke()
    else:
        auth_demo.smoke()
    with pytest.raises(FileExistsError): auth_demo.smoke()
    result = json.loads((tmp_path / "smtp-smoke.json").read_text())
    assert result["inbox_confirmed"] is False
    assert result["outcome"] == ("FAILED_OR_UNCERTAIN" if failure else "SMTP_ACCEPTED")
    assert len(sent) == (0 if failure == "auth" else 1)
    output = capsys.readouterr().out + json.dumps(result)
    assert "synthetic-password" not in output and "holder@example.test" not in output
