"""Fresh combined-source HTTP examples; synthetic, provider OFF, no browser claim."""
import json
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tests.integration.test_auth_public import env
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_email_verification import env as store_env
from tests.integration.test_store_creation import holder, create
from tests.integration.test_import_staging import imp, post
from tests.integration.test_import_commit import ready, finished

ROOT = Path('runtime/recovery-handoff/examples')


def save(name, rows):
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / (name + '.json')).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')


def test_summary_chat_context_and_clarification_examples(assistant):
    from app.application.contracts.plan_summary import SummaryRequest, SummaryEnvelope
    from app.application.contracts.assistant_chat import ChatRequest, ChatEnvelope
    from app.application.use_cases.assistant_chat import AssistantChat
    from app.models import AssistantMessage, PlanSummaryGeneration

    state, record, summary, headers, body, path = assistant
    SummaryRequest.model_validate(body)
    response = state[5].post(path, headers=headers, json=body)
    assert response.status_code == 200, response.text
    SummaryEnvelope.model_validate(response.json())
    read = state[5].get(response.headers['Location'])
    assert read.status_code == 200 and read.json()['data'] == response.json()['data']
    rows = [dict(operation_id='AS01', method='POST', path=path, body=body,
                 headers={'Idempotency-Key': headers['Idempotency-Key']}, response=response.json()),
            dict(operation_id='AS02', method='GET', path=response.headers['Location'], response=read.json())]
    state[5].app.state.assistant_chat = AssistantChat(summary.planning)
    assert state[5].app.state.assistant_chat.presentation_version == 6
    message_path = path.rsplit('/', 1)[0] + '/messages'

    def message(label, question, context=None):
        request = {**body, 'question': question, 'ingredient_id': None, 'history': []}
        if context is not None:
            request['context'] = context
        ChatRequest.model_validate(request)
        key = str(uuid4())
        receipt = state[5].post(message_path, headers={**headers, 'Idempotency-Key': key}, json=request)
        assert receipt.status_code == 200, receipt.text
        ChatEnvelope.model_validate(receipt.json())
        assert state[5].post(message_path, headers={**headers, 'Idempotency-Key': key}, json=request).json()['data'] == receipt.json()['data']
        rows.append(dict(operation_id='AS03', example=label, method='POST', path=message_path,
                         headers={'Idempotency-Key': key}, body=request, response=receipt.json()))
        return receipt.json()['data']

    assert message('answer', 'Chi phí và ngân sách?')['kind'] == 'answer'
    ambiguous = message('clarification', 'Tồn kho?')
    assert ambiguous['kind'] == 'clarification' and ambiguous.get('context')
    assert ambiguous['context']['pending']
    # This retained fixture has IDs but no captured ingredient names. Keep the
    # empty labelled candidates honest; use the server-pinned pending IDs.
    assert ambiguous['context']['pending']['candidate_ids']
    identity = ambiguous['context']['pending']['candidate_ids'][0]
    context = {**ambiguous['context'], 'ingredient_id': identity}
    continued = message('context_continuation', 'Tồn kho?', context)
    assert continued['kind'] == 'answer' and continued['ingredient_id'] == identity
    assert state[5].get(message_path).status_code == 405
    with Session(state[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(AssistantMessage)) == 3
        assert fresh.scalar(select(func.count()).select_from(PlanSummaryGeneration)) == 1
    save('assistant', rows)


def test_store_recovery_examples(store_env):
    from app.application.contracts.auth import Envelope, StoreSummary
    from app.models import Store
    csrf = holder(store_env)
    assert store_env[6].get('/api/v1/stores').json()['data']['items'] == []
    key = str(uuid4())
    body = dict(name='Synthetic handoff Store', timezone='UTC', currency='VND')
    receipt = create(store_env, csrf, key, body)
    assert receipt.status_code == 201
    TypeAdapter(Envelope[StoreSummary]).validate_python(receipt.json())
    assert create(store_env, csrf, key, body).json()['data'] == receipt.json()['data']
    with Session(store_env[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Store)) == 1
    save('store', [dict(operation_id='T03', method='POST', path='/api/v1/stores',
                       headers={'Idempotency-Key': key}, body=body, response=receipt.json(),
                       recovery={'reader': '/api/v1/stores', 'exact_replay_equal': True,
                                 'empty_before_dispatch_did_not_fence_creation': True})])


def test_import_commit_recovery_examples(imp):
    from app.application.contracts.import_mapping import CommitRequest, CommitAccepted, ImportCompletion, ImportEnvelope
    ident, read, revision = ready(imp)
    body = dict(phase='commit', preview_id=read['preview']['summary']['preview_id'],
                preview_digest=read['preview']['summary']['digest'], confirm=True, resolutions=[])
    # Explicit null and omitted reason are equivalent in the current typed digest;
    # store/replay the original wire body rather than normalizing it in FE.
    assert CommitRequest.model_validate(body).model_dump() == CommitRequest.model_validate({**body, 'reason': None}).model_dump()
    key = str(uuid4())
    path = f'/api/v1/imports/{ident}/process'
    accepted = post(imp, f'/imports/{ident}/process', body, match=revision, key=key)
    assert accepted.status_code == 202, accepted.text
    ImportEnvelope[CommitAccepted].model_validate(accepted.json())
    completion = finished(imp, ident, accepted)
    ImportCompletion.model_validate(completion)
    replay = post(imp, f'/imports/{ident}/process', body, match=revision, key=key)
    assert replay.status_code == 202 and replay.json()['data'] == accepted.json()['data']
    null_reason = post(imp, f'/imports/{ident}/process', {**body, 'reason': None}, match=revision, key=key)
    assert null_reason.status_code == 202 and null_reason.json()['data'] == accepted.json()['data']
    different_reason = post(imp, f'/imports/{ident}/process', {**body, 'reason': 'Different reviewed intent'}, match=revision, key=key)
    assert different_reason.status_code == 409 and different_reason.json()['error']['code'] == 'IDEMPOTENCY_KEY_REUSED'
    assert imp[2].run_one() is None
    save('import', [dict(operation_id='I05', method='POST', path=path,
                        headers={'Idempotency-Key': key, 'If-Match': '"' + revision + '"'},
                        body=body, response=accepted.json(), completion=completion,
                        recovery={'exact_replay_equal': True, 'reason_omitted_vs_null_equivalent': True,
                                  'reader': f'/api/v1/imports/{ident}/completion'})])
