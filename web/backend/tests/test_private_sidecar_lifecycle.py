"""SQLite sidecar disappearance is not a still-named unsafe file."""
from pathlib import Path
import importlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import time

import pytest

from services import runtime_paths as paths
from services.auth_store import AuthStore
from services.sso_store import SsoReplayStore
from services.history_db import HistoryDB
from research.store import ResearchStore


@pytest.fixture(params=['auth', 'sso', 'history'])
def role(request, tmp_path, monkeypatch):
    state=tmp_path.resolve()/'state';state.mkdir(mode=0o700)
    (state/'logs').mkdir(mode=0o700);(tmp_path/'cache').mkdir(mode=0o700)
    monkeypatch.setenv('STRUCTURAL_PRIVACY_HMAC_KEY','0123456789abcdef'*4)
    monkeypatch.setenv('AUTH_DATA_DIR',str(state));monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR',str(state))
    monkeypatch.setenv('STRUCTURAL_ENV','dev')
    kind=request.param
    if kind=='auth':
        db=state/'auth.sqlite3';ResearchStore(AuthStore(db))
    elif kind=='sso':
        db=state/'sso_replay.sqlite3';SsoReplayStore(db)
    else:
        db=state/'history.db';HistoryDB(db)
    db.chmod(0o600)
    monkeypatch.setenv('STRUCTURAL_ENV','prod')
    for namespace in ('services.runtime_paths','web.backend.services.runtime_paths'):
        module=importlib.import_module(namespace)
        for name,value in [('STATE_ROOT',state),('LOG_ROOT',state/'logs'),('CACHE_ROOT',tmp_path/'cache')]:
            monkeypatch.setattr(module,name,value)
    return kind,db


def witness_for(module, kind, db):
    cls={'auth':module.PrivateAuthFile,'sso':module.PrivateSsoFile,'history':module.PrivateHistoryFile}[kind]
    return cls.acquire(db)


@pytest.mark.parametrize('namespace',['services.runtime_paths','web.backend.services.runtime_paths'])
@pytest.mark.parametrize('suffix',['-wal','-shm','-journal'])
def test_existing_unsafe_sidecars_keep_all_private_rules(role, namespace, suffix, monkeypatch):
    kind,db=role;module=importlib.import_module(namespace)
    witness=witness_for(module,kind,db)
    side=db.with_name(db.name+suffix)
    try:
        side.write_bytes(b'synthetic sidecar metadata only');side.chmod(0o644)
        with pytest.raises(module.RuntimePathError):witness._sidecar_entry(side.name)
        side.chmod(0o600)
        target=side.with_name('linked-sidecar');os.link(side,target)
        with pytest.raises(module.RuntimePathError):witness._sidecar_entry(side.name)
        target.unlink();side.unlink()
        target.write_bytes(b'not a database');target.chmod(0o600);side.symlink_to(target)
        with pytest.raises(module.RuntimePathError):witness._sidecar_entry(side.name)
        side.unlink();target.unlink()
    finally:witness.close()


@pytest.mark.parametrize('fault',['zero-still-zero','zero-new-uid','zero-new-mode','zero-new-hardlink','zero-new-symlink','zero-new-directory','wrong-uid','wrong-mode-gone','directory','hardlink'])
def test_synthetic_stat_is_only_a_rejection_negative(role, monkeypatch, fault):
    kind,db=role;witness=witness_for(paths,kind,db);side=db.with_name(db.name+'-shm')
    side.write_bytes(b'synthetic');side.chmod(0o600)
    original=os.stat;actual=original(side,follow_symlinks=False);calls=[]
    values=list(actual)
    if fault=='wrong-uid':values[4]=os.geteuid()+1
    elif fault=='wrong-mode-gone':values[0]=stat.S_IFREG|0o644;values[3]=0
    elif fault=='directory':values[0]=stat.S_IFDIR|0o600
    elif fault=='hardlink':values[3]=2
    else:values[3]=0
    invalid=os.stat_result(values)
    def observed(name,*args,**kwargs):
        if name==side.name and kwargs.get('dir_fd')==witness.parent_fd:
            calls.append(True)
            if len(calls)==1:return invalid
            if fault=='zero-still-zero':return invalid
            different=list(actual);different[1]=actual.st_ino+1
            if fault=='zero-new-uid':different[4]=os.geteuid()+1
            elif fault=='zero-new-mode':different[0]=stat.S_IFREG|0o644
            elif fault=='zero-new-hardlink':different[3]=2
            elif fault=='zero-new-symlink':different[0]=stat.S_IFLNK|0o600
            elif fault=='zero-new-directory':different[0]=stat.S_IFDIR|0o600
            return os.stat_result(different)
        return original(name,*args,**kwargs)
    try:
        monkeypatch.setattr(paths.os,'stat',observed)
        with pytest.raises(paths.RuntimePathError):witness._sidecar_entry(side.name)
        assert len(calls)==(2 if fault.startswith('zero-') else 1)
    finally:witness.close()


def test_main_database_never_uses_zero_link_disappearance_exception(role, monkeypatch):
    kind,db=role;witness=witness_for(paths,kind,db);original=os.stat;value=list(original(db));value[3]=0;calls=[]
    def observed(name,*args,**kwargs):
        if name==db.name and kwargs.get('dir_fd')==witness.parent_fd:
            calls.append(True)
            if len(calls)==1:return os.stat_result(value)
            raise FileNotFoundError('negative only')
        return original(name,*args,**kwargs)
    try:
        monkeypatch.setattr(paths.os,'stat',observed)
        with pytest.raises(paths.RuntimePathError):witness._entry(db.name)
        assert len(calls)==1
        with pytest.raises(paths.RuntimePathError):witness._sidecar_entry(db.name)
        assert len(calls)==1
    finally:witness.close()


@pytest.mark.parametrize('name',['other-wal','auth.sqlite3-wal/..','unknown.sqlite3-shm'])
def test_sidecar_names_are_fixed_and_role_bound(role, name):
    kind,db=role;witness=witness_for(paths,kind,db)
    try:
        with pytest.raises(paths.RuntimePathError):witness._sidecar_entry(name)
        wrong='sso_replay.sqlite3-wal' if kind!='sso' else 'auth.sqlite3-wal'
        with pytest.raises(paths.RuntimePathError):witness._sidecar_entry(wrong)
    finally:witness.close()


_NATIVE_READER=r'''
import sqlite3,sys,json,socket
from pathlib import Path
root=Path(sys.argv[1]);owned=Path(sys.argv[2]);count=0
def audit(event,args):
 if event=='sqlite3.connect':assert str(args[0])==root.as_uri()+'?mode=rw'
 if event=='socket.__new__':assert args[1] not in (socket.AF_INET,socket.AF_INET6)
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('native lifecycle network forbidden')
 if event=='import':assert args[0].split('.')[0] not in ('torch','transformers','sentence_transformers','huggingface_hub')
sys.addaudithook(audit)
conn=sqlite3.connect(root.as_uri()+'?mode=rw',uri=True)
try:
 for _ in range(256):
  conn.execute('SELECT name FROM sqlite_schema').fetchall();count+=1
finally:conn.close()
# One active reader per process then final close: no later sidecar recreation.
print(json.dumps({'native_reads_closed':count}))
'''


@pytest.mark.parametrize('namespace',['services.runtime_paths','web.backend.services.runtime_paths'])
def test_real_native_active_readers_then_final_close_without_recreation(role, namespace):
    kind,db=role;module=importlib.import_module(namespace);witness=witness_for(module,kind,db)
    processes=[]
    try:
        env={'PATH':'/usr/bin:/bin','HOME':str(db.parent.parent),'PYTHONDONTWRITEBYTECODE':'1'}
        for _ in range(2):
            processes.append(subprocess.Popen([sys.executable,'-B','-c',_NATIVE_READER,str(db),str(db.parent.parent)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE))
        checks=0;deadline=time.monotonic()+8
        while any(child.poll() is None for child in processes):
            assert time.monotonic()<deadline
            witness._sidecars();checks+=1
        for child in processes:
            output,error=child.communicate(timeout=5)
            assert child.returncode==0,error
            assert json.loads(output)['native_reads_closed']==256
        assert checks>0
        assert stat.S_IMODE(db.stat().st_mode)==0o600
        print('NATIVE_SIDECAR_LIFECYCLE:'+str({'role':kind,'namespace':namespace,'checks':checks,'closed_native_reads':512}))
    finally:
        witness.close()
        for child in processes:
            if child.poll() is None:child.kill();child.communicate(timeout=5)


def test_revalidated_sidecar_still_participates_in_orphan_checks(role, monkeypatch):
    kind,db=role;witness=witness_for(paths,kind,db);side=db.with_name(db.name+'-wal')
    side.write_bytes(b'synthetic metadata negative');side.chmod(0o600)
    original=os.stat;database=original(db);sideinfo=original(side);seen=[]
    empty=list(database);empty[6]=0
    zero=list(sideinfo);zero[3]=0
    def observed(name,*args,**kwargs):
        if kwargs.get('dir_fd')==witness.parent_fd:
            if name==db.name:return os.stat_result(empty)
            if name==side.name:
                seen.append(True)
                return os.stat_result(zero) if len(seen)==1 else sideinfo
        return original(name,*args,**kwargs)
    try:
        monkeypatch.setattr(paths.os,'stat',observed)
        with pytest.raises(paths.RuntimePathError,match='orphan'):witness.check()
        assert len(seen)==2
    finally:witness.close()


def test_zero_link_recheck_other_error_is_not_an_absence(role, monkeypatch):
    kind,db=role;witness=witness_for(paths,kind,db);side=db.with_name(db.name+'-shm')
    side.write_bytes(b'synthetic negative');side.chmod(0o600)
    original=os.stat;zero=list(original(side));zero[3]=0;seen=[]
    def observed(name,*args,**kwargs):
        if name==side.name and kwargs.get('dir_fd')==witness.parent_fd:
            seen.append(True)
            if len(seen)==1:return os.stat_result(zero)
            raise PermissionError('synthetic metadata access denied')
        return original(name,*args,**kwargs)
    try:
        monkeypatch.setattr(paths.os,'stat',observed)
        with pytest.raises(PermissionError):witness._sidecar_entry(side.name)
        assert len(seen)==2
    finally:witness.close()
