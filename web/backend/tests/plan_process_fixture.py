"""Spawn-safe actual HTTP readonly plan recovery; no funding installation."""
from pathlib import Path
import json


def read_plan(path,rid,ref,cookie,output):
    from .source_v11_process_fixture import configure
    configure(path)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import auth,research
    from services.auth_store import AuthStore
    auth._store=lambda:AuthStore(Path(path))
    research.enabled=lambda:True
    app=FastAPI();app.include_router(research.router,prefix='/api')
    with TestClient(app,base_url='https://beta.structural.bytedance.city') as client:
        client.cookies.set('phase_session',cookie)
        response=client.get('/api/research/'+rid+'/plan-results/'+ref)
        value=response.json()
        assert response.status_code==200
        Path(output).write_text(json.dumps(value,sort_keys=True,ensure_ascii=False))


def kill_upgrade(path,cut):
    import os,sqlite3
    from .source_v11_process_fixture import configure
    configure(path)
    from research.plan_financial import provision_plan_v12
    native=sqlite3.connect
    targets={'journal':'PRAGMA journal_mode=DELETE','rebuild':'CREATE TABLE research_tasks_plan12','resource':'CREATE TABLE research_plan_funding','marker':'UPDATE research_schema SET version=12'}
    class Crash(sqlite3.Connection):
        def execute(self,sql,*a,**k):
            result=super().execute(sql,*a,**k)
            if cut in targets and sql.startswith(targets[cut]):os._exit(81)
            return result
        def commit(self):
            try:version=super().execute('SELECT version FROM research_schema').fetchone()[0]
            except sqlite3.Error:version=None
            if version==12 and cut=='before-commit':os._exit(81)
            result=super().commit()
            if version==12 and cut=='after-commit':os._exit(82)
            return result
    sqlite3.connect=lambda *a,**k:native(*a,**k) if 'factory' in k else native(*a,factory=Crash,**k)
    provision_plan_v12(Path(path))
    raise AssertionError('actual plan migration boundary was not reached')
