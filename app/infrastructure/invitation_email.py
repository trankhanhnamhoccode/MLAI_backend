"""TLS SMTP invitation formatter shared by explicit command and owned worker."""
from email.message import EmailMessage
import smtplib
import ssl
from urllib.parse import urlsplit,urlencode


def smtp_sender(settings):
    base=settings.auth_invitation_frontend_url or ''
    url=urlsplit(base)
    if (url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment
            or not settings.auth_smtp_host or not settings.auth_delivery_sender):
        raise ValueError('Configure HTTPS invitation callback and SMTP before dispatch')
    template='{invitation_id}' in url.path
    if '{' in base.replace('{invitation_id}','') or '}' in base.replace('{invitation_id}','') or base.count('{invitation_id}')>1:
        raise ValueError('Invalid invitation callback template')
    def send(address,invitation_id,secret):
        page=base.replace('{invitation_id}',str(invitation_id)) if template else base
        fragment=urlencode(dict(token=secret.get_secret_value()) if template else dict(invitation_id=str(invitation_id),token=secret.get_secret_value()))
        message=EmailMessage()
        message['From'],message['To'],message['Subject']=settings.auth_delivery_sender,address,'ShelfCash Staff invitation'
        message.set_content('Sign in with your verified account to review and accept:\n'+page+'#'+fragment)
        with smtplib.SMTP_SSL(settings.auth_smtp_host,settings.auth_smtp_port,timeout=20,context=ssl.create_default_context()) as smtp:
            if settings.auth_smtp_username:
                smtp.login(settings.auth_smtp_username,settings.auth_smtp_password.get_secret_value() if settings.auth_smtp_password else '')
            smtp.send_message(message)
    return send


class InvitationEmailTransport:
    def __init__(self,settings):
        self._sender=None
        if not settings.auth_email_delivery_enabled:return
        try:
            from app.infrastructure.invitation_secret import InvitationSecret
            InvitationSecret(settings.auth_delivery_encryption_key)
            url=urlsplit(settings.auth_invitation_frontend_url or '')
            if f'{url.scheme}://{url.netloc}' not in settings.auth_allowed_origins:raise ValueError('Callback Origin')
            self._sender=smtp_sender(settings)
        except (ValueError,TypeError):pass

    @property
    def available(self):return self._sender is not None

    def __call__(self,*args):
        if not self.available:raise RuntimeError('Invitation delivery unavailable')
        self._sender(*args)
