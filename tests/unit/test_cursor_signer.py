from app.infrastructure.auth_crypto import CursorSigner


def test_owned_private_key_and_domain_session_binding():
    signer, other_process = CursorSigner(), CursorSigner()
    signature = signer.sign("session", "stores", "payload")
    assert signature == signer.sign("session", "stores", "payload")
    assert signature != signer.sign("other-session", "stores", "payload")
    assert signature != signer.sign("session", "staff", "payload")
    assert signature != signer.sign("session", "stores", "changed-payload")
    assert signature != other_process.sign("session", "stores", "payload")
