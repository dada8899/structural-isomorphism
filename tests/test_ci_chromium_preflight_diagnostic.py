"""Offline synthetic diagnostics; no real system inputs or installation."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
from types import SimpleNamespace,CodeType

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preflight_diagnostic_candidate',ROOT/'scripts/diagnose_ci_chromium_preflight.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
BRANCH='codex/structure-chromium-preflight-diagnostic-20261023-attempt2'


def assert_workflow(doc):
    assert set(doc)=={'name','permissions','jobs','on' if 'on' in doc else True}
    assert doc.get('on',doc.get(True))=={'push':{'branches':[BRANCH]}}
    assert doc['permissions']=={'contents':'read'} and set(doc['jobs'])=={'diagnostic-only'}
    job=doc['jobs']['diagnostic-only'];assert set(job)=={'if','runs-on','timeout-minutes','steps'}
    assert job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']==6
    assert ' '.join(job['if'].split())==("github.event_name == 'push' && github.repository == 'dada8899/structural-isomorphism' "
        "&& github.ref == 'refs/heads/"+BRANCH+"' && github.event.created == true && toJSON(github.event.deleted) == 'false' && github.run_attempt == '1'")
    steps=job['steps'];assert len(steps)==5
    assert set(steps[0])=={'uses','with'} and steps[0]['uses']=='actions/checkout@v4'
    config=steps[0]['with'];assert {k:v for k,v in config.items() if k!='sparse-checkout'}=={
        'persist-credentials':False,'lfs':False,'submodules':False,'fetch-depth':1,'sparse-checkout-cone-mode':False}
    assert config['sparse-checkout'].splitlines()==['scripts/prepare_ci_chromium.py','scripts/verify_ci_chromium_setup.py',
        'scripts/diagnose_ci_chromium_preflight.py','.github/workflows/chromium-preflight-diagnostic.yml']
    assert steps[1]=={'uses':'actions/setup-python@v5','with':{'python-version':'3.11'}}
    old=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    run=next(s['run'] for s in old['jobs']['browser-product-contract']['steps'] if s.get('name')=='Install browser test dependencies')
    assert shlex.split(steps[2]['run'].replace('\\\n',' '))==shlex.split(run[:run.index('python -I -B scripts/prepare_ci_chromium.py')].replace('\\\n',' '))
    assert set(steps[2])=={'name','run'}
    assert steps[3]=={'name':'Observe frozen readonly preflight predicates only','id':'diagnostic','run':'python -I -B scripts/diagnose_ci_chromium_preflight.py'}
    upload=steps[4];assert set(upload)=={'name','if','uses','with'}
    assert upload['if']=="${{ always() && steps.diagnostic.outputs.diagnostic_safe == 'true' }}" and upload['uses']=='actions/upload-artifact@v4'
    assert set(upload['with'])=={'name','path','if-no-files-found','include-hidden-files'}
    assert upload['with']['path']=='${{ runner.temp }}/structure-chromium-preflight-diagnostic-${{ github.run_id }}-1/preflight-diagnostic.json'
    assert upload['with']['if-no-files-found']=='error' and upload['with']['include-hidden-files'] is False


def test_workflow_has_only_new_native_diagnostic_effects():
    assert_workflow(yaml.safe_load((ROOT/'.github/workflows/chromium-preflight-diagnostic.yml').read_text()))


@pytest.mark.parametrize('fault',['dispatch','ref','retry','runner','budget','credentials','sparse','helper','artifact'])
def test_workflow_rejects_execution_or_export_scope_expansion(fault):
    doc=yaml.safe_load((ROOT/'.github/workflows/chromium-preflight-diagnostic.yml').read_text());job=doc['jobs']['diagnostic-only'];steps=job['steps']
    if fault=='dispatch':doc.get('on',doc.get(True))['workflow_dispatch']={}
    elif fault=='ref':doc.get('on',doc.get(True))['push']['branches']=['main']
    elif fault=='retry':job['if']=job['if'].replace("github.run_attempt == '1'",'true')
    elif fault=='runner':job['runs-on']='ubuntu-latest'
    elif fault=='budget':job['timeout-minutes']=7
    elif fault=='credentials':steps[0]['with']['persist-credentials']=True
    elif fault=='sparse':steps[0]['with']['sparse-checkout']+='web/backend\n'
    elif fault=='helper':steps[3]['run']='python -I -B scripts/prepare_ci_chromium.py'
    else:steps[4]['with']['path']='${{ runner.temp }}/**'
    with pytest.raises((AssertionError,KeyError)):assert_workflow(doc)


def test_checksum_verified_ast_contains_only_unchanged_readonly_definitions():
    trace=d.Trace();frozen=d.load_readonly(trace)
    assert d.FUNCTIONS=={'need','strict_json','metadata','snapshot','helper_metadata','sdk'}
    assert not any(name in frozen for name in ('context','before','install','after','subprocess','signal','root_worker'))
    original=ast.parse(d.SOURCE_FILE.read_bytes())
    compiled=compile(d.SOURCE_FILE.read_bytes(),str(d.SOURCE_FILE),'exec')
    bodies={code.co_name:code for code in compiled.co_consts if isinstance(code,CodeType)}
    for name in d.FUNCTIONS-{'need'}:
        node=next(n for n in original.body if isinstance(n,ast.FunctionDef) and n.name==name)
        assert frozen[name].__code__.co_firstlineno==node.lineno
        assert frozen[name].__code__.co_code==bodies[name].co_code
        assert frozen[name].__code__.co_consts==bodies[name].co_consts
        assert frozen[name].__code__.co_names==bodies[name].co_names
    assert hashlib.sha256(d.SOURCE_FILE.read_bytes()).hexdigest()==d.SOURCE_SHA


@pytest.fixture
def diagnostic(tmp_path,monkeypatch):
    root=(tmp_path/'own').resolve();root.mkdir(mode=0o700)
    trace=d.Trace();trace.mark('context_complete',True)
    frozen=trace.call('source_code',lambda:d.load_readonly(trace))
    helper=root/'prepare_ci_chromium.py';helper.write_bytes((ROOT/'scripts/prepare_ci_chromium.py').read_bytes())
    source=root/'source';source.write_bytes(b'RAW_APT_PRIVATE_BODY_NOT_EXPORTED');source.chmod(0o644)
    key=root/'keyring';key.write_bytes(b'RAW_KEY_PRIVATE_BODY_NOT_EXPORTED');key.chmod(0o644)
    frozen['HELPER']=helper;frozen['SYSTEM_FILES']={'source':(source,16384),'keyring':(key,1024*1024)}
    # Only this test port maps the expected root ownership to the actual test
    # user's synthetic files. It is not a native Linux/root reproduction.
    original=frozen['metadata']
    frozen['metadata']=lambda path,cap,owner:original(path,cap,os.getuid())
    registry=root/'site/playwright/driver/package/browsers.json';registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({'browsers':[{'name':name,'revision':'1217','browserVersion':'147.0.7727.15'} for name in d.BROWSERS]}))
    versions=dict(frozen['PINS'])
    monkeypatch.setattr(d.importlib.metadata,'version',lambda name:versions[name])
    monkeypatch.setattr(d.importlib.metadata,'distribution',lambda name:SimpleNamespace(locate_file=lambda _:registry))
    predicates={k:True for k in ('native_host','github_hosted','platform_vars','event','ref','repository','attempt')}
    def report():
        trace.mark('public_persist',True)
        return d.record(trace,'1','a'*40,predicates,d.integers(root.stat()))
    return SimpleNamespace(root=root,trace=trace,frozen=frozen,helper=helper,source=source,key=key,registry=registry,versions=versions,report=report)


def test_all_predicates_passing_is_only_new_runner_diagnostic_not_setup(diagnostic):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);report=f.report()
    assert d.valid_record(report) and report['status']=='DIAGNOSTIC_PASS'
    assert report['helper_invoked'] is False and report['setup_authorized'] is False and report['new_runner_observation_only'] is True
    assert all(row['status']=='pass' for row in report['checks'])
    assert not list(f.root.glob('*state*')) and not list(f.root.glob('*claim*')) and not (f.root/'write-probe.json').exists()


@pytest.mark.parametrize('fault,expected',[('helper_hash','helper_metadata'),('source_missing','source_metadata'),
    ('source_symlink','source_metadata'),('key_directory','keyring_metadata'),('mode','snapshot_modes'),
    ('lookup','sdk_lookup'),('pin','sdk_pins'),('registry_version','sdk_registry')])
def test_first_failed_check_stops_later_work_without_raw_values(diagnostic,monkeypatch,fault,expected):
    f=diagnostic
    if fault=='helper_hash':f.helper.write_bytes(b'changed source')
    elif fault=='source_missing':f.source.unlink()
    elif fault=='source_symlink':f.source.unlink();f.source.symlink_to(f.key)
    elif fault=='key_directory':f.key.unlink();f.key.mkdir()
    elif fault=='mode':f.source.chmod(0o660)
    elif fault=='lookup':monkeypatch.setattr(d.importlib.metadata,'version',lambda name: (_ for _ in ()).throw(KeyError('RAW_SECRET_EXCEPTION')))
    elif fault=='pin':f.versions['pytest']='7a'*32
    else:f.registry.write_text(json.dumps({'browsers':[{'name':name,'revision':'1217','browserVersion':'RAW_SECRET_REGISTRY'} for name in d.BROWSERS]}))
    d.run_checks(f.frozen,f.trace,f.root);report=f.report()
    assert report['status']=='DIAGNOSTIC_FAIL' and report['first_failed_check_id']==expected and d.valid_record(report)
    encoded=json.dumps(report)
    assert all(secret not in encoded for secret in ('RAW_APT','RAW_KEY','RAW_SECRET','7a'*32,str(f.root)))
    assert not (f.root/'write-probe.json').exists()


def test_symlink_observation_never_reads_the_target(tmp_path,monkeypatch):
    target=tmp_path/'target';target.write_bytes(b'PRIVATE_TARGET');link=tmp_path/'link';link.symlink_to(target)
    monkeypatch.setattr(d,'read_regular',lambda *a:pytest.fail('symlink target must not be read'))
    result=d.observe(link,16384)
    assert result['kind']=='symlink' and result['sha256'] is None and result['stable'] is None


def test_registry_symlink_is_refused_without_following_its_body(diagnostic,monkeypatch):
    f=diagnostic;target=f.registry.with_name('original-registry.json');f.registry.rename(target);f.registry.symlink_to(target)
    original=d.read_regular
    def guarded(path,cap):
        assert path!=f.registry, 'registry symlink body must not be read'
        return original(path,cap)
    monkeypatch.setattr(d,'read_regular',guarded)
    d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    assert value['first_failed_check_id']=='sdk_registry' and value['registry']['sha256'] is None and d.valid_record(value)


def test_changed_frozen_source_is_rejected_before_loading_any_definition(tmp_path,monkeypatch):
    path=tmp_path/'verify_ci_chromium_setup.py';path.write_bytes(b'raise RuntimeError("UNTRUSTED_CODE")\n')
    monkeypatch.setattr(d,'SOURCE_FILE',path)
    with pytest.raises(d.Closed):d.load_readonly(d.Trace())


def test_failed_input_role_cannot_be_relabelled_as_another_check(diagnostic):
    f=diagnostic;f.source.unlink();d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    assert d.valid_record(value) and value['first_failed_check_id']=='source_metadata'
    value['failed_input']['path_id']='keyring'
    assert not d.valid_record(value)


def test_synthetic_context_exposes_only_predicates_and_never_accepts_old_ref(tmp_path,monkeypatch):
    monkeypatch.setattr(d.sys,'platform','linux')
    monkeypatch.setattr(d.os,'uname',lambda:SimpleNamespace(machine='x86_64'))
    env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64',
         'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/codex/structure-chromium-setup-once-20261023-attempt1',
         'GITHUB_REPOSITORY':'dada8899/structural-isomorphism','GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_ID':'1',
         'GITHUB_SHA':'a'*40,'RUNNER_TEMP':str(tmp_path.resolve()),'UNKNOWN_SECRET':'NEVER_ECHO_THIS'}
    root,run,sha,predicates,info=d.context(env)
    assert predicates['ref'] is False and all(type(value) is bool for value in predicates.values())
    assert 'NEVER_ECHO_THIS' not in json.dumps(predicates) and info['mode']==0o700 and info['uid']==os.getuid()
    assert not list(root.iterdir())  # This is a fake-context unit test, no Linux observation.


def test_json_probe_is_exclusive_and_does_not_create_authority_names(tmp_path):
    (tmp_path/'write-probe.json').write_bytes(b'preserve existing')
    with pytest.raises(FileExistsError):d.write_probe(tmp_path)
    assert (tmp_path/'write-probe.json').read_bytes()==b'preserve existing'
    assert not (tmp_path/'state.json').exists() and not (tmp_path/'launch-claim.json').exists()


@pytest.mark.parametrize('fault',['extra','setup','package','raw_version','raw_path','bad_first','coerced_bool','false_context','missing_pin_match'])
def test_single_report_schema_rejects_foreign_or_sensitive_fields(diagnostic,fault):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    if fault=='extra':value['environment']={'SECRET':'do-not-publish'}
    elif fault=='setup':value['setup_authorized']=True
    elif fault=='package':value['packages'][0]['package_id']='arbitrary-package'
    elif fault=='raw_version':value['packages'][0]['version']='7a'*32
    elif fault=='raw_path':value['context']['path']='/private/unknown'
    elif fault=='bad_first':value['first_failed_check_id']='helper_metadata'
    elif fault=='false_context':value['context']['predicates']['ref']=False
    elif fault=='missing_pin_match':value['packages'][0]['pin_match']=None
    else:value['packages'][0]['pin_match']=1
    assert not d.valid_record(value)


def test_publish_only_fixed_schema_and_safe_output_after_native_readback(diagnostic,monkeypatch):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    output=f.root/'output';output.write_bytes(b'');output.chmod(0o600)
    monkeypatch.setenv('GITHUB_OUTPUT',str(output));receipt=d.publish(f.root,value)
    raw=(f.root/'preflight-diagnostic.json').read_bytes()
    assert len(raw)<=8192 and json.loads(raw)==value and output.read_bytes()==b'diagnostic_safe=true\n'
    assert (f.root/'preflight-diagnostic.json').stat().st_mode&0o777==0o600
    assert receipt['fsynced'] is True and receipt['output_ino']==output.stat().st_ino
    assert receipt['bytes']==len(b'diagnostic_safe=true\n') and receipt['report_sha256']==hashlib.sha256(raw).hexdigest()


def test_unsafe_schema_never_creates_an_upload_gate(diagnostic,monkeypatch):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);value=f.report();value['raw_exception']='PRIVATE'
    output=f.root/'output';output.write_bytes(b'');output.chmod(0o600);monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    with pytest.raises(d.Closed):d.publish(f.root,value)
    assert not (f.root/'preflight-diagnostic.json').exists() and output.read_bytes()==b''


def test_replaced_report_after_fsync_cannot_sign_an_upload(diagnostic,monkeypatch):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    output=f.root/'output';output.write_bytes(b'');output.chmod(0o600);monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    original=d.os.fsync;replaced=[]
    def replace(fd):
        result=original(fd);path=f.root/'preflight-diagnostic.json'
        if path.exists() and not replaced:
            info=os.fstat(fd)
            if (info.st_dev,info.st_ino)==(path.stat().st_dev,path.stat().st_ino):
                replaced.append(True);path.rename(f.root/'original-report.json');path.write_bytes(b'RAW_MUST_NOT_UPLOAD');path.chmod(0o600)
        return result
    monkeypatch.setattr(d.os,'fsync',replace)
    with pytest.raises(d.Closed):d.publish(f.root,value)
    assert replaced and output.read_bytes()==b''


def test_changed_but_schema_valid_report_at_output_open_is_not_the_checked_report(diagnostic,monkeypatch):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    output=f.root/'output';output.write_bytes(b'');output.chmod(0o600);monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    original=d.os.open;changed=[]
    def exchange(path,flags,*args,**kw):
        if os.fspath(path)==str(output) and not changed:
            report=f.root/'preflight-diagnostic.json';modified=json.loads(report.read_bytes());modified['event_sha']='b'*40
            assert d.valid_record(modified)
            report.write_text(json.dumps(modified,sort_keys=True));changed.append(True)
        return original(path,flags,*args,**kw)
    monkeypatch.setattr(d.os,'open',exchange)
    with pytest.raises(d.Closed):d.publish(f.root,value)
    assert changed and output.read_bytes()==b''


def test_output_replacement_cannot_be_accepted_as_the_original_channel(diagnostic,monkeypatch):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    output=f.root/'output';output.write_bytes(b'');output.chmod(0o600);monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    original=d.os.open;changed=[]
    def exchange(path,flags,*args,**kw):
        if os.fspath(path)==str(output) and not changed:
            output.rename(f.root/'original-output');output.write_bytes(b'');output.chmod(0o600);changed.append(True)
        return original(path,flags,*args,**kw)
    monkeypatch.setattr(d.os,'open',exchange)
    with pytest.raises(d.Closed):d.publish(f.root,value)
    assert changed and output.read_bytes()==b'' and (f.root/'original-output').read_bytes()==b''


def test_report_fd_is_held_until_output_fsync_and_both_fds_are_closed(diagnostic,monkeypatch):
    f=diagnostic;d.run_checks(f.frozen,f.trace,f.root);value=f.report()
    output=f.root/'output';output.write_bytes(b'prior=unchanged\n');output.chmod(0o600);monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    original_open,original_fsync=d.os.open,d.os.fsync;fds={};synced=[]
    def opened(path,flags,*args,**kw):
        fd=original_open(path,flags,*args,**kw)
        if os.fspath(path)==str(f.root/'preflight-diagnostic.json') and flags&os.O_EXCL:fds['report']=fd
        if os.fspath(path)==str(output):fds['output']=fd;assert os.fstat(fds['report']).st_nlink==1
        return fd
    def fsync(fd):
        result=original_fsync(fd)
        if fd==fds.get('output'):
            assert os.fstat(fds['report']).st_nlink==1
            synced.append((os.fstat(fd).st_dev,os.fstat(fd).st_ino))
        return result
    monkeypatch.setattr(d.os,'open',opened);monkeypatch.setattr(d.os,'fsync',fsync)
    receipt=d.publish(f.root,value)
    assert synced==[(receipt['output_dev'],receipt['output_ino'])] and receipt['offset']==len(b'prior=unchanged\n')
    assert output.read_bytes()==b'prior=unchanged\ndiagnostic_safe=true\n'
    for fd in fds.values():
        with pytest.raises(OSError):os.fstat(fd)
