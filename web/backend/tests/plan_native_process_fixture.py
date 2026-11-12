"""Owned native-plan migration kills and fresh actual HTTP history reads."""
from pathlib import Path
import json


def kill_upgrade(path,cut):
    import os,sqlite3
    from .source_v11_process_fixture import configure
    configure(path)
    from research.plan_native_financial import provision_native_v13
    native=sqlite3.connect
    targets={'journal':'PRAGMA journal_mode=DELETE','rebuild':'CREATE TABLE research_tasks_native13','resource':'CREATE TABLE research_plan_native_funding','marker':'UPDATE research_schema SET version=13'}
    class Crash(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            result=super().execute(sql,*args,**kwargs)
            if cut in targets and sql.startswith(targets[cut]):os._exit(81)
            return result
        def commit(self):
            try:version=super().execute('SELECT version FROM research_schema').fetchone()[0]
            except sqlite3.Error:version=None
            if version==13 and cut=='before-commit':os._exit(81)
            result=super().commit()
            if version==13 and cut=='after-commit':os._exit(82)
            return result
    sqlite3.connect=lambda *args,**kwargs:native(*args,**kwargs) if 'factory' in kwargs else native(*args,factory=Crash,**kwargs)
    provision_native_v13(Path(path))
    raise AssertionError('actual native migration boundary was not reached')


def read_history(path,rid,ref,output):
    import os
    from urllib.parse import parse_qs,urlsplit
    from .source_v11_process_fixture import configure
    path=configure(path);beta='https://beta.structural.bytedance.city'
    os.environ.update({'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(path.parent),'STRUCTURAL_SSO_DATA_DIR':str(path.parent),
      'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':beta,
      'JWT_SECRET':'native13-history-synthetic-secret-0123456789','STRUCTURAL_SSO_SECRET':'native13-history-synthetic-secret-0123456789',
      'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'})
    from api import auth,research
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mail=[];auth._send_email=lambda to,subject,text:mail.append(text);research.enabled=lambda:True
    app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    with TestClient(app,base_url=beta) as client:
        response=client.post('/api/auth/request-link',json={'email':'fresh@example.invalid'},headers={'origin':beta});assert response.status_code==200,response.text
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        response=client.post('/api/auth/verify',json={'token':token},headers={'origin':beta});assert response.status_code==200,response.text
        response=client.get('/api/research/'+rid+'/plan-results/'+ref);assert response.status_code==200,response.text
        history=client.get('/api/research/'+rid);assert history.status_code==200,history.text
        Path(output).write_text(json.dumps({'result':response.json(),'history':history.json()},sort_keys=True))
