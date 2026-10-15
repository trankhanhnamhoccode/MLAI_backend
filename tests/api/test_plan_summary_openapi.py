"""Only explicit summary generation/retained read; no chat or hidden C08 change."""
from app.main import create_app
from app.config import Settings


def test_summary_routes_security_and_typed_wire():
    spec=create_app(Settings(_env_file=None)).openapi()
    paths=spec['paths'];schemas=spec['components']['schemas']
    base='/api/v1/procurement-plans/{plan_id}/assistant/summary'
    create=paths[base]['post'];read=paths[base+'/{generation_id}']['get']
    assert create['operationId']=='AS01' and read['operationId']=='AS02'
    assert create['security']==read['security']==[{'APIKeyCookie':[]}]
    assert 'requestBody' not in read
    assert next(p for p in create['parameters'] if p['name']=='Idempotency-Key')['required']
    assert schemas['SummaryRequest']['additionalProperties'] is False
    assert set(schemas['SummaryRequest']['required'])=={'expected_evidence_version','option_id','locale','detail_level'}
    assert set(schemas['SummaryExpression']['properties'])=={'ordering','tone'}
    assert schemas['SummaryAnswer']['properties']['source']['enum']==['deterministic_fallback','model_presentation']
    assert paths['/api/v1/procurement-plans/{plan_id}/explanation']['get']['operationId']=='C08'
    chat=paths['/api/v1/procurement-plans/{plan_id}/assistant/messages']['post']
    assert chat['operationId']=='AS03' and chat['security']==create['security']
    assert next(p for p in chat['parameters'] if p['name']=='Idempotency-Key')['required']
    assert schemas['ChatRequest']['additionalProperties'] is False
    assert schemas['HistoryMessage']['properties']['role']['enum']==['user','assistant']
