"""Actual guarded history metadata and existing import worker, no reparse GET."""
from datetime import datetime,timezone,timedelta
from uuid import UUID,uuid4
from sqlalchemy.orm import Session
from tests.integration.test_planning_public import flow,config,env,submit
from tests.integration.test_import_staging import imp,analyzed,post,sales_bytes
from app.application.use_cases.import_history import ImportHistoryReads
from app.models import ImportBatch,ImportFile,PlanningRun


def test_run_history_snapshot_filters_and_revision_invalidation(flow):
    c,_,_,worker=flow;client=c[0][5];base=f'/api/v1/stores/{c[1].store_id}/procurement-plans'
    responses=[submit(c) for _ in range(3)]
    first=client.get(base,params={'limit':1});assert first.status_code==200,first.text
    value=first.json();assert value['meta']['pagination']['total_count']==3
    assert value['data']['items'][0]['created_by']=={'user_id':str(c[1].user_id),'display_name':None}
    cursor=value['meta']['pagination']['next_cursor'];assert cursor
    second=client.get(base,params={'limit':1,'cursor':cursor});assert second.status_code==200,second.text
    assert first.json()['data']['items'][0]['run_id']!=second.json()['data']['items'][0]['run_id']
    assert client.get(base,params={'status':'failed'}).json()['data']['items']==[]
    assert client.get(base,params={'forecast_start_from':'2026-10-11'}).json()['data']['items']==[]
    assert client.get(base,params={'forecast_start_from':'2026-10-12','forecast_start_to':'2026-10-11'}).status_code==422
    assert client.get(base,params={'status':'completed,invalid'}).status_code==422
    record=worker.run_one();assert record.status=='completed'
    stale=client.get(base,params={'limit':1,'cursor':cursor});assert stale.status_code==409,stale.text
    assert stale.json()['error']['code']=='SNAPSHOT_NOT_AVAILABLE'
    with Session(c[0][1]) as s:assert s.query(PlanningRun).count()==3
    from pathlib import Path
    Path('runtime/s410/n9_actual.json').write_text(first.text,encoding='utf-8')


def test_import_history_first_upload_timezone_distinct_filters_and_draft_exclusion(imp):
    client=imp[0][5];client.app.state.import_history=ImportHistoryReads(imp[2])
    store=imp[1].store_id;base=f'/api/v1/stores/{store}/imports'
    ident=analyzed(imp)
    draft=post(imp,'/stores/'+str(store)+'/imports',{'data_date':'2026-10-01'})
    assert draft.status_code==201
    # Actual upload+analysis; chosen timestamp tests local date boundary and
    # data_date distinction, without making a completion record up.
    with Session(imp[0][1]) as s:
        batch=s.get(ImportBatch,UUID(ident));batch.imported_at=datetime(2026,10,9,20,tzinfo=timezone.utc);s.commit()
    calendar=client.get(base+'/calendar',params={'month':'2026-10'});assert calendar.status_code==200,calendar.text
    data=calendar.json()['data'];assert data['matched_import_count']==data['unfiltered_import_count']==1
    assert data['days']==[{'date':'2026-10-10','import_count':1}]
    history=client.get(base,params={'import_date':'2026-10-10','category':'sales','q':'sales.csv','status':'in_progress'})
    assert history.status_code==200,history.text
    assert history.json()['data']['items'][0]['import_id']==ident
    assert history.json()['data']['items'][0]['status']=='in_progress'
    assert history.json()['meta']['unfiltered_date_count']==1
    assert client.get(base,params={'import_date':'2026-10-09'}).json()['data']['items']==[]
    mismatch=client.get(base,params={'import_date':'2026-10-10','category':'supplier','q':'sales.csv'})
    assert mismatch.json()['data']['items']==[] and mismatch.json()['meta']['unfiltered_date_count']==1
    assert client.get(base+'/calendar',params={'month':'2026-99'}).json()['error']['code']=='INVALID_MONTH'
    with Session(imp[0][1]) as s:
        batch=s.get(ImportBatch,UUID(ident));assert not (batch.analysis_json or {}).get('completion')
        assert s.query(ImportBatch).count()==2 and s.query(ImportFile).count()==1
    from pathlib import Path
    Path('runtime/s410/h01_actual.json').write_text(calendar.text,encoding='utf-8')
    Path('runtime/s410/h02_actual.json').write_text(history.text,encoding='utf-8')


def test_import_same_file_and_snapshot_cursor_and_sensitive_current_rights(imp,monkeypatch):
    from tests.integration.test_import_commit import analyzed_files
    from tests.integration.test_import_staging import csv_source
    from tests.integration.test_auth_public import setup,login
    from app.models import Supplier,StoreMembership
    from app.models.auth import MembershipGrant
    from app.application.use_cases import import_staging
    client=imp[0][5];client.app.state.import_history=ImportHistoryReads(imp[2]);store=imp[1].store_id
    supplier=uuid4()
    with Session(imp[0][1]) as s:s.add(Supplier(id=supplier,store_id=store,name='Synthetic Supplier',active=True));s.commit()
    mixed=analyzed_files(imp,[('supplier.csv',csv_source('suppliers',[dict(source_supplier_key=str(supplier),name='Synthetic Supplier',active=True)])),
        ('sales.csv',sales_bytes(imp))])
    another=analyzed(imp);base=f'/api/v1/stores/{store}/imports'
    params={'import_date':'2026-10-10','limit':1}
    first=client.get(base,params=params);assert first.status_code==200,first.text
    cursor=first.json()['meta']['pagination']['next_cursor'];assert cursor
    # category and q on different files do not match a mixed batch.
    mismatch=client.get(base,params={**params,'category':'supplier','q':'sales.csv'})
    assert mismatch.json()['data']['items']==[]
    correct=client.get(base,params={**params,'category':'supplier','q':'supplier.csv'})
    assert correct.json()['data']['items'][0]['import_id']==mixed and correct.json()['data']['items'][0]['file_count']==2
    def forbidden(*args,**kwargs):raise AssertionError('History GET parsed/recomputed business data')
    monkeypatch.setattr(import_staging,'parse_source',forbidden)
    assert client.get(base+'/calendar',params={'month':'2026-10'}).status_code==200
    with Session(imp[0][1]) as s:
        batch=s.get(ImportBatch,UUID(another));batch.status='failed';batch.revision='history-source-change';s.commit()
    stale=client.get(base,params={**params,'cursor':cursor});assert stale.status_code==409 and stale.json()['error']['code']=='SNAPSHOT_NOT_AVAILABLE'
    staff=setup(imp[0],'history-staff@example.test',store=False)
    with Session(imp[0][1]) as s:
        member=StoreMembership(id=uuid4(),store_id=store,user_id=staff.user_id,role='STAFF',active=True);s.add(member);s.flush()
        for grant in ('import.read','menu.read','sales.read'):s.add(MembershipGrant(membership_id=member.id,permission=grant))
        mid=member.id;s.commit()
    login(imp[0],'history-staff@example.test')
    # Filtering must not hide unauthorized supplier contents/counts.
    denied=client.get(base,params={**params,'category':'sales'});assert denied.status_code==403 and denied.json()['data'] is None
    assert client.get(base+'/calendar',params={'month':'2026-10','category':'sales'}).status_code==403


def test_actual_i06_completion_alone_normalizes_terminal_history(imp):
    from tests.integration.test_import_commit import ready,commit,finished
    client=imp[0][5];client.app.state.import_history=ImportHistoryReads(imp[2])
    ident,preview,revision=ready(imp)
    base=f'/api/v1/stores/{imp[1].store_id}/imports'
    assert client.get(base,params={'import_date':'2026-10-10','status':'completed'}).json()['data']['items']==[]
    completion=finished(imp,ident,commit(imp,ident,preview,revision))
    after=client.get(base,params={'import_date':'2026-10-10','status':completion['status']});assert after.status_code==200,after.text
    assert after.json()['data']['items'][0]['status']==completion['status']
    assert client.get('/api/v1/imports/'+ident+'/completion').json()['data']==completion
