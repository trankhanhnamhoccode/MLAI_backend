"""Product-approved catalogue delta and unchanged explicit consent semantics."""
import pytest
from pydantic import ValidationError

from app.application.contracts.staff import AcceptInvitation, GrantsRequest
from app.domain.permissions import CATALOGUE, CATALOG_VERSION, PERMISSIONS, effective_permissions


def test_catalogue_preserves_old_descriptors_and_matches_approved_history_keys():
    assert CATALOG_VERSION == 'permissions-v3'
    assert len(PERMISSIONS) == 43
    labels = {
        'calendar.read': 'Xem lịch nghiệp vụ', 'calendar.write': 'Ghi lịch nghiệp vụ',
        'usage.history.read': 'Xem lịch sử sử dụng', 'usage.history.write': 'Ghi lịch sử sử dụng',
        'purchase.history.read': 'Xem lịch sử mua', 'purchase.history.write': 'Ghi lịch sử mua',
    }
    by_key = {item.key: item for item in CATALOGUE}
    for key, label in labels.items():
        item = by_key[key]
        assert item.group == 'History' and item.label_vi == label
        assert item.description_vi == label + '; chỉ trong Store được cấp quyền.'
        assert item.grantable_to_staff and not item.required_with and item.exposure == 'ordinary'
    assert effective_permissions('STAFF', ('menu.read',)) == ('menu.read',)
    assert set(effective_permissions('OWNER', ())) == PERMISSIONS
    assert len(GrantsRequest(grants=sorted(PERMISSIONS), reason='Explicit grant').grants) == 43


def test_accept_schema_is_true_only_and_rejects_coercion():
    assert AcceptInvitation.model_json_schema()['properties']['accept']['const'] is True
    for value in (False, 1, 0, 'true', None):
        with pytest.raises(ValidationError):
            AcceptInvitation(token='synthetic', accept=value)
    assert AcceptInvitation(token='synthetic', accept=True).accept is True
