"""C4 adds only approved GET routes and preserves every C3 operation locator."""
import json
from pathlib import Path
from app.main import create_app
from app.config import Settings


def test_c4_additive_routes_and_typed_extensions():
    spec=create_app(Settings(_env_file=None)).openapi()
    old=json.loads((Path(__file__).parents[1]/'fixtures/c3_operation_routes.json').read_text(encoding='utf-8'))
    operations={value['operationId']:(path,method,value) for path,methods in spec['paths'].items()
        for method,value in methods.items() if method in ('get','post','put','patch','delete')}
    assert len(old['routes'])==69
    assert set(operations)-set(old['routes'])=={'D01','SU01','EX01'}
    for name,route in old['routes'].items():
        assert operations[name][:2]==(route['path'],route['method'])
    assert len(operations)==72 and len(spec['paths'])==66
    for operation in ('D01','SU01','EX01'):
        assert operations[operation][1]=='get' and 'requestBody' not in operations[operation][2]
        assert operations[operation][2]['security']==[{'APIKeyCookie':[]}]
    for operation,required in (
        ('M01',{'file_id','sheet_id','review_only','status','origin'}),
        ('M02',{'file_id','origin','snapshot_id'}),
        ('I04',{'file_id','sheet_id','projection'}),
        ('N9',{'created_by_user_id','created_date_from','created_date_to','snapshot_id'})):
        assert required <= {item['name'] for item in operations[operation][2]['parameters']}
    components=spec['components']['schemas']
    assert {'captured_budget'}<=components['RunSummary']['properties'].keys()
    assert {'mapping_revision','read_set_digest','aggregates'}<=components['PreviewPage']['properties'].keys()
    assert {'source_cells','planned_effect','source_evidence_availability'}<=components['SourceEffectRow']['properties'].keys()
    assert {'counter_scope','counters'}<=components['MappingList']['properties'].keys()
