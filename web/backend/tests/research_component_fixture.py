"""Fresh legacy-auth components, with real HTTP identity and native storage."""
from contextlib import closing, contextmanager
from pathlib import Path
import json
import os
import sqlite3
import sys
import threading

import pytest
from .test_research_persistence import stack as persistence_stack

BETA = 'http://testserver'


@pytest.fixture
def stack(tmp_path, monkeypatch):
    from api import auth, favorites, report, report_account
    from services.report_store import ReportStore
    from research import ResearchStore
    producer = persistence_stack.__wrapped__(tmp_path, monkeypatch)
    try:
        client, path = next(producer)
        monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED', 'true')
        monkeypatch.setenv('STRUCTURAL_D1_PUBLIC_GET_ENABLED', 'false')
        monkeypatch.setattr(report_account, '_store', ReportStore(tmp_path / 'legacy-history.db'))
        monkeypatch.setattr(report, '_store', report_account._store)
        monkeypatch.setattr(favorites, '_legacy_data_file', lambda: tmp_path / 'unused-legacy.jsonl')
        store = ResearchStore(auth._store())
        assert not store._formal_mode() and not store.auth_store._private_auth
        with store.transaction() as conn:
            assert store.auth_store.check_offline_auth_metadata(conn) == 'legacy_auth'
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 14
        yield client, path.parent, None
    finally:
        producer.close()


@contextmanager
def after_native_commit(store, *, caller, query, parameters, expected, action=None, proof_path=None):
    """Observe a real native COMMIT return; never replace a DB primitive.

    Match the actual transaction connection, precise caller code, PID/thread,
    and a separately opened readonly connection's persisted task state. The
    injected exception is a lost ACK only after that proof has been captured.
    """
    from research.store import ResearchStore
    previous = sys.getprofile()
    owner = (os.getpid(), threading.get_ident())
    hits = []

    def observe(frame, event, native):
        if previous is not None:
            previous(frame, event, native)
        if event != 'c_return' or getattr(native, '__name__', None) != 'commit' or hits:
            return
        conn = getattr(native, '__self__', None)
        if (frame.f_code is not ResearchStore.transaction.__wrapped__.__code__
                or frame.f_locals.get('self') is not store or frame.f_locals.get('conn') is not conn
                or not isinstance(conn, sqlite3.Connection) or conn.in_transaction
                or owner != (os.getpid(), threading.get_ident())):
            return
        parent = frame.f_back
        while parent is not None and parent.f_code is not caller:
            parent = parent.f_back
        if parent is None:
            return
        with closing(sqlite3.connect(store.path.as_uri() + '?mode=ro', uri=True, isolation_level=None)) as reader:
            state = reader.execute(query, parameters).fetchone()
        if state is None or tuple(state) != tuple(expected):
            return
        proof = dict(pid=owner[0], thread=owner[1], connection_id=id(conn),
                     connection_type=type(conn).__module__ + '.' + type(conn).__qualname__,
                     native='sqlite3.Connection.commit', transaction_file=frame.f_code.co_filename,
                     transaction_line=frame.f_lineno, caller_file=caller.co_filename,
                     caller=caller.co_name, caller_line=parent.f_lineno,
                     database=str(store.path), task_parameters=list(parameters), persisted=list(state), hits=1)
        hits.append(proof)
        if proof_path is not None:
            Path(proof_path).write_text(json.dumps(proof, sort_keys=True) + '\n')
        if action is not None:
            action()
        else:
            raise sqlite3.OperationalError('synthetic committed ACK lost')

    sys.setprofile(observe)
    try:
        yield hits
    finally:
        sys.setprofile(previous)
    assert len(hits) == 1, 'actual native after-COMMIT boundary was not exercised exactly once'
