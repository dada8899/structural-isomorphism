"""Actual mail sender with in-memory transports only; never SMTP network IO."""
import json
import smtplib
import ssl

import pytest

from api import auth


@pytest.fixture
def configured(monkeypatch,tmp_path):
    values={'STRUCTURAL_ENV':'test','AUTH_DEV_MODE':'false','AUTH_DATA_DIR':str(tmp_path/'auth'),
        'SMTP_HOST':'smtp.example.invalid','SMTP_FROM_EMAIL':'sender@example.invalid',
        'SMTP_PORT':'587','SMTP_TIMEOUT_SECONDS':'2.5',
        'SMTP_USERNAME':'synthetic-user','SMTP_PASSWORD':'synthetic-password'}
    for name,value in values.items():monkeypatch.setenv(name,value)
    for name in ('SMTP_USE_SSL','SMTP_STARTTLS'):monkeypatch.delenv(name,raising=False)
    events=[];opened=[];tls=[];contexts=[]
    default_context=ssl.create_default_context
    def actual_context(*args,**kwargs):
        context=default_context(*args,**kwargs);contexts.append(context);return context
    monkeypatch.setattr(ssl,'create_default_context',actual_context)
    class Transport:
        def __enter__(self):events.append('enter');return self
        def __exit__(self,*args):events.append('exit')
        def starttls(self,**kwargs):tls.append(kwargs.get('context'));events.append('starttls')
        def login(self,*args):events.append('login')
        def send_message(self,message):events.append('send')
    Transport.contexts=contexts
    def factory(kind):
        def create(host,port,**kwargs):
            opened.append({'kind':kind,'host':host,'port':port,**kwargs});events.append('open:'+kind)
            return Transport()
        return create
    monkeypatch.setattr(auth.smtplib,'SMTP',factory('SMTP'))
    monkeypatch.setattr(auth.smtplib,'SMTP_SSL',factory('SSL'))
    return events,opened,tls,Transport


def verified(context):
    assert isinstance(context,ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode==ssl.CERT_REQUIRED


def send():auth._send_email('recipient@example.invalid','synthetic subject','synthetic body')


@pytest.mark.parametrize('flag',[None,'false','true'])
def test_implicit_465_uses_verified_ssl_once(configured,monkeypatch,flag):
    events,opened,tls,transport=configured
    monkeypatch.setenv('SMTP_PORT','465')
    if flag is not None:monkeypatch.setenv('SMTP_USE_SSL',flag)
    send()
    assert len(opened)==1 and opened[0]['kind']=='SSL'
    assert opened[0]['host']=='smtp.example.invalid' and opened[0]['port']==465
    assert opened[0]['timeout']==2.5
    verified(opened[0].get('context'))
    assert len(transport.contexts)==1 and opened[0]['context'] is transport.contexts[0]
    assert tls==[] and events==['open:SSL','enter','login','send','exit']


def test_explicit_ssl_on_another_port_uses_verified_context(configured,monkeypatch):
    events,opened,tls,transport=configured
    monkeypatch.setenv('SMTP_PORT','2465');monkeypatch.setenv('SMTP_USE_SSL','true')
    send()
    assert len(opened)==1 and opened[0]['kind']=='SSL' and opened[0]['port']==2465
    verified(opened[0].get('context'))
    assert len(transport.contexts)==1 and opened[0]['context'] is transport.contexts[0]
    assert events.count('send')==1 and tls==[]


def test_starttls_uses_verified_context_before_auth_and_one_send(configured):
    events,opened,tls,transport=configured
    send()
    assert len(opened)==1 and opened[0]['kind']=='SMTP' and opened[0]['timeout']==2.5
    assert len(tls)==1
    verified(tls[0])
    assert len(transport.contexts)==1 and tls[0] is transport.contexts[0]
    assert events==['open:SMTP','enter','starttls','login','send','exit']


@pytest.mark.parametrize('mode',['SSL','STARTTLS'])
@pytest.mark.parametrize('error_type',[ssl.SSLCertVerificationError,ssl.SSLError])
def test_tls_refusal_never_reaches_auth_or_send(configured,monkeypatch,mode,error_type):
    events,opened,tls,transport=configured
    first=error_type('synthetic TLS refusal')
    if mode=='SSL':
        monkeypatch.setenv('SMTP_PORT','465');monkeypatch.setenv('SMTP_USE_SSL','true')
        def refused(host,port,**kwargs):
            opened.append({'kind':'SSL','context':kwargs.get('context')});raise first
        monkeypatch.setattr(auth.smtplib,'SMTP_SSL',refused)
    else:
        def refused(self,**kwargs):tls.append(kwargs.get('context'));events.append('starttls');raise first
        monkeypatch.setattr(transport,'starttls',refused)
    with pytest.raises(error_type) as caught:send()
    assert caught.value is first and len(opened)==1
    context=opened[0].get('context') if mode=='SSL' else tls[0]
    verified(context)
    assert len(transport.contexts)==1 and context is transport.contexts[0]
    assert 'login' not in events and 'send' not in events
    assert events.count('exit')==(0 if mode=='SSL' else 1)


def test_send_failure_propagates_without_retry(configured,monkeypatch):
    events,opened,_,transport=configured
    first=smtplib.SMTPDataError(550,b'synthetic refusal')
    def refused(self,message):events.append('send');raise first
    monkeypatch.setattr(transport,'send_message',refused)
    with pytest.raises(smtplib.SMTPDataError) as caught:send()
    assert caught.value is first and len(opened)==1 and events.count('send')==1
    assert events[-1]=='exit'


def test_explicit_plain_owned_loopback_remains_plain(configured,monkeypatch):
    events,opened,tls,_=configured
    monkeypatch.setenv('SMTP_HOST','127.0.0.1');monkeypatch.setenv('SMTP_PORT','2525')
    monkeypatch.setenv('SMTP_USE_SSL','false');monkeypatch.setenv('SMTP_STARTTLS','false')
    def no_tls():raise AssertionError('plain fixture must not create TLS context')
    monkeypatch.setattr(ssl,'create_default_context',no_tls)
    send()
    assert len(opened)==1 and opened[0]['kind']=='SMTP' and tls==[]
    assert events==['open:SMTP','enter','login','send','exit']


def test_dev_outbox_bypasses_smtp(configured,monkeypatch):
    events,opened,tls,_=configured
    monkeypatch.setenv('AUTH_DEV_MODE','true')
    send()
    assert events==opened==tls==[]
    rows=[json.loads(line) for line in auth._outbox_file().read_text().splitlines()]
    assert len(rows)==1 and rows[0]['to']=='recipient@example.invalid'
    assert rows[0]['subject']=='synthetic subject' and rows[0]['text']=='synthetic body'


@pytest.mark.parametrize('host',['smtp.example.invalid','127.0.0.1'])
def test_production_plaintext_refuses_before_connection_or_credential_read(configured,monkeypatch,host):
    events,opened,tls,_=configured
    monkeypatch.setenv('STRUCTURAL_ENV','prod');monkeypatch.setenv('SMTP_HOST',host)
    monkeypatch.setenv('SMTP_PORT','2525');monkeypatch.setenv('SMTP_USE_SSL','false');monkeypatch.setenv('SMTP_STARTTLS','false')
    original=auth.os.getenv
    def no_credentials(name,*args):
        if name in ('SMTP_USERNAME','SMTP_PASSWORD'):raise AssertionError('plaintext must not read credentials')
        return original(name,*args)
    monkeypatch.setattr(auth.os,'getenv',no_credentials)
    with pytest.raises(RuntimeError,match='production SMTP requires verified TLS'):send()
    assert events==opened==tls==[]


@pytest.fixture
def owned_tls_smtp(request):
    from contextlib import closing
    import socketserver,threading
    from web.backend.tests.acceptance.owned_smtp_tls import owned_smtp_tls,StartTLSHandler
    case=request.param;messages=[];commands=[]
    with owned_smtp_tls(trust=case!='untrusted',server_ip='127.0.0.2' if case=='wrong_san' else '127.0.0.1') as (context,ca_file):
        class Handler(StartTLSHandler):
            timeout=3
            def handle(self):
                self.wfile.write(b'220 owned SMTP\r\n')
                while True:
                    line=self.rfile.readline(8192)
                    if not line:return
                    verb=line.split(None,1)[0].upper()
                    if self.smtp_tls_command(verb):
                        if self.smtp_tls_failed:return
                        continue
                    if verb in (b'AUTH',b'MAIL',b'DATA'):commands.append(verb)
                    if verb==b'DATA':
                        self.wfile.write(b'354 data\r\n');body=bytearray()
                        while True:
                            part=self.rfile.readline(8192)
                            if part==b'.\r\n':break
                            if not part or len(body)+len(part)>65536:return
                            body.extend(part)
                        messages.append(bytes(body));self.wfile.write(b'250 stored\r\n')
                    elif verb==b'QUIT':self.wfile.write(b'221 done\r\n');return
                    else:self.wfile.write(b'250 ok\r\n')
        server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler)
        server.daemon_threads=True;server.smtp_tls_context=context
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:yield server.server_address[1],messages,commands,case
        finally:
            server.shutdown();server.server_close();thread.join(4)
            assert not thread.is_alive()


@pytest.mark.parametrize('owned_tls_smtp',['valid','untrusted','wrong_san'],indirect=True)
def test_actual_owned_starttls_verifies_chain_and_san_before_send(owned_tls_smtp,monkeypatch):
    port,messages,commands,case=owned_tls_smtp
    for name,value in {'STRUCTURAL_ENV':'prod','AUTH_DEV_MODE':'false','SMTP_HOST':'127.0.0.1',
        'SMTP_PORT':str(port),'SMTP_FROM_EMAIL':'sender@example.invalid','SMTP_TIMEOUT_SECONDS':'2',
        'SMTP_USE_SSL':'false','SMTP_STARTTLS':'true'}.items():monkeypatch.setenv(name,value)
    monkeypatch.delenv('SMTP_USERNAME',raising=False);monkeypatch.delenv('SMTP_PASSWORD',raising=False)
    if case=='valid':
        send();assert len(messages)==1 and commands.count(b'DATA')==1
    else:
        with pytest.raises(ssl.SSLCertVerificationError):send()
        assert messages==[] and commands==[]
