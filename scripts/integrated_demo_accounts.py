"""Synthetic holder provisioning and HTTPS probes for the owned integrated demo.

No business fixtures, real email, public operator endpoint or SQL authority writes.
"""
from __future__ import annotations

import json
import secrets
from uuid import UUID, uuid4

import httpx
from sqlalchemy import create_engine, text

from app.application.contracts.provisioning import IssueCredentialCommand, ProvisionStoreCommand, VerifiedAccountCommand
from app.application.use_cases.auth import now_utc
from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.application.use_cases.provisioning import AssistedProvisioning
from scripts.integrated_demo import DB, ORIGIN, PRIVATE, ROLE, URL, context, db_status, guard, private_json, settings


class Client:
    def __init__(self):
        self.http = httpx.Client(base_url=URL, verify=context(), trust_env=False, headers={'Origin': ORIGIN}, timeout=30)
        self.csrf = None

    def request(self, method, path, body=None, expected=200, match=None):
        headers = {}
        if method != 'GET':
            headers['Idempotency-Key'] = str(uuid4())
            if self.csrf: headers['X-CSRF-Token'] = self.csrf
        if match: headers['If-Match'] = match
        r = self.http.request(method, path, json=body, headers=headers)
        if r.status_code != expected:
            raise RuntimeError(f'HTTPS probe failed: HTTP {r.status_code}')
        return r

    def login(self, account):
        r=self.request('POST','/api/v1/auth/login',dict(email=account['email'],password=account['password'],remember_me=False))
        self.csrf=r.json()['data']['session']['csrf_token']
        return r

    def close(self):
        if self.csrf:
            self.request('POST','/api/v1/auth/logout',expected=204)
        self.http.close()


def provision() -> None:
    db_status(); s=settings(); engine=create_engine(s.database_url)
    accounts_path=PRIVATE/'accounts.json'
    accounts=json.loads(accounts_path.read_text()) if accounts_path.exists() else {}
    service=AssistedProvisioning(engine,s)
    client=Client()
    try:
        guard(engine,ROLE)
        for name in ('owner','staff','isolated_owner'):
            if name not in accounts:
                email=f'integrated-demo-{name.replace("_","-")}@example.test'
                command=dict(request_reference=f'integrated-demo-{name}',
                    evidence_reference='User-authorized synthetic demo holder, 2026-10-14; not real-world identity proof',
                    email=email,display_name='Integrated demo '+name)
                cls=VerifiedAccountCommand if name=='staff' else ProvisionStoreCommand
                if name!='staff': command['store_name']='Integrated demo '+name
                receipt=service.provision(cls(**command),s.auth_operator_id,s.auth_operator_key)
                accounts[name]=dict(email=email,user_id=str(receipt.user_id),
                    store_id=str(receipt.store_id) if receipt.store_id else None)
                private_json('accounts.json',accounts)
            account=accounts[name]
            if 'password' not in account:
                delivered=[]
                receipt=service.issue(IssueCredentialCommand(user_id=UUID(account['user_id']),purpose='SETUP',
                    verified_email=account['email'],request_reference=str(uuid4()),
                    evidence_reference='Authorized synthetic holder; private local capture, no SMTP'),
                    s.auth_operator_id,s.auth_operator_key,lambda address,token:delivered.append(token.get_secret_value()))
                if receipt.status!='delivered' or len(delivered)!=1: raise RuntimeError('Private delivery failed')
                password='Demo!'+secrets.token_urlsafe(24)
                # Save private recovery inputs before public completion; never print them.
                private_json(name+'-setup.json',dict(token=delivered[0],password=password,
                    frontend_url=ORIGIN+'/credentials/complete#token='+delivered[0]))
                client.request('POST','/api/v1/auth/credentials/complete',dict(token=delivered[0],password=password))
                account['password']=password
                private_json('accounts.json',accounts)
        owner=Client(); staff=Client()
        try:
            owner.login(accounts['owner']); staff.login(accounts['staff'])
            store=accounts['owner']['store_id']; base='/api/v1/stores/'+store
            # Existing membership is read through current public context, never regranted.
            current=staff.http.get(base)
            if current.status_code==404:
                created=owner.request('POST',base+'/staff-invitations',dict(email=accounts['staff']['email'],
                    grants=['menu.read'],permission_catalog_version='permissions-v3',
                    reason='Explicit synthetic demo: menu.read only; other privileges require Owner review'),expected=201)
                invitation=created.json()['data']['invitation']
                received=[]
                result=InvitationDispatcher(engine,s,now_utc).dispatch(s.auth_operator_id,s.auth_operator_key,
                    lambda address,identifier,token:received.append((str(identifier),token.get_secret_value())))
                if result['delivered']!=1 or len(received)!=1: raise RuntimeError('Private invitation delivery failed')
                identifier,token=received[0]
                if identifier!=invitation['invitation_id']: raise RuntimeError('Private delivery identity mismatch')
                private_json('staff-invitation.json',dict(invitation_id=identifier,token=token,
                    frontend_url=ORIGIN+'/invitations/'+identifier+'#token='+token))
                staff.request('POST','/api/v1/staff-invitations/'+identifier+'/accept',
                    dict(token=token,accept=True),expected=201,match=invitation['version'])
            elif current.status_code!=200: raise RuntimeError('Unexpected current membership state')
        finally: owner.close(); staff.close()
    finally: client.close(); engine.dispose()
    print('Synthetic Owner, Staff and isolated Owner provisioned via application/HTTPS. Staff: menu.read only. Private accounts.json holds credentials.')


def verify() -> None:
    db_status(); s=settings(); engine=create_engine(s.database_url)
    clients=[]
    try:
        guard(engine,ROLE)
        # Dependencies are probed directly with empty queues. No hidden job/business creation.
        with engine.connect() as c:
            for table in ('import_jobs', 'planning_runs', 'planning_exports', 'notification_intents'):
                if c.scalar(text('SELECT count(*) FROM '+table)):
                    raise ValueError('Idle dependency probe requires a demo with no jobs/runs/exports')
        # Never call run_one/recover beside live workers: a newly queued user job
        # could otherwise be claimed between the empty check and the command.
        with engine.connect() as c:
            if c.scalar(text('SELECT 1')) != 1:
                raise ValueError('Runtime DB dependency unavailable')
        with httpx.Client(verify=context(),trust_env=False,base_url=URL) as wire:
            assert wire.get('/health').status_code==200
            schema=wire.get('/openapi.json').json()
            methods={'get','post','put','patch','delete','options','head','trace'}
            from app.main import create_app
            expected=create_app(s).openapi()
            assert schema==expected
            inventory=(sum(len(methods & set(item)) for item in schema['paths'].values()),len(schema['paths']))
            for origin,allowed in ((ORIGIN,True),('https://untrusted.example',False),('http://localhost:5173',False)):
                r=wire.options('/api/v1/auth/login',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
                assert (r.headers.get('access-control-allow-origin')==origin)==allowed
                assert r.status_code==(200 if allowed else 400)
                if not allowed:
                    denied=wire.post('/api/v1/auth/login',json={},headers={'Origin':origin})
                    assert denied.status_code==403
            for endpoint,body in (
                ('register', dict(email='integrated-demo-probe@example.test',display_name='Unavailable delivery probe')),
                ('email-verifications/request', dict(email='integrated-demo-probe@example.test')),
                ('password-reset/request', dict(email='integrated-demo-staff@example.test')),
            ):
                r=wire.post('/api/v1/auth/'+endpoint,json=body,headers={'Origin':ORIGIN})
                assert r.status_code==503 and r.json()['error']['code']=='EMAIL_DELIVERY_UNAVAILABLE'
        accounts=json.loads((PRIVATE/'accounts.json').read_text())
        for name in ('owner','staff','isolated_owner'):
            client=Client(); clients.append(client)
            login=client.login(accounts[name])
            cookie=login.headers['set-cookie']
            assert '__Host-shelfcash_session=' in cookie and all(flag in cookie for flag in ('Secure','HttpOnly','SameSite=lax','Path=/'))
            assert 'Domain=' not in cookie
            assert client.request('GET','/api/v1/auth/me').json()['data']['user']['user_id']==accounts[name]['user_id']
            main='/api/v1/stores/'+accounts['owner']['store_id']
            other='/api/v1/stores/'+accounts['isolated_owner']['store_id']
            if name=='isolated_owner':
                client.request('GET',other)
                assert client.http.get(main).status_code==404
            else:
                read=client.request('GET',main).json()['data']
                assert client.http.get(other).status_code==404
                if name=='staff':
                    assert read['membership']['effective_permissions']==['menu.read']
                    assert client.http.get(main+'/inventory').status_code==403
                today=client.request('GET',main+'/today').json()['data']['sections']
                if name=='staff':
                    assert today['inventory']['availability']=='forbidden'
                else:
                    assert today['inventory']['completeness']=='unknown'
                    assert any(not action['can_execute'] for action in today['readiness']['value']['actions'])
                assert client.request('GET','/api/v1/notifications').json()['data']['items']==[]
                assert client.request('GET','/api/v1/notifications/unread-count').json()['data']['unread_count']==0
            missing=client.http.post('/api/v1/auth/logout',headers={'Origin':ORIGIN})
            assert missing.status_code==403
        # Fresh connection verifies committed authority plus absence of operational facts.
        with engine.connect() as c:
            assert c.scalar(text('SELECT count(*) FROM stores'))==2
            assert c.scalar(text('SELECT count(*) FROM users'))==3
            assert c.scalar(text("SELECT count(*) FROM membership_grants WHERE permission='menu.read'"))==1
            assert c.scalar(text('SELECT count(*) FROM membership_grants'))==1
            for table in ('products','ingredients','inventory_movements','planning_runs','import_jobs'):
                assert c.scalar(text('SELECT count(*) FROM '+table))==0
        workers=json.loads((PRIVATE/'workers.json').read_text())
        assert all(workers[k] for k in ('import_alive','planning_alive','pdf_alive','notification_alive'))
        assert not workers['email_enabled']
        print(f'Verified HTTPS/TLS, OpenAPI{inventory[0]}/{inventory[1]}, exact CORS/Origin, secure cookie, login/me/CSRF/isolation, Today/inbox, read-only DB/queue probes, four worker observations and fresh committed state. No browser E2E or real email.')
    finally:
        for client in clients: client.close()
        engine.dispose()


def main() -> int:
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('provision','verify'))
    action=parser.parse_args().action
    try:
        globals()[action]()
        return 0
    except Exception as error:
        print(f'Demo account/probe failed ({type(error).__name__}); raw responses/secrets withheld.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
