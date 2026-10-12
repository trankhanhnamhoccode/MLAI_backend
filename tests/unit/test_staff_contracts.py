import base64
import pytest
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr, ValidationError
from app.application.contracts.staff import GrantsRequest, AcceptInvitation, CreateInvitation
from app.application.contracts.auth import AuthError
from app.infrastructure.invitation_secret import InvitationSecret


def test_explicit_consent_grants_and_no_caller_authority():
    assert GrantsRequest(grants=[],reason="No feature grants").grants==()
    for grants in (["menu.read","menu.read"],["menu.read","inventory.read"]):
        with pytest.raises(ValidationError):GrantsRequest(grants=grants,reason="test")
    with pytest.raises(AuthError,match="UNKNOWN_PERMISSION"):
        GrantsRequest(grants=["staff.manage"],reason="test")
    for consent in (False,1,"true"):
        with pytest.raises(ValidationError):AcceptInvitation(token="synthetic",accept=consent)
    with pytest.raises(ValidationError):AcceptInvitation(token="synthetic",accept=True,user_id="spoof")
    value=CreateInvitation(email=" STAFF@Example.test ",grants=[],permission_catalog_version="permissions-v2",reason="test")
    assert value.email=="staff@example.test"
    with pytest.raises(AuthError,match="INVALID_TOKEN"):AcceptInvitation(token="x"*255+"\U0001f600"*65,accept=True)


def test_encrypted_intent_authenticated_identity_random_nonce_and_secret_repr():
    crypto=InvitationSecret(SecretStr(base64.b64encode(bytes(range(32))).decode()))
    a,b=crypto.seal("synthetic-token","scope-a"),crypto.seal("synthetic-token","scope-a")
    assert a!=b and b"synthetic-token" not in a
    secret=crypto.open(a,"scope-a")
    assert secret.get_secret_value()=="synthetic-token" and "synthetic-token" not in repr(secret)
    with pytest.raises(InvalidTag):crypto.open(a,"scope-b")
    with pytest.raises(InvalidTag):crypto.open(a[:-1]+bytes([a[-1]^1]),"scope-a")
    for key in (None,SecretStr("invalid"),SecretStr(base64.b64encode(b"short").decode())):
        with pytest.raises((ValueError,AuthError)):InvitationSecret(key)
