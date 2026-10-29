"""Canonical fresh-spawn workers for synthetic private registration tests.

No application, store or process is created on import. Tokens remain arguments
on the existing multiprocessing pipe, never executable strings or argv.
"""
import os
import sqlite3

BETA='https://beta.structural.bytedance.city'


def _verify_process(root,token,barrier,queue):
    """Real fresh process; safety audit metadata is inherited, no store stubs."""
    from pathlib import Path
    from services import runtime_paths as paths
    paths.STATE_ROOT=Path(root);paths.CACHE_ROOT=Path(root).parent/'cache';paths.LOG_ROOT=Path(root)/'logs'
    from api import auth as child_auth
    from starlette.requests import Request
    from starlette.responses import Response
    import asyncio
    request=Request({'type':'http','method':'POST','scheme':'https','path':'/api/auth/verify',
        'query_string':b'','server':('beta.structural.bytedance.city',443),'client':('127.0.0.1',10000),
        'headers':[(b'host',b'beta.structural.bytedance.city'),(b'origin',BETA.encode())]})
    barrier.wait(10)
    result=asyncio.run(child_auth.verify(child_auth.VerifyBody(token=token),request,Response()))
    leaked=[];blocked=[]
    try:
        import audit_bootstrap as audit
        blocked=list(audit.blocked)
        for conn in audit.handles:
            try:conn.execute('SELECT 1')
            except sqlite3.Error:pass
            else:leaked.append('native-open');conn.close()
    except ImportError:pass
    queue.put((result.status_code,bool(result.headers.get('set-cookie')),leaked,blocked))


def _die_registration_process(root,token,point):
    from pathlib import Path
    from services import runtime_paths as paths,auth_registration as child_registration
    paths.STATE_ROOT=Path(root);paths.CACHE_ROOT=Path(root).parent/'cache';paths.LOG_ROOT=Path(root)/'logs'
    if point=='birth':
        child_registration._mark_ready=lambda *_a,**_k:os._exit(77)
    elif point=='ready':
        child_registration._finalize=lambda *_a,**_k:os._exit(77)
    else:
        from services.sqlite_utils import PrivateAuthConnection
        original=PrivateAuthConnection.commit
        def commit(self):
            finalized=self.execute("SELECT 1 FROM auth_registration_operations WHERE state='finalized'").fetchone()
            original(self)
            if finalized:os._exit(77)
        PrivateAuthConnection.commit=commit
    from api import auth as child_auth
    from starlette.requests import Request
    from starlette.responses import Response
    import asyncio
    request=Request({'type':'http','method':'POST','scheme':'https','path':'/api/auth/verify',
        'query_string':b'','server':('beta.structural.bytedance.city',443),'client':('127.0.0.1',10000),
        'headers':[(b'host',b'beta.structural.bytedance.city'),(b'origin',BETA.encode())]})
    asyncio.run(child_auth.verify(child_auth.VerifyBody(token=token),request,Response()))
