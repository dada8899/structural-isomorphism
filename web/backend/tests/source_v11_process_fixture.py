"""Owned synthetic formal Source worker processes; no Main admission."""
from pathlib import Path
import importlib,json


def configure(path):
    path=Path(path)
    for namespace in ('services.runtime_paths','web.backend.services.runtime_paths'):
        module=importlib.import_module(namespace)
        module.STATE_ROOT=path.parent;module.CACHE_ROOT=path.parent.parent/'cache';module.LOG_ROOT=path.parent/'logs'
    from research import source_integration
    source_integration.enabled=lambda:True
    return path


def reopen(path,task_id,output):
    path=configure(path)
    from services.auth_store import AuthStore
    from research import ResearchStore,ResearchRunner
    from research.authorization import AuthorizationGate
    store=ResearchStore(AuthStore(path))
    with AuthorizationGate(store).source_task_gate(task_id) as lease:identity=lease.identity
    state=ResearchRunner(store).run_once(task_id)
    Path(output).write_text(json.dumps({'state':state,'identity':identity}))


def crash_after_claim(path,task_id):
    import os
    from functools import partial
    path=configure(path)
    from services.auth_store import AuthStore
    from services.sqlite_utils import PrivateAuthConnection
    from research import ResearchStore,ResearchRunner
    from research.source_policy import PinnedPublicTransport
    from web.backend.tests.source_http_fixture import get_local
    execute,commit=PrivateAuthConnection.execute,PrivateAuthConnection.commit
    claimed=set()
    def on_execute(self,sql,*a,**k):
        result=execute(self,sql,*a,**k)
        if sql.startswith('UPDATE research_source_runs SET started=1'):claimed.add(id(self))
        return result
    def on_commit(self):
        commit(self)
        if id(self) in claimed:os._exit(81)
    PrivateAuthConnection.execute=on_execute;PrivateAuthConnection.commit=on_commit
    ResearchRunner(ResearchStore(AuthStore(path)),source_transport=PinnedPublicTransport(_worker=partial(get_local,0))).run_once(task_id)
    raise AssertionError('owned claim kill point was not reached')


def schema_kill(path,cut):
    """Actual offline migration killed at owned native SQLite boundaries."""
    import os,sqlite3
    configure(path)
    from research.source_guard import provision_source_v11
    native=sqlite3.connect
    targets={'journal':'PRAGMA journal_mode=DELETE','consent':'ALTER TABLE research_source_approvals ADD COLUMN consent_origin',
        'resource':'CREATE TABLE research_source_resources','marker':'UPDATE research_schema SET version=11'}
    class Crash(sqlite3.Connection):
        def execute(self,sql,*a,**k):
            value=super().execute(sql,*a,**k)
            if cut in targets and sql.startswith(targets[cut]):os._exit(81)
            return value
        def commit(self):
            try:version=super().execute('SELECT version FROM research_schema').fetchone()[0]
            except sqlite3.Error:version=None
            if version==11 and cut=='before-commit':os._exit(81)
            value=super().commit()
            if version==11 and cut=='after-commit':os._exit(82)
            return value
    sqlite3.connect=lambda *a,**k:native(*a,**k) if 'factory' in k else native(*a,factory=Crash,**k)
    provision_source_v11(Path(path))
    raise AssertionError('owned Source11 kill boundary was not reached')
