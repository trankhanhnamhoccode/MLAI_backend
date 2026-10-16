"""Current handoff JSON must match source DTOs and keep journal exclusions closed."""
import json
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.application.contracts.plan_summary import SummaryEnvelope, SummaryRequest
from app.application.contracts.assistant_chat import ChatEnvelope, ChatRequest
from app.application.contracts.auth import Envelope, StoreSummary
from app.application.contracts.import_mapping import CommitRequest, ImportEnvelope, CommitAccepted, ImportCompletion
from app.application.contracts.store_creation import StoreCreateRequest

ROOT = Path(__file__).resolve().parents[2] / 'docs/handoff'


def test_current_openapi_and_fe73_additive_delta():
    source = create_app(Settings(_env_file=None)).openapi()
    assert json.loads((ROOT / 'openapi.json').read_text(encoding='utf-8')) == source
    diff = json.loads((ROOT / 'openapi_diff_fe73.json').read_text(encoding='utf-8'))
    assert diff['baseline_openapi_sha256'] == '790443d80350cc597c7c06179309e43303ba558de34017ea1dd4113de71fc1ee'
    assert {o['id'] for o in diff['added_operations']} == {'AS01', 'AS02', 'AS03'}
    assert not diff['changed_operations'] and not diff['removed_operations']
    assert diff['changed_schemas'] == ['ExportAccepted']
    assert source['components']['schemas']['ExportAccepted']['properties']['render_version'] == {
        'type': 'string', 'enum': ['planning-pdf/1', 'planning-pdf/2', 'planning-pdf/3'],
        'title': 'Render Version', 'default': 'planning-pdf/3'}


def test_journal_allowlist_is_closed_and_uses_real_operations():
    spec = json.loads((ROOT / 'recovery_journal.json').read_text(encoding='utf-8'))
    api = json.loads((ROOT / 'openapi.json').read_text(encoding='utf-8'))
    operations = {o['operationId']: (m.upper(), p) for p, item in api['paths'].items()
                  for m, o in item.items() if m in {'get', 'post', 'put', 'patch', 'delete'}}
    assert spec['default'] == 'DENY_UNLISTED_OPERATIONS_AND_FIELDS'
    assert {'password', 'session_token', 'csrf_token', 'invitation_token', 'file_bytes', 'raw_uploaded_cells'} <= set(spec['never_persist'])
    assert {'A01', 'A02', 'A05', 'A06', 'A07', 'N7'} <= set(spec['excluded_auth_operations'])
    def fields(schema):
        if '$ref' in schema:
            return fields(api['components']['schemas'][schema['$ref'].rsplit('/', 1)[-1]])
        result = set(schema.get('properties', {}))
        for variant in schema.get('anyOf', []) + schema.get('oneOf', []) + schema.get('allOf', []):
            result.update(fields(variant))
        return result
    for row in spec['operations']:
        assert (row['method'], row['path']) == operations[row['operation_id']]
        assert not {'X-CSRF-Token', 'Cookie', 'Authorization'} & set(row['persist_headers'])
        assert not {'token', 'password', 'history', 'question'} & set(row['journal']['allowed_body_fields'])
        operation = api['paths'][row['path']][row['method'].lower()]
        body = next(iter(operation['requestBody']['content'].values()))['schema']
        assert set(row['journal']['allowed_body_fields']) <= fields(body)
        for reader in row['readers']:
            assert (reader['method'], reader['path']) == operations[reader['operation_id']]
    by_id = {row['operation_id']: row for row in spec['operations']}
    assert by_id['AS03']['journal']['mode'] == 'metadata_only'
    assert by_id['I02']['journal']['mode'] == 'excluded'
    commit = next(row for row in spec['operations'] if row['operation_id'] == 'I05' and row['phase'] == 'commit')
    assert commit['journal']['conditions']['reason'] == 'ABSENT or null ONLY'
    assert commit['journal']['conditions']['resolutions'] == 'exact empty array ONLY'


def test_current_synthetic_examples_validate_against_boundary_models():
    examples = json.loads((ROOT / 'examples.json').read_text(encoding='utf-8'))['examples']
    assert {e['operation_id'] for e in examples} == {'AS01', 'AS02', 'AS03', 'T03', 'I05'}
    assert {e.get('example') for e in examples if e['operation_id'] == 'AS03'} == {'answer', 'clarification', 'context_continuation'}
    pairs = {'AS01': (SummaryRequest, SummaryEnvelope), 'AS02': (None, SummaryEnvelope),
             'AS03': (ChatRequest, ChatEnvelope), 'T03': (StoreCreateRequest, Envelope[StoreSummary]),
             'I05': (CommitRequest, ImportEnvelope[CommitAccepted])}
    for row in examples:
        request, response = pairs[row['operation_id']]
        if request:
            request.model_validate(row['body'])
        response.model_validate(row['response'])
        assert not {'X-CSRF-Token', 'Cookie', 'Authorization'} & row.get('headers', {}).keys()
        if 'completion' in row:
            ImportCompletion.model_validate(row['completion'])
