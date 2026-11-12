"""Ephemeral test CA and real STARTTLS for the existing owned SMTP fixtures."""
from contextlib import contextmanager
from pathlib import Path
import os
import socketserver
import ssl
import subprocess
import tempfile


@contextmanager
def owned_smtp_tls(*,trust=True,server_ip='127.0.0.1'):
    if server_ip not in ('127.0.0.1','127.0.0.2'):raise ValueError('fixed synthetic SMTP SAN required')
    with tempfile.TemporaryDirectory(prefix='owned-smtp-tls-',dir=os.environ.get('TMPDIR')) as directory:
        root=Path(directory);root.chmod(0o700)
        ca_key=root/'ca.key';ca=root/'ca.pem';key=root/'server.key';csr=root/'server.csr';certificate=root/'server.pem'
        ca_config=root/'ca.cnf'
        ca_config.write_text('[req]\ndistinguished_name=subject\nx509_extensions=extensions\nprompt=no\n[subject]\nCN=Owned SMTP Test CA\n[extensions]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n')
        extensions=root/'extensions.cnf'
        extensions.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=IP:'+server_ip+'\n')
        commands=(
            ['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(ca_key),'-out',str(ca),'-days','1','-config',str(ca_config)],
            ['/usr/bin/openssl','req','-new','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(csr),'-subj','/CN=Owned SMTP Test Server'],
            ['/usr/bin/openssl','x509','-req','-in',str(csr),'-CA',str(ca),'-CAkey',str(ca_key),'-CAcreateserial','-out',str(certificate),'-days','1','-extfile',str(extensions)],
        )
        for command in commands:
            subprocess.run(command,input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=8)
        for path in root.iterdir():path.chmod(0o600)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificate,key)
        previous=os.environ.get('SSL_CERT_FILE')
        if trust:os.environ['SSL_CERT_FILE']=str(ca)
        try:yield context,ca
        finally:
            if trust:
                if previous is None:os.environ.pop('SSL_CERT_FILE',None)
                else:os.environ['SSL_CERT_FILE']=previous


class StartTLSHandler(socketserver.StreamRequestHandler):
    """Only protocol upgrade; existing DATA/recipient/size/deadline logic stays."""
    def setup(self):
        super().setup();self.smtp_tls_active=False;self.smtp_tls_failed=False

    def smtp_socket_upgraded(self,old,new):pass
    def smtp_socket_closed(self,connection):pass

    def smtp_tls_command(self,verb):
        if verb in (b'EHLO',b'HELO'):
            self.wfile.write(b'250-owned SMTP\r\n'+(b'250-STARTTLS\r\n' if not self.smtp_tls_active else b'')+b'250 SIZE 65536\r\n')
            return True
        if verb==b'STARTTLS':
            if self.smtp_tls_active:
                self.wfile.write(b'454 TLS already active\r\n');return True
            self.wfile.write(b'220 Begin TLS\r\n');self.wfile.flush()
            old=self.connection
            self.rfile.close();self.wfile.close()
            try:secured=self.server.smtp_tls_context.wrap_socket(old,server_side=True)
            except (ssl.SSLError,OSError):
                self.smtp_tls_failed=True
                old.close()
                return True
            self.connection=self.request=secured
            self.smtp_socket_upgraded(old,secured)
            # Rebuild stdlib streams on the actual upgraded socket. Keep the
            # handler's original timeout and buffer settings unchanged.
            socketserver.StreamRequestHandler.setup(self)
            self.smtp_tls_active=True
            return True
        if not self.smtp_tls_active and verb in (b'AUTH',b'MAIL',b'RCPT',b'DATA'):
            self.wfile.write(b'530 STARTTLS required\r\n');return True
        return False

    def finish(self):
        try:super().finish()
        finally:
            self.connection.close()
            self.smtp_socket_closed(self.connection)
