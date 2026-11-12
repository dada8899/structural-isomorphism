"""Synthetic source failures only; no sudo, APT, network or browser."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
setup=load('source_stage_setup','prepare_ci_chromium.py')
verify=load('source_stage_verifier','verify_ci_chromium_setup.py')
SOURCE=(b'Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu\n'
        b'Suites: noble noble-updates noble-backports noble-security\n'
        b'Components: main restricted universe multiverse\n'
        b'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')
STAGES=('source-path','source-open','source-lock','source-metadata','source-read',
        'source-map','source-named-identity','source-backup-open','source-write','source-fsync')

@pytest.mark.parametrize('stage',STAGES)
@pytest.mark.parametrize('error_type',[setup.Refused,OSError])
def test_real_source_operation_failure_reports_only_fixed_stage(tmp_path,monkeypatch,capsys,stage,error_type):
    source=tmp_path/'ubuntu.sources';source.write_bytes(SOURCE);source.chmod(0o644)
    before=setup.identity(source.stat());backup=tmp_path/'backup'
    operations={'source-path':(Path,'resolve'),'source-open':(setup.os,'open'),
                'source-lock':(setup.fcntl,'flock'),'source-metadata':(setup.os,'fstat'),
                'source-read':(setup,'checked_read'),'source-map':(setup,'mirror_source'),
                'source-named-identity':(Path,'lstat'),'source-backup-open':(setup.os,'open'),
                'source-write':(setup.os,'pwrite'),'source-fsync':(setup.os,'fsync')}
    owner,name=operations[stage];original=getattr(owner,name)
    def fail_at_operation(*args,**kwargs):
        if setup._failure_phase=='root-worker' and setup._failure_stage==stage:
            raise error_type('CANARY_PRIVATE_SOURCE_URI_PATH')
        return original(*args,**kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(owner,name,fail_at_operation)
        with pytest.raises(error_type):setup.SourceLease(source,backup,expected_uid=os.getuid())
    assert (setup._failure_phase,setup._failure_stage)==('root-worker',stage)
    assert source.read_bytes()==SOURCE and setup.identity(source.stat())==before
    assert capsys.readouterr().out==''
    # The existing root wrapper suppresses the exception; main emits the fixed
    # global stage only. No exception class/message/path is serialized.
    def wrapped_failure():
        setup.entering('root-worker',stage)
        raise setup.CleanupUnknown('CANARY_PRIVATE_SOURCE_URI_PATH') from None
    monkeypatch.setattr(setup,'prepare',wrapped_failure)
    monkeypatch.setattr(setup.sys,'argv',['fixed-helper'])
    assert setup.main()==2
    raw=capsys.readouterr().out;value=json.loads(raw)
    assert value=={'protocol':'ci-chromium-failure-v1','status':'UNKNOWN',
                   'failure_phase':'root-worker','failure_stage':stage}
    assert setup.failure_valid(value,2) and verify.failure_stage_safe('root-worker',stage)
    assert 'CANARY' not in raw and str(tmp_path) not in raw


def test_backup_labels_do_not_replace_install_or_restore_phase(tmp_path):
    source=tmp_path/'ubuntu.sources';source.write_bytes(SOURCE);source.chmod(0o644)
    identity=setup.identity(source.stat());backup=tmp_path/'backup'
    lease=setup.SourceLease(source,backup,expected_uid=os.getuid())
    try:
        assert setup._failure_stage=='source-fsync' and backup.read_bytes()==SOURCE
        setup.entering('root-worker','install');lease.apply()
        assert setup._failure_stage=='install' and source.read_bytes()==setup.mirror_source(SOURCE)
        setup.entering('root-worker','install-source-restore');lease.restore()
        assert setup._failure_stage=='install-source-restore'
        assert source.read_bytes()==backup.read_bytes()==SOURCE
        assert setup.identity(source.stat())==identity
    finally:lease.close()


def test_stage_sets_match_and_unknown_values_remain_rejected():
    assert setup.FAILURE_STAGES==verify.FAILURE_STAGES
    for stage in STAGES:
        assert setup.failure_valid(setup.failure_record('root-worker',stage),2)
        assert not verify.failure_stage_safe('parent',stage)
    for stage in ('source-CANARY','source-open:/private','source-open-oserror'):
        assert not verify.failure_stage_safe('root-worker',stage)
        with pytest.raises(setup.Refused):setup.failure_record('root-worker',stage)
