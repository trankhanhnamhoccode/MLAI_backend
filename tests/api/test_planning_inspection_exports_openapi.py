"""Accepted S410 wire including conditional PLAN16 nullable digest and J01."""
from app.main import create_app
from app.config import Settings


def test_exact_s410_surfaces_and_conditional_result_digest():
    spec=create_app(Settings(_env_file=None)).openapi();paths=spec['paths'];schemas=spec['components']['schemas']
    for ident,method,path in [('C04','get','/procurement-plans/{plan_id}/ingredients'),
        ('C05','get','/procurement-plans/{plan_id}/ingredients/{ingredient_id}'),
        ('C08','get','/procurement-plans/{plan_id}/explanation'),('N9','get','/stores/{store_id}/procurement-plans'),
        ('N10','post','/procurement-plans/{plan_id}/exports'),('N11','get','/procurement-plans/{plan_id}/exports/{export_id}'),
        ('H01','get','/stores/{store_id}/imports/calendar'),('H02','get','/stores/{store_id}/imports')]:
        operation=paths['/api/v1'+path][method];assert operation['operationId']==ident
        assert operation['security']==[{'APIKeyCookie':[]}]
        if method=='get':assert 'requestBody' not in operation
    for name in ('IngredientNavigator','IngredientDetail','InspectionMeta'):
        field=schemas[name]['properties']['result_digest'];assert {v['type'] for v in field['anyOf']}=={'string','null'}
        assert 'result_digest' in schemas[name]['required']
    assert set(schemas['ExportRequest']['required'])=={'format','option_id','locale'}
    assert schemas['ExportRequest']['additionalProperties'] is False
    assert schemas['ExportAccepted']['properties']['result_digest']['type']=='string'
    assert 'planning_pdf_export' in schemas['JobView']['properties']['operation']['enum']
    assert 'rendering' in schemas['JobView']['properties']['stage']['enum']
    result=schemas['JobView']['properties']['result']['anyOf'][0]
    assert result['discriminator']['mapping']['planning_pdf_export']=='#/components/schemas/ExportJobResult'
    success=paths['/api/v1/procurement-plans/{plan_id}/exports/{export_id}']['get']['responses']['200']
    assert set(success['content'])=={'application/pdf'}
    assert {'Content-Disposition','Content-Length','ETag','Cache-Control','X-Content-Type-Options'}<=set(success['headers'])
    operations={operation['operationId'] for methods in paths.values() for operation in methods.values()}
    assert not operations & {'C06','C07'}
