from app.config import Settings
from app.main import create_app


def test_decline_additive_contract_and_terminal_extensions():
    schema = create_app(Settings(_env_file=None)).openapi()
    operation = schema['paths']['/api/v1/staff-invitations/{invitation_id}/decline']['post']
    assert operation['operationId'] == 'IN01'
    assert operation['security'] == [{'APIKeyCookie': []}]
    assert {'Origin', 'X-CSRF-Token', 'If-Match', 'Idempotency-Key'} <= {
        item['name'] for item in operation['parameters'] if item['in'] == 'header'}
    assert {'200', '404', '409', '410', '412', '428'} <= set(operation['responses'])
    models = schema['components']['schemas']
    assert set(models['DeclineInvitation']['properties']) == {'token', 'reason'}
    assert models['DeclineInvitation']['properties']['token']['writeOnly']
    assert set(models['DeclineReceipt']['properties']) == {
        'invitation_id', 'store_id', 'status', 'declined_at', 'version', 'event_id', 'next_action'}
    for name in ('Invitation', 'InvitationOffer'):
        assert 'declined' in models[name]['properties']['status']['enum']
        assert 'declined_at' in models[name]['properties']
    assert 'can_decline' in models['OfferRead']['properties']
    assert 'DECLINED' in models['InvitationEvent']['properties']['kind']['enum']
    assert set(models['AcceptInvitation']['properties']) == {'token', 'accept'}
