from app.main import create_app
from app.config import Settings


def test_store_creation_is_additive_strict_authenticated_metadata_only():
    schema=create_app(Settings(_env_file=None)).openapi()
    operation=schema['paths']['/api/v1/stores']['post']
    assert operation['operationId']=='T03'
    assert operation['security']==[{'APIKeyCookie':[]}]
    assert {'Origin','X-CSRF-Token','Idempotency-Key'}<={p['name'] for p in operation['parameters']}
    assert {'201','401','403','409','422','428','503'}<=operation['responses'].keys()
    body=schema['components']['schemas']['StoreCreateRequest']
    assert set(body['properties'])==set(body['required'])=={'name','timezone','currency'}
    assert body['additionalProperties'] is False
    assert schema['paths']['/api/v1/stores']['get']['operationId']=='T01'


def test_store_creation_bounded_json_duplicate_headers_and_origin_before_decode():
    from fastapi.testclient import TestClient
    app=create_app(Settings(_env_file=None,auth_allowed_origins=['https://fe.example.test'],
        database_url='postgresql+psycopg://synthetic:synthetic@127.0.0.1:1/shelfcash_test'))
    with TestClient(app,base_url='https://backend.example.test') as client:
        headers={'Origin':'https://fe.example.test','Content-Type':'application/json'}
        large=client.post('/api/v1/stores',content=b'x'*65537,headers=headers)
        assert large.status_code==413 and large.headers['access-control-allow-origin']=='https://fe.example.test'
        wrong=client.post('/api/v1/stores',content=b'{',headers={'Origin':'https://wrong.example','Content-Type':'application/json'})
        assert wrong.status_code==403 and wrong.json()['error']['code']=='CSRF_CHECK_FAILED'
        duplicate=client.post('/api/v1/stores',json=dict(name='Explicit',timezone='UTC',currency='VND'),
            headers=[('Origin','https://fe.example.test'),('Idempotency-Key','one'),('Idempotency-Key','two')])
        assert duplicate.status_code==400
