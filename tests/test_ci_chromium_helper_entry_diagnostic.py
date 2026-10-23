"""Offline entry observation controls; all process/host ports are synthetic."""
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import signal
import stat
import subprocess
from types import SimpleNamespace,CodeType

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('entry_candidate',ROOT/'scripts/diagnose_ci_chromium_helper_entry.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
BRANCH='codex/structure-chromium-entry-diagnostic-20261023-attempt1'
SOURCE=(b'Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\n'
        b'Suites: noble noble-updates noble-backports noble-security\nComponents: main restricted universe multiverse\n'
        b'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')

def assert_workflow(doc):
    assert set(doc)=={'name','permissions','jobs','on' if 'on' in doc else True}
    assert doc.get('on',doc.get(True))=={'push':{'branches':[BRANCH]}} and doc['permissions']=={'contents':'read'}
    assert set(doc['jobs'])=={'entry-only'};job=doc['jobs']['entry-only']
    assert set(job)=={'if','runs-on','timeout-minutes','steps'} and job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']==6
    assert ' '.join(job['if'].split())==("github.event_name == 'push' && github.repository == 'dada8899/structural-isomorphism' "
        "&& github.ref == 'refs/heads/"+BRANCH+"' && github.event.created == true && toJSON(github.event.deleted) == 'false' && github.run_attempt == '1'")
    steps=job['steps'];assert len(steps)==5
    assert steps[0]['uses']=='actions/checkout@v4' and set(steps[0])=={'uses','with'}
    config=steps[0]['with'];assert {k:v for k,v in config.items() if k!='sparse-checkout'}=={'persist-credentials':False,'lfs':False,'submodules':False,'fetch-depth':1,'sparse-checkout-cone-mode':False}
    assert config['sparse-checkout'].splitlines()==['scripts/prepare_ci_chromium.py','scripts/diagnose_ci_chromium_helper_entry.py','.github/workflows/chromium-helper-entry-diagnostic.yml']
    assert steps[1]=={'uses':'actions/setup-python@v5','with':{'python-version':'3.11'}}
    old=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    run=next(s['run'] for s in old['jobs']['browser-product-contract']['steps'] if s.get('name')=='Install browser test dependencies')
    assert shlex.split(steps[2]['run'].replace('\\\n',' '))==shlex.split(run[:run.index('python -I -B scripts/prepare_ci_chromium.py')].replace('\\\n',' '))
    assert set(steps[2])=={'name','run'}
    assert steps[3]=={'name':'Observe one unprivileged fixed companion','id':'entry','run':'python -I -B scripts/diagnose_ci_chromium_helper_entry.py'}
    upload=steps[4];assert upload['uses']=='actions/upload-artifact@v4' and upload['if']=="${{ always() && steps.entry.outputs.entry_diagnostic_safe == 'true' }}"
    assert upload['with']['path']=='${{ runner.temp }}/structure-chromium-entry-diagnostic-${{ github.run_id }}-1/helper-entry-diagnostic.json'
    assert upload['with']['if-no-files-found']=='error' and upload['with']['include-hidden-files'] is False

def test_workflow_is_only_new_once_native_entry_observation():
    assert_workflow(yaml.safe_load((ROOT/'.github/workflows/chromium-helper-entry-diagnostic.yml').read_text()))

@pytest.mark.parametrize('fault',['dispatch','ref','retry','host','timeout','credentials','sparse','installer','output'])
def test_workflow_rejects_scope_expansion(fault):
    doc=yaml.safe_load((ROOT/'.github/workflows/chromium-helper-entry-diagnostic.yml').read_text());job=doc['jobs']['entry-only'];steps=job['steps']
    if fault=='dispatch':doc.get('on',doc.get(True))['workflow_dispatch']={}
    elif fault=='ref':doc.get('on',doc.get(True))['push']['branches']=['main']
    elif fault=='retry':job['if']=job['if'].replace("github.run_attempt == '1'",'true')
    elif fault=='host':job['runs-on']='ubuntu-latest'
    elif fault=='timeout':job['timeout-minutes']=7
    elif fault=='credentials':steps[0]['with']['persist-credentials']=True
    elif fault=='sparse':steps[0]['with']['sparse-checkout']+='web/backend\n'
    elif fault=='installer':steps[3]['run']='python -I -B scripts/prepare_ci_chromium.py'
    else:steps[4]['with']['path']='${{ runner.temp }}/**'
    with pytest.raises((AssertionError,KeyError)):assert_workflow(doc)

def test_loaded_functions_keep_original_body_and_exclude_every_privileged_entry():
    frozen=d.load_readonly(d.Trace())
    assert not any(name in frozen for name in ('prepare','root_worker','PinnedArchiveKeyring','SourceLease','subprocess'))
    code=compile(d.HELPER.read_bytes(),str(d.HELPER),'exec');original={c.co_name:c for c in code.co_consts if isinstance(c,CodeType)}
    for name in ('host_guard','mirror_source'):
        actual=frozen[name].__code__
        assert actual.co_code==original[name].co_code and actual.co_consts==original[name].co_consts
    assert d.FUNCTIONS=={'require','sdk_profile','host_guard','mirror_source'}

@pytest.fixture
def child_fixture(tmp_path,monkeypatch):
    root=tmp_path.resolve();source=root/'source';source.write_bytes(SOURCE);release=root/'os-release';release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
    registry=root/'browsers.json';registry.write_text(json.dumps({'browsers':[{'name':name,'revision':'1217','browserVersion':'147.0.7727.15'} for name in ('chromium','chromium-headless-shell')]}))
    env={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64','RUNNER_TEMP':str(root),'PATH':'synthetic','LANG':'C.UTF-8'}
    monkeypatch.setattr(d.os,'environ',env)
    monkeypatch.setattr(d,'SOURCE',source)
    original=d.load_readonly
    def loader(trace):
        value=original(trace)
        value['os']=SimpleNamespace(getuid=os.getuid,geteuid=os.getuid,uname=lambda:SimpleNamespace(machine='x86_64'),environ=env)
        value['sys']=SimpleNamespace(platform='linux',version_info=(3,11,17))
        value['Path']=lambda path:release if str(path)=='/etc/os-release' else Path(path)
        value['importlib']=SimpleNamespace(metadata=SimpleNamespace(version=lambda _:'1.59.0',distribution=lambda _:SimpleNamespace(locate_file=lambda _:registry)))
        return value
    monkeypatch.setattr(d,'load_readonly',loader)
    # Target-only Linux unlink observation. Local APFS keeps stale directory
    # nlink after removal, so this explicit fake is not native Linux evidence.
    native_stat,native_rmdir=d.os.fstat,d.os.rmdir;retired=set()
    def rmdir(path,*a,**kw):
        info=os.stat(path,dir_fd=kw.get('dir_fd'),follow_symlinks=False)
        result=native_rmdir(path,*a,**kw);retired.add((info.st_dev,info.st_ino));return result
    def fstat(fd):
        info=native_stat(fd)
        if stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino) in retired:
            return SimpleNamespace(**{name:getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_size')},st_nlink=0)
        return info
    monkeypatch.setattr(d.os,'rmdir',rmdir);monkeypatch.setattr(d.os,'fstat',fstat)
    return SimpleNamespace(root=root,source=source,release=release,registry=registry,env=env)

def test_child_pass_has_no_parent_authorization_or_installer_permission(child_fixture):
    value=d.child_observation()
    assert d.valid_child(value) and value['status']=='PASS'
    assert value['sudo_invoked'] is value['browser_installer_invoked'] is value['setup_authorized'] is False
    assert not list(child_fixture.root.glob('structure-chromium-entry-child-*'))
    assert not any(key in value for key in ('event_sha','run_id','root_receipt'))

@pytest.mark.parametrize('uri,category',[('http://azure.archive.ubuntu.com/ubuntu/','azure_http'),
 ('https://azure.archive.ubuntu.com/ubuntu','azure_https'),('http://security.ubuntu.com/ubuntu','security_http'),
 ('https://security.ubuntu.com/ubuntu/','security_https'),('https://archive.ubuntu.com/ubuntu','archive_https'),
 ('http://token@azure.archive.ubuntu.com/ubuntu','other'),('https://private.invalid/SECRET','other'),
 ('http://azure.archive.ubuntu.com/ubuntu?private=1','other')])
def test_uri_classes_are_exact_known_literals_not_url_echoes(uri,category):
    assert d.uri_class([uri])==category
    assert d.uri_class([uri,'another'])=='other'

def test_native_profile_candidate_is_rejected_without_echoing_security_host_body(child_fixture):
    f=child_fixture;f.source.write_bytes(SOURCE.replace(b'http://azure.archive.ubuntu.com',b'http://security.ubuntu.com'))
    value=d.child_observation()
    assert d.valid_child(value) and value['first_failed_check_id']=='source_input_profile'
    assert value['failed_site']['function']=='mirror_source'
    assert value['source']['stanzas'][0]['uri_class']=='security_http'
    assert 'security.ubuntu.com' not in json.dumps(value) and str(f.root) not in json.dumps(value)

def test_two_stanza_security_category_does_not_relax_frozen_input_policy(child_fixture):
    base=SOURCE.replace(b'noble noble-updates noble-backports noble-security',b'noble noble-updates noble-backports')
    security=SOURCE.replace(b'noble noble-updates noble-backports noble-security',b'noble-security').replace(b'http://azure.archive.ubuntu.com',b'https://security.ubuntu.com')
    child_fixture.source.write_bytes(base+b'\n'+security)
    value=d.child_observation();assert d.valid_child(value)
    assert value['first_failed_check_id']=='source_input_profile'
    assert [row['uri_class'] for row in value['source']['stanzas']]==['azure_http','security_https']
    assert [row['suites_class'] for row in value['source']['stanzas']]==['base_noble','security_noble']

def test_unknown_fields_and_userinfo_never_enter_the_record(child_fixture):
    f=child_fixture;f.source.write_bytes(SOURCE+b'PRIVATE_UNKNOWN_FIELD: SECRET_VALUE\n')
    value=d.child_observation();assert d.valid_child(value) and value['status']=='FAIL'
    text=json.dumps(value);assert 'PRIVATE_UNKNOWN_FIELD' not in text and 'SECRET_VALUE' not in text
    assert value['source']['stanzas'][0]['unknown_field_count']==1

def test_parent_envelope_is_exact_original_seven_keys_without_auth_data(child_fixture):
    env={**child_fixture.env,'GITHUB_EVENT_NAME':'push','GITHUB_SHA':'a'*40,'GITHUB_TOKEN':'SYNTHETIC_SECRET'}
    result=d.child_environment(env)
    assert set(result)==set(d.ENV_KEYS) and 'GITHUB_SHA' not in result and 'GITHUB_TOKEN' not in result

def test_duplicate_child_claims_are_not_collapsed_into_a_valid_last_value():
    with pytest.raises(d.Closed):d.strict_json(b'{"sudo_invoked":true,"sudo_invoked":false}')

def test_temp_creation_then_validation_failure_is_not_reported_as_cleanup_success(child_fixture,monkeypatch):
    original=d.tempfile.mkdtemp;created=[]
    def wrong_mode(*a,**kw):
        result=original(*a,**kw);Path(result).chmod(0o755);created.append(Path(result));return result
    monkeypatch.setattr(d.tempfile,'mkdtemp',wrong_mode)
    value=d.child_observation()
    assert d.valid_child(value) and value['first_failed_check_id']=='temporary_owner'
    assert value['checks'][-1]=={'check_id':'cleanup','status':'fail'} and created[0].exists()

def test_partial_constructor_birth_is_unknown_and_never_swept_by_prefix(child_fixture,monkeypatch):
    original=d.tempfile.mkdtemp;created=[]
    def partial(*a,**kw):
        result=original(*a,**kw);created.append(Path(result))
        raise MemoryError('synthetic after directory creation')
    monkeypatch.setattr(d.tempfile,'mkdtemp',partial)
    value=d.child_observation()
    assert d.valid_child(value) and value['first_failed_check_id']=='temporary_owner'
    assert value['checks'][-1]['status']=='fail' and created[0].exists()

@pytest.mark.parametrize('after_open',[False,True])
def test_directory_open_failure_cannot_claim_no_resource_or_cleanup(child_fixture,monkeypatch,after_open):
    native_open=d.os.open;unobserved=[]
    def opened(path,flags,*a,**kw):
        if str(path).startswith('structure-chromium-entry-child-') and flags&os.O_DIRECTORY:
            if after_open:unobserved.append(native_open(path,flags,*a,**kw))
            raise MemoryError('synthetic directory handle construction failure')
        return native_open(path,flags,*a,**kw)
    monkeypatch.setattr(d.os,'open',opened)
    try:
        value=d.child_observation()
        assert d.valid_child(value) and value['first_failed_check_id']=='temporary_owner' and value['checks'][-1]['status']=='fail'
        assert len(list(child_fixture.root.glob('structure-chromium-entry-child-*')))==1
    finally:
        # Test-only closure of the FD deliberately hidden from the producer.
        for fd in unobserved:os.close(fd)

def test_close_uncertainty_fails_cleanup_but_all_known_handles_are_attempted(child_fixture,monkeypatch):
    native_open,native_close=d.os.open,d.os.close;directories=[];closed=[];injected=[]
    def opened(path,flags,*a,**kw):
        fd=native_open(path,flags,*a,**kw)
        if flags&os.O_DIRECTORY:directories.append(fd)
        return fd
    def close(fd):
        result=native_close(fd)
        if fd in directories:
            closed.append(fd)
            if fd==directories[-1] and not injected:
                injected.append(True);raise OSError('synthetic acknowledgement after real close')
        return result
    monkeypatch.setattr(d.os,'open',opened);monkeypatch.setattr(d.os,'close',close)
    value=d.child_observation()
    assert d.valid_child(value) and value['first_failed_check_id']=='cleanup' and value['checks'][-1]['status']=='fail'
    assert len(directories)==2 and set(closed)==set(directories)
    for fd in directories:
        with pytest.raises(OSError):os.fstat(fd)

def test_parent_chain_replacement_never_retires_the_substitute(child_fixture,monkeypatch):
    f=child_fixture;native=d.read_regular;retained=f.root.with_name('retained-original-parent');changed=[]
    def exchange(path,cap):
        raw=native(path,cap)
        if path==f.source and not changed:
            f.root.rename(retained);f.root.mkdir(mode=0o700);changed.append(True)
        return raw
    monkeypatch.setattr(d,'read_regular',exchange)
    value=d.child_observation()
    assert d.valid_child(value) and value['checks'][-1]['status']=='fail'
    assert len(list(retained.glob('structure-chromium-entry-child-*')))==1 and not list(f.root.iterdir())

@pytest.mark.parametrize('fault',['none','timeout','constructor','bad_schema','live_group'])
def test_parent_fixed_companion_reports_actual_exit_reaping_or_unknown(child_fixture,monkeypatch,fault):
    body=d.child_observation();calls=[];signals=[]
    class Process:
        pid=345
        stdout=io.BytesIO()
        returncode=None if fault=='timeout' else 0
        def communicate(self,timeout):
            assert 0<=timeout<=12
            if fault=='timeout':raise subprocess.TimeoutExpired('synthetic',timeout)
            return (json.dumps({'raw':'PRIVATE'} if fault=='bad_schema' else body).encode(),None)
        def poll(self):return self.returncode
        def wait(self,timeout):self.returncode=-9 if fault=='timeout' else 0;return self.returncode
    def launch(args,**kw):
        calls.append((args,kw))
        if fault=='constructor':raise MemoryError('synthetic postfork')
        return Process()
    def killpg(pid,number):
        signals.append(number)
        if number==0 and fault!='live_group':raise ProcessLookupError()
    monkeypatch.setattr(d.subprocess,'Popen',launch);monkeypatch.setattr(d.os,'killpg',killpg)
    process,child=d.companion(child_fixture.env);value=d.parent_record('1','a'*40,process,child)
    assert d.valid_parent(value)
    assert calls[0][0]==[d.sys.executable,'-I','-B',str(d.SELF),'--child']
    assert calls[0][1]['stdin']==subprocess.DEVNULL and set(calls[0][1]['env'])==set(d.ENV_KEYS)
    assert value['status']==('PASS' if fault=='none' else 'FAIL') and value['old_native_effects']=='UNKNOWN'
    if fault=='constructor':assert process['actual_exit'] is None and process['reaped'] is None and not signals
    if fault=='timeout':assert signal.SIGKILL in signals and process['reaped'] is True

@pytest.mark.parametrize('fault',['raw','sudo','env','first','bool_exit'])
def test_closed_parent_record_rejects_extra_or_contradictory_claims(child_fixture,fault):
    child=d.child_observation();process={'attempted':True,'actual_exit':0,'reaped':True,'group_absent':True,'deadline_exceeded':False}
    value=d.parent_record('1','a'*40,process,child)
    if fault=='raw':value['raw_exception']='PRIVATE'
    elif fault=='sudo':value['sudo_invoked']=True
    elif fault=='env':value['child']['environment']={'PRIVATE':'SECRET'}
    elif fault=='first':value['first_failed_check_id']='child_process'
    else:value['process']['actual_exit']=False
    assert not d.valid_parent(value)

@pytest.mark.parametrize('mutation',['replacement','same_inode'])
def test_report_is_rechecked_after_actual_output_open_before_safe_flag(child_fixture,monkeypatch,mutation):
    child=d.child_observation();value=d.parent_record('1','a'*40,{'attempted':True,'actual_exit':0,'reaped':True,'group_absent':True,'deadline_exceeded':False},child)
    output=child_fixture.root/'output';output.write_bytes(b'');output.chmod(0o600);monkeypatch.setitem(child_fixture.env,'GITHUB_OUTPUT',str(output))
    native=d.os.open;changed=[]
    def exchange(path,flags,*a,**kw):
        if os.fspath(path)==str(output) and not changed:
            report=child_fixture.root/'helper-entry-diagnostic.json'
            if mutation=='replacement':report.rename(child_fixture.root/'original.json')
            report.write_bytes(b'UNSAFE_SYNTHETIC_REPORT');report.chmod(0o600);changed.append(True)
        return native(path,flags,*a,**kw)
    monkeypatch.setattr(d.os,'open',exchange)
    with pytest.raises(d.Closed):d.publish(child_fixture.root,value)
    assert changed and output.read_bytes()==b''

def test_one_safe_report_is_bounded_and_published_without_extra_permissions(child_fixture,monkeypatch):
    child=d.child_observation();value=d.parent_record('1','a'*40,{'attempted':True,'actual_exit':0,'reaped':True,'group_absent':True,'deadline_exceeded':False},child)
    output=child_fixture.root/'output';output.write_bytes(b'');output.chmod(0o600);monkeypatch.setitem(child_fixture.env,'GITHUB_OUTPUT',str(output))
    receipt=d.publish(child_fixture.root,value)
    raw=(child_fixture.root/'helper-entry-diagnostic.json').read_bytes()
    assert len(raw)<=8192 and json.loads(raw)==value and receipt['fsynced'] is True
    assert output.read_bytes()==b'entry_diagnostic_safe=true\n'
