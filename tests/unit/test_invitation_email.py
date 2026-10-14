"""No SMTP/network: confirm parameterized FE links and one email worker."""
from uuid import uuid4
from pydantic import SecretStr
from app.config import Settings
from app.infrastructure.invitation_email import smtp_sender


def test_confirmed_invitation_route_keeps_only_token_in_fragment(monkeypatch):
    messages=[]
    class SMTP:
        def __init__(self,*args,**kwargs):assert kwargs['context'].verify_mode!=0
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def send_message(self,message):messages.append(message)
    monkeypatch.setattr('app.infrastructure.invitation_email.smtplib.SMTP_SSL',SMTP)
    settings=Settings(_env_file=None,auth_smtp_host='smtp.fixture.test',auth_delivery_sender='fixture@example.test',
        auth_invitation_frontend_url='https://localhost:5173/invitations/{invitation_id}')
    identifier=uuid4();smtp_sender(settings)('fixture@example.test',identifier,SecretStr('synthetic-token'))
    assert f'https://localhost:5173/invitations/{identifier}#token=synthetic-token' in messages[0].get_content()


def test_single_email_worker_processes_all_three_queues():
    from app.infrastructure.email_verification_worker import EmailVerificationWorker
    calls=[]
    class Dispatcher:
        def __init__(self,name):self.name=name
        def dispatch(self,limit):calls.append((self.name,limit))
    worker=EmailVerificationWorker(Dispatcher('verify'),reset_dispatcher=Dispatcher('reset'),
        invitation_dispatch=lambda:(calls.append(('invite',1)),worker._stop.set()))
    worker.start();worker._thread.join(timeout=3)
    assert not worker._thread.is_alive()
    assert calls==[('verify',1),('reset',1),('invite',1)]
