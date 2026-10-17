"""Canonical spawn entrypoints for synthetic research persistence probes.

Only test process targets live here; application helpers remain in the original
test modules. No app, database or process is created on import.
"""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

from fastapi.testclient import TestClient
from research.authorization import AuthorizationGate
from research.store import ResearchStore


def _api_process(cookie, path, payload, key, ready, start, result):
    from web.backend.tests.test_research_persistence import app, post

    client = TestClient(app())
    client.cookies.set("phase_session", cookie)
    ready.put(True)
    if not start.wait(15):
        return
    response = post(client, path, payload, key)
    result.put((response.status_code, response.json().get("data", {}).get("research", {}).get("id")))
    client.close()


def _hold_gate(path, principal, acquired):
    from services.auth_store import AuthStore
    gate = AuthorizationGate(ResearchStore(AuthStore(Path(path))))
    with gate.owner_gate(principal):
        acquired.set()
        time.sleep(20)


def _run_owned_probe(program, cwd):
    """Register a new session here; exceptions clean its group even after exit."""
    with subprocess.Popen(
        [sys.executable, '-c', program], cwd=cwd, start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=120)
        except BaseException:
            # A reaped parent may leave a descendant holding these pipes.
            # The group was created exclusively by this exact launch.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            raise
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def _crash_v7(path,cut):
    import sqlite3
    from research.financial_guard import V7_TABLES, V7_GUARDS
    from services.auth_store import AuthStore
    store=ResearchStore.__new__(ResearchStore);store.path=Path(path);store.auth_store=AuthStore(Path(path))
    connect=sqlite3.connect
    marker={'table':V7_TABLES[0],'guard':V7_GUARDS[-1],'marker':'UPDATE research_schema SET version=7 WHERE id=1'}.get(cut)
    class Crash(sqlite3.Connection):
        def execute(self,sql,*a,**k):
            result=super().execute(sql,*a,**k)
            if marker==sql:os._exit(61)
            return result
        def commit(self):
            if cut=='before_commit':os._exit(61)
            super().commit()
            if cut=='after_commit':os._exit(62)
    sqlite3.connect=lambda *a,**k:connect(*a,factory=Crash,**k)
    store._migrate_v7()


def _observe_child(path,pid,ref,ready,go,result):
    from research import paid_budget as ledger
    from services.auth_store import AuthStore
    store=ResearchStore(AuthStore(Path(path)))
    ready.put(True)
    if not go.wait(10):return
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        observed=ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)
        result.put((observed['id'],observed['booked_upper']))


def _reserve_child(cookie,rid,excerpt,pid,quote,basis,reference,cap,ready,go,results):
    from research.financial_guard import OfflineProjectRegistration
    from research.provider_schemas import Money
    from research.errors import ResearchError
    from research import paid_budget as ledger
    from fastapi.testclient import TestClient
    from web.backend.tests.test_research_persistence import app,post
    from web.backend.tests.test_research_paid_api import preview_data,confirm_data
    from web.backend.tests.test_research_paid_producers import identity
    from research.paid_approval import OfflineFundingResolver
    from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot
    from api import auth
    resolver=OfflineFundingResolver(principal_id=pid,quote=UsageUpperQuote.model_validate(quote),basis=BudgetBasisSnapshot.model_validate(basis),
        approved_upper=Money(currency='CNY',scale=6,amount_units=3))
    source=None
    try:
        application=app();application.state.research_paid_resolver=resolver
        with TestClient(application) as client:
            client.cookies.set('phase_session',cookie)
            draft=post(client,f'/api/research/{rid}/paid-previews',preview_data(client,rid,excerpt),'child-preview')
            assert draft.status_code==200,draft.text
            confirmed=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft.json()['data']),'child-confirm')
            assert confirmed.status_code==200,confirmed.text
            store=ResearchStore(auth._store());actor=identity(client)
            source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,
                authorized_cap=Money(currency='CNY',scale=6,amount_units=cap),authorization_ref=reference)
            ready.put(True)
            if not go.wait(10):return
            try:
                with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
                    ledger.activate_offline_in(conn,store=store,actor=actor,lease=lease,source=source)
                    proof=ledger.reserve_in(conn,store=store,actor=actor,lease=lease,source=source,approval_ref=confirmed.json()['data']['approval_ref'])
                    results.put(('held',proof.reserved.reserved_upper.amount_units))
            except ResearchError as error:results.put((error.code,0))
    finally:
        if source is not None:source.close()
        resolver.close()


def _die_after_committed_consumption(cookie,rid,excerpt,pid,quote,basis,cut):
    from uuid import uuid4
    from research.financial_guard import OfflineProjectRegistration
    from research.provider_schemas import Money
    from research.paid_provider_session import BudgetedOwnedSession
    from fastapi.testclient import TestClient
    from web.backend.tests.test_research_persistence import app,post
    from web.backend.tests.test_research_paid_api import preview_data,confirm_data
    from web.backend.tests.test_research_paid_producers import identity
    from web.backend.tests.test_research_owned_return import tcp_reply,response_body
    from research.paid_approval import OfflineFundingResolver
    from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot
    from research.provider_adapter import OfflineOwnedTransport
    from api import auth
    resolver=OfflineFundingResolver(principal_id=pid,quote=UsageUpperQuote.model_validate(quote),basis=BudgetBasisSnapshot.model_validate(basis),
        approved_upper=Money(currency='CNY',scale=6,amount_units=3))
    application=app();application.state.research_paid_resolver=resolver
    with TestClient(application) as client:
        client.cookies.set('phase_session',cookie)
        preview=post(client,f'/api/research/{rid}/paid-previews',preview_data(client,rid,excerpt),'crash-preview').json()['data']
        confirmed=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(preview),'crash-confirm').json()['data']
        store=ResearchStore(auth._store());actor=identity(client)
        source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,
            authorized_cap=Money(currency='CNY',scale=6,amount_units=10),authorization_ref=str(uuid4()))
        def die(*args,**kwargs):os._exit(73)
        if cut=='before-begin':OfflineOwnedTransport.begin=die
        with tcp_reply(response_body()) as (factory,state):
            session=BudgetedOwnedSession.offline_start(store,actor,source,confirmed['approval_ref'],connection_factory=factory)
            session.receive()
            assert state['requests']==1
            os._exit(74)
