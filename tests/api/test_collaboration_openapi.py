"""Exact accepted C2 surface and additive N5/N14 contracts."""
from app.main import create_app
from app.config import Settings


def test_c2_exact_operations_strict_union_and_paired_queue_reference():
    schema=create_app(Settings(_env_file=None,environment='test')).openapi()
    operations={(p,m,s['operationId']) for p,e in schema['paths'].items() for m,s in e.items() if m in ('get','post','put','patch','delete')}
    assert len(operations)==69 and len(schema['paths'])==64
    assert {(p,m,i) for p,m,i in operations if i.startswith(('PR','MQ'))}=={
        ('/api/v1/stores/{store_id}/permission-requests','post','PR01'),
        ('/api/v1/stores/{store_id}/permission-requests','get','PR02'),
        ('/api/v1/stores/{store_id}/permission-requests/{request_id}','get','PR03'),
        ('/api/v1/stores/{store_id}/permission-requests/{request_id}/actions','post','PR04'),
        ('/api/v1/imports/{import_id}/mapping-submissions','post','MQ01'),
        ('/api/v1/stores/{store_id}/mapping-submissions','get','MQ02'),
        ('/api/v1/stores/{store_id}/mapping-submissions/{submission_id}','get','MQ03')}
    components=schema['components']['schemas']
    for name in ('SubmitRequest','ApproveRequest','SubmitMapping','WithdrawMapping','RequestChanges'):
        assert components[name]['additionalProperties'] is False
    assert {'submission','notification_delivery'} <= components['DecisionResult']['properties'].keys()
    assert {'permission_request_id','decision_id'} <= components['PermissionEvent']['properties'].keys()
    assert {'submission','notification_delivery'} <= set(components['DecisionResult']['required'])
    assert {'permission_request_id','decision_id'} <= set(components['PermissionEvent']['required'])
    for path,method,status in (
        ('/api/v1/stores/{store_id}/permission-requests','post','201'),
        ('/api/v1/stores/{store_id}/permission-requests/{request_id}','get','200'),
        ('/api/v1/stores/{store_id}/permission-requests/{request_id}/actions','post','200'),
        ('/api/v1/imports/{import_id}/mapping-submissions','post','200'),
        ('/api/v1/imports/{import_id}/mapping-submissions','post','201'),
        ('/api/v1/stores/{store_id}/mapping-submissions/{submission_id}','get','200')):
        assert 'ETag' in schema['paths'][path][method]['responses'][status]['headers']
    from app.application.contracts.import_mapping import Approve
    import pytest
    from pydantic import ValidationError
    from uuid import uuid4
    with pytest.raises(ValidationError):
        Approve(decision='approve_activate',proposal_revision='proposal',expected_active_version=None,
            reason='Review',submission_id=uuid4())
    from app.application.contracts.collaboration import Version
    from pydantic import TypeAdapter
    with pytest.raises(ValidationError):
        TypeAdapter(Version).validate_python('é'*129)
