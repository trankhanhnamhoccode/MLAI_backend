"""Exact S4.9 inventory, wire types, headers and excluded future surfaces."""
from app.main import create_app
from app.config import Settings


def test_c02_c03_exact_public_contract():
    spec=create_app(Settings(_env_file=None)).openapi()
    c02=spec['paths']['/api/v1/stores/{store_id}/procurement-plans']['post']
    c03=spec['paths']['/api/v1/procurement-plans/{plan_id}']['get']
    assert c02['operationId']=='C02' and c03['operationId']=='C03'
    assert c02['security']==c03['security']==[{'APIKeyCookie':[]}]
    assert {'200','202','400','401','403','404','409','422','503'}==set(c02['responses'])
    assert next(p for p in c02['parameters'] if p['name']=='Idempotency-Key')['required'] is True
    assert {'Location','Retry-After','Cache-Control'}<=set(c02['responses']['202']['headers'])
    assert {'ETag','Cache-Control'}<=set(c03['responses']['200']['headers'])
    assert c02['requestBody']['content']['application/json']['schema']=={'$ref':'#/components/schemas/PlanningRequest-Input'}
    assert 'requestBody' not in c03
    schemas=spec['components']['schemas']
    assert set(schemas['Accepted']['properties'])=={'run_id','status','accepted_at'}
    assert set(schemas['RunView']['required'])==set(schemas['RunView']['properties'])=={
        'run_id','store_id','status','outcome','accepted_at','started_at','finished_at','response_version','request',
        'configuration','operational_basis','forecast','scope','execution','result','errors'}
    assert set(schemas['PlanningRequest-Input']['properties'])=={'requirements_mode','forecast_start_date','default_requirements_version','requirements','saved_requirement_id'}
    assert schemas['StrategyResult']['properties']['domain_size']['type']=='string'
    assert schemas['ExactQuantity']['properties']['numerator']['type']=='string'
    operations={op['operationId'] for methods in spec['paths'].values() for op in methods.values()}
    assert {'C04','C05','C08','N9','N10','N11','H01','H02'}<=operations
    assert not operations & {'C06','C07'}
