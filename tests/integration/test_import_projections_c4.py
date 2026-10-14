"""Pinned mapping counters/raw evidence/overlapping aggregates use whole scopes."""
from tests.integration.test_import_actual_receipts import fresh_store, env, source, review
from tests.integration.test_import_staging import csv_source, previewed
from tests.integration.test_import_commit import analyzed_files


def test_mapping_counters_and_filters_do_not_count_page_length(fresh_store):
    c=fresh_store;record=source(c)
    ident=analyzed_files(c,[('one.csv',csv_source('inventory_receipts',[record])),('two.csv',csv_source('inventory_receipts',[record]))])
    root='/api/v1/imports/'+ident
    full=c[0][5].get(root+'/mappings',params={'review_only':False,'limit':100}).json()['data']
    assert full['counters']['batch']['total']==len(full['items'])>1
    file=full['items'][0]['source_location']['file_id']
    params={'file_id':file,'review_only':False,'limit':1}
    response=c[0][5].get(root+'/mappings',params=params);assert response.status_code==200,response.text
    value=response.json()['data'];expected=[r for r in full['items'] if r['source_location']['file_id']==file]
    assert value['counters']['filtered']['total']==len(expected)>len(value['items'])
    assert value['counts']==full['counts']
    summary=c[0][5].get(root+'/mapping-summary',params={'file_id':file,'review_only':False}).json()['data']
    assert summary['counters']==value['counters'] and summary['mapping_revision']==value['mapping_revision']
    assert c[0][5].get(root+'/mappings',params={**params,'snapshot_id':'stale'}).status_code==409
    cursor=response.json()['meta']['pagination']['next_cursor']
    assert c[0][5].get(root+'/mappings',params={**params,'cursor':cursor+'tampered'}).status_code==422
    from tests.integration.test_import_rule_review import declare_context
    from tests.integration.test_import_actual_receipts import CONTEXT
    declare_context(c,ident,CONTEXT)
    stale=c[0][5].get(root+'/mappings',params={**params,'cursor':cursor})
    assert stale.status_code==409 and stale.json()['error']['code']=='SNAPSHOT_NOT_AVAILABLE'


def test_receipt_raw_source_and_overlapping_file_totals_are_pinned(fresh_store,monkeypatch):
    c=fresh_store;record=source(c)
    ident=analyzed_files(c,[('one.csv',csv_source('inventory_receipts',[record])),('two.csv',csv_source('inventory_receipts',[record]))])
    review(c,ident);read=previewed(c,ident)
    from app.application.use_cases import import_staging
    def forbidden(*args,**kwargs):raise AssertionError('GET parsed or canonicalized source')
    monkeypatch.setattr(import_staging,'make_preview',forbidden)
    monkeypatch.setattr(import_staging,'parse_source',forbidden)
    root='/api/v1/imports/'+ident
    params=dict(include_preview=True,preview_id=read['preview']['summary']['preview_id'],projection='source_effect',rows_limit=1)
    response=c[0][5].get(root,params=params);assert response.status_code==200,response.text
    data=response.json()['data']['preview'];aggregates=data['aggregates']
    assert aggregates['preview_digest']==data['summary']['digest']
    assert aggregates['batch']['raw_source_rows']=={'availability':'available','count':2}
    assert aggregates['batch']['logical_action_count']==2 # receipt + explicit Ingredient reservation
    for file in aggregates['files']:
        scoped=c[0][5].get(root,params={**params,'file_id':file['scope']['file_id']}).json()['data']['preview']
        assert scoped['aggregates']['selected']==file
        assert file['raw_source_rows']['count']==1
    # The receipt belongs to both file scopes; summed child totals overlap.
    assert sum(f['logical_action_count'] for f in aggregates['files'])>aggregates['batch']['logical_action_count']
    whole=c[0][5].get(root,params={**params,'rows_limit':100}).json()['data']['preview']
    row=next(r for r in whole['rows'] if (r['after'] or {}).get('domain')=='inventory_receipts')
    assert row['planned_effect']['kind']=='receipt' and row['source_evidence_availability']=='available'
    assert len({cell['location']['file_id'] for cell in row['source_cells']})==2
    assert all(len(cell['raw_value'] or '')<=200 for cell in row['source_cells'])


def test_xlsx_formula_uses_only_cached_value_and_large_display_is_unavailable(fresh_store):
    from xml.sax.saxutils import escape
    from tests.unit.test_import_parser import workbook
    c=fresh_store;record=source(c,reason='x'*201)
    def cells(values,index,formula=False):
        return f'<row r="{index}">'+''.join(
            f'<c r="{chr(65+i)}{index}"><f>WEBSERVICE(&quot;http://never.invalid&quot;)</f><v>1.25</v></c>'
            if formula and key=='quantity' else
            f'<c r="{chr(65+i)}{index}" t="inlineStr"><is><t>{escape(str(value) if value is not None else "")}</t></is></c>'
            for i,(key,value) in enumerate(zip(record,values)))+'</row>'
    content=workbook(cells(['inventory_receipts.'+key for key in record],1)+cells(record.values(),2,True))
    ident=analyzed_files(c,[('formula.xlsx',content)]);review(c,ident);read=previewed(c,ident)
    response=c[0][5].get('/api/v1/imports/'+ident,params=dict(include_preview=True,preview_id=read['preview']['summary']['preview_id'],projection='source_effect'))
    assert response.status_code==200,response.text
    row=next(row for row in response.json()['data']['preview']['rows'] if (row['after'] or {}).get('domain')=='inventory_receipts')
    quantity=next(cell for cell in row['source_cells'] if cell['column_label']=='inventory_receipts.quantity')
    assert quantity['formula_present'] and quantity['raw_value']=='1.25' and row['after']['quantity']=='1.25'
    reason=next(cell for cell in row['source_cells'] if cell['column_label']=='inventory_receipts.reason')
    assert reason['raw_value'] is None and row['source_evidence_availability']=='partial'
    assert 'WEBSERVICE' not in response.text
