"""Setup-once authorization/evidence controls; no real helper or binary runs."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import threading
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('setup_once_candidate', ROOT/'scripts/verify_ci_chromium_setup.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
REAL_SNAPSHOT=v.snapshot
BRANCH = 'codex/structure-chromium-source-fix-20261023'
WORKFLOW = ROOT/'.github/workflows/chromium-setup-once.yml'


def assert_workflow(document):
    assert set(document)=={'name','permissions','jobs','on' if 'on' in document else True}
    assert document.get('on',document.get(True)) == {'push':{'branches':[BRANCH]}}
    assert document['permissions'] == {'contents':'read'} and set(document['jobs']) == {'setup-only'}
    job = document['jobs']['setup-only']
    assert set(job) == {'if','runs-on','timeout-minutes','steps'}
    assert job['runs-on']=='ubuntu-24.04' and job['timeout-minutes']==6
    assert ' '.join(job['if'].split()) == (
        "github.event_name == 'push' && github.repository == 'dada8899/structural-isomorphism' "
        "&& github.ref == 'refs/heads/"+BRANCH+"' && github.event.created == true "
        "&& toJSON(github.event.deleted) == 'false' && github.run_attempt == '1'")
    steps=job['steps'];assert len(steps)==7
    checkout=steps[0];assert checkout['uses']=='actions/checkout@v4'
    assert set(checkout)=={'uses','with'}
    assert {k:value for k,value in checkout['with'].items() if k!='sparse-checkout'} == {
        'persist-credentials':False,'lfs':False,'submodules':False,'fetch-depth':1,'sparse-checkout-cone-mode':False}
    assert checkout['with']['sparse-checkout'].splitlines()==[
        'scripts/prepare_ci_chromium.py','scripts/verify_ci_chromium_setup.py','.github/workflows/chromium-setup-once.yml']
    assert steps[1]=={'uses':'actions/setup-python@v5','with':{'python-version':'3.11'}}
    original=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    old=next(s['run'] for s in original['jobs']['browser-product-contract']['steps'] if s.get('name')=='Install browser test dependencies')
    expected=old[:old.index('python -I -B scripts/prepare_ci_chromium.py')]
    assert set(steps[2])=={'name','run'}
    assert shlex.split(steps[2]['run'].replace('\\\n',' '))==shlex.split(expected.replace('\\\n',' '))
    for step,phase in zip(steps[3:6],('before','install','after')):
        assert set(step)==({'name','run','if','id'} if phase=='after' else {'name','run'})
        assert step['run']=='python -I -B scripts/verify_ci_chromium_setup.py '+phase
    assert steps[5]['if']=='always()'
    assert steps[5]['id']=='postflight'
    upload=steps[6];assert upload['uses']=='actions/upload-artifact@v4'
    assert upload['if']=="${{ always() && steps.postflight.outputs.public_records_safe == 'true' }}"
    assert set(upload)=={'name','if','uses','with'}
    assert set(upload['with'])=={'name','path','if-no-files-found','include-hidden-files'}
    assert upload['with']['if-no-files-found']=='error' and upload['with']['include-hidden-files'] is False
    prefix='${{ runner.temp }}/structure-chromium-setup-once-${{ github.run_id }}-${{ github.run_attempt }}/public/'
    assert upload['with']['path'].splitlines()==[prefix+name for name in ('setup-before.json','helper-outcome.json','setup-after.json')]


def test_workflow_is_one_native_setup_effect_with_exact_sparse_inputs_and_public_outputs():
    assert_workflow(yaml.safe_load(WORKFLOW.read_text()))


@pytest.mark.parametrize('mutation',['dispatch','branch','retry','runner','limit','credentials','lfs','wide_sparse',
                                   'backend','retry_helper','skip_post','wide_artifact','ungated_artifact'])
def test_workflow_rejects_scope_expansion_or_missing_failure_evidence(mutation):
    doc=yaml.safe_load(WORKFLOW.read_text());job=doc['jobs']['setup-only'];steps=job['steps']
    if mutation=='dispatch':doc.get('on',doc.get(True))['workflow_dispatch']={}
    elif mutation=='branch':doc.get('on',doc.get(True))['push']['branches']=['main']
    elif mutation=='retry':job['if']=job['if'].replace("github.run_attempt == '1'","true")
    elif mutation=='runner':job['runs-on']='ubuntu-latest'
    elif mutation=='limit':job['timeout-minutes']=7
    elif mutation=='credentials':steps[0]['with']['persist-credentials']=True
    elif mutation=='lfs':steps[0]['with']['lfs']=True
    elif mutation=='wide_sparse':steps[0]['with']['sparse-checkout']+='web/backend\n'
    elif mutation=='backend':steps[2]['run']+='python -m pip install -r web/backend/requirements.txt\n'
    elif mutation=='retry_helper':steps[4]['run']+=' || python -I -B scripts/verify_ci_chromium_setup.py install'
    elif mutation=='skip_post':steps[5].pop('if')
    elif mutation=='ungated_artifact':steps[6]['if']='always()'
    else:steps[6]['with']['path']='${{ runner.temp }}/**'
    with pytest.raises((AssertionError,KeyError)):assert_workflow(doc)


@pytest.fixture
def setup_fixture(tmp_path,monkeypatch):
    root=tmp_path/'owned';root.mkdir(mode=0o700);(root/'public').mkdir(mode=0o700)
    helper=tmp_path/'fixed-helper.py';helper.write_bytes(b'synthetic fixed helper, never executed\n')
    source=tmp_path/'source';source.write_bytes(b'RAW_APT_CONTENT_DO_NOT_UPLOAD\n');source.chmod(0o644)
    key=tmp_path/'key';key.write_bytes(b'SYNTHETIC_PUBLIC_KEYRING'.ljust(3607,b'x'));key.chmod(0o777)
    monkeypatch.setattr(v,'KEYRING_SHA',hashlib.sha256(key.read_bytes()).hexdigest())
    monkeypatch.setattr(v,'HELPER',helper)
    monkeypatch.setattr(v,'HELPER_SHA',hashlib.sha256(helper.read_bytes()).hexdigest())
    def snapshot():
        values={name:v.metadata(path,16384,os.getuid()) for name,path in [('source',source),('keyring',key)]}
        # Explicit fake root ownership for the typed receipt, no native root.
        values['keyring'].update(uid=0,gid=0)
        return values
    monkeypatch.setattr(v,'snapshot',snapshot)
    monkeypatch.setattr(v,'source_predicate',lambda expected:None)
    monkeypatch.setattr(v,'sdk',lambda:{'python':'3.11.0','versions':dict(v.PINS),'browsers':{'chromium':{'revision':'1217','version':v.VERSION},'chromium-headless-shell':{'revision':'1217','version':v.VERSION}}})
    calls=[]
    def receipt():
        original=snapshot()['keyring']
        return {'profile':v.KEYRING_PROFILE,'reference':'1'*32,'input_trust':'untrusted','original':original,
                'effective':{**original,'ino':original['ino']+1,'mode':0o644},
                'directory':{'dev':original['dev'],'ino':original['ino']+2,'uid':0,'gid':0,'mode':0o755,'nlink':2},
                'original_unchanged':True,'signed_by_bound':True,'retired':True}
    def fake_run(args,**kw):
        calls.append((args,kw))
        return SimpleNamespace(returncode=0,stdout=json.dumps({'status':'ready','children_closed':True,'source_restored':True,'keyring':receipt()}).encode())
    monkeypatch.setattr(v.subprocess,'run',fake_run)
    for name,value in {'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64','RUNNER_TEMP':str(tmp_path)}.items():monkeypatch.setenv(name,value)
    monkeypatch.setenv('SYNTHETIC_PRIVATE_TOKEN','DO_NOT_FORWARD_OR_UPLOAD')
    probes=[]
    def fake_payloads(result):
        probes.append(True)
        binary={**v.metadata(helper,16384,os.getuid()),'mode':0o755}
        marker={**binary,'mode':0o644,'size':0,'sha256':hashlib.sha256(b'').hexdigest()}
        probe={'status':'ready','pid':321,'exit_code':0,'version':v.VERSION,'direct_process_reaped':True,'group_absent':True}
        result.update({name:{'binary':dict(binary),'installation_marker':dict(marker),'probe':dict(probe)}
                       for name in ('chromium','chromium-headless-shell')})
        return result
    monkeypatch.setattr(v,'payloads',fake_payloads)
    header={'schema':v.SCHEMA,'classification':'SETUP_ONLY_NOT_A_GRADE','run_id':'1','event_sha':'a'*40}
    return SimpleNamespace(root=root,header=header,helper=helper,source=source,key=key,calls=calls,probes=probes,receipt=receipt)


def test_real_synthetic_inode_hash_snapshots_and_fake_helper_admit_only_one_install(setup_fixture):
    f=setup_fixture
    assert v.before(f.root,f.header)==0
    os.utime(f.source,None)  # Timestamp changes alone are not a restoration failure.
    assert v.install(f.root,f.header)==0 and v.after(f.root,f.header)==0
    assert len(f.calls)==1 and f.calls[0][0]==[v.sys.executable,'-I','-B',str(f.helper)]
    env=f.calls[0][1]['env'];assert set(env)=={'GITHUB_ACTIONS','RUNNER_ENVIRONMENT','RUNNER_OS','RUNNER_ARCH','RUNNER_TEMP','PATH','LANG'}
    assert f.calls[0][1]['timeout']==100 and 'HOME' not in env
    assert v.install(f.root,f.header)!=0 and len(f.calls)==1
    records=[json.loads(p.read_text()) for p in (f.root/'public').iterdir()]
    encoded=json.dumps(records)
    assert all(secret not in encoded for secret in ('RAW_APT_CONTENT','RAW_KEY_CONTENT','DO_NOT_FORWARD_OR_UPLOAD',str(f.root.parent)))
    assert {p.name for p in (f.root/'public').iterdir()}=={'setup-before.json','helper-outcome.json','setup-after.json'}


def test_pinned_schema_records_777_as_untrusted_input_and_requires_retired_effective_receipt(setup_fixture):
    f=setup_fixture;assert f.key.stat().st_mode&0o777==0o777
    assert v.before(f.root,f.header)==0
    before=v.read_json(f.root/'public/setup-before.json')
    assert before['schema']=='chromium-pinned-keyring-setup-v1'
    assert before['keyring_material']==v.keyring_material() and before['keyring_material']['effective_created'] is False
    assert v.install(f.root,f.header)==0 and v.after(f.root,f.header)==0
    receipt=v.read_json(f.root/'public/helper-outcome.json')['keyring_receipt']
    assert receipt['original']['mode']==0o777 and receipt['input_trust']=='untrusted'
    assert receipt['effective']['mode']==0o644 and receipt['effective']['uid']==receipt['effective']['gid']==0
    assert receipt['retired'] is True and receipt['signed_by_bound'] is True


@pytest.mark.parametrize('wrong',[False,True])
def test_original_snapshot_allows_only_independent_content_pin_not_storage_permission(setup_fixture,monkeypatch,wrong):
    f=setup_fixture;native=v.metadata
    def root_metadata(path,cap,owner):
        return {**native(path,cap,os.getuid()),'uid':0,'gid':0}
    monkeypatch.setattr(v,'SYSTEM_FILES',{'source':(f.source,16384),'keyring':(f.key,1024*1024)})
    monkeypatch.setattr(v,'metadata',root_metadata)
    if wrong:f.key.write_bytes(b'wrong'.ljust(3607,b'x'))
    if wrong:
        with pytest.raises(v.Unavailable):REAL_SNAPSHOT()
    else:
        observed=REAL_SNAPSHOT()
        assert observed['keyring']['mode']==0o777 and observed['keyring']['sha256']==v.KEYRING_SHA


@pytest.mark.parametrize('fault',['missing','bad_pin','bad_mode','not_root','not_bound','not_retired','changed_original','unknown'])
def test_missing_or_invalid_effective_trust_receipt_never_becomes_ready(setup_fixture,monkeypatch,fault):
    f=setup_fixture;v.before(f.root,f.header);receipt=f.receipt()
    if fault=='bad_pin':receipt['effective']['sha256']='0'*64
    elif fault=='bad_mode':receipt['effective']['mode']=0o777
    elif fault=='not_root':receipt['effective']['uid']=1001
    elif fault=='not_bound':receipt['signed_by_bound']=False
    elif fault=='not_retired':receipt['retired']=False
    elif fault=='changed_original':receipt['original']['ino']+=100
    elif fault=='unknown':receipt['path']='/unapproved/private'
    response={'status':'ready','children_closed':True,'source_restored':True}
    if fault!='missing':response['keyring']=receipt
    monkeypatch.setattr(v.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(response).encode()))
    assert v.install(f.root,f.header)!=0 and v.after(f.root,f.header)!=0 and not f.probes
    record=v.read_json(f.root/'public/helper-outcome.json')
    assert record['status']=='UNKNOWN' and record['keyring_receipt'] is None


@pytest.mark.parametrize('mutation',['replacement','same_inode_rewrite'])
def test_setup_public_reports_remain_bound_at_real_output_open(setup_fixture,monkeypatch,mutation):
    f=setup_fixture;v.before(f.root,f.header);v.install(f.root,f.header);assert v.after(f.root,f.header)==0
    output=f.root/'output';output.write_bytes(b'');output.chmod(0o600);monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    target=f.root/'public/helper-outcome.json';original=v.os.open;changed=[]
    def exchange(path,flags,*args,**kw):
        if os.fspath(path)==str(output) and not changed:
            if mutation=='replacement':target.rename(f.root/'checked-original.json')
            target.write_bytes(b'UNSAFE_SYNTHETIC_REPORT');target.chmod(0o600);changed.append(True)
        return original(path,flags,*args,**kw)
    monkeypatch.setattr(v.os,'open',exchange)
    try:v.publish_safe_output(f.root,f.header)
    except (v.Unavailable,OSError):pass
    assert changed and output.read_bytes()==b''


def test_setup_report_fds_survive_output_open_and_fsync_with_a_native_receipt(setup_fixture,monkeypatch):
    f=setup_fixture;v.before(f.root,f.header);v.install(f.root,f.header);assert v.after(f.root,f.header)==0
    output=f.root/'output';output.write_bytes(b'prior=safe\n');output.chmod(0o600);monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    native_open,native_fsync=v.os.open,v.os.fsync;reports=[];outputs=[];synced=[]
    def opened(path,flags,*a,**kw):
        fd=native_open(path,flags,*a,**kw)
        if str(path) in {str(f.root/'public'/name) for name in v.PUBLIC_FILES} and flags&os.O_NONBLOCK:reports.append(fd)
        if str(path)==str(output):
            assert len(reports)==3
            for report in reports:assert os.fstat(report).st_nlink==1
            outputs.append(fd)
        return fd
    def fsync(fd):
        result=native_fsync(fd)
        if outputs and fd==outputs[0]:
            for report in reports:assert os.fstat(report).st_nlink==1
            synced.append((os.fstat(fd).st_dev,os.fstat(fd).st_ino))
        return result
    monkeypatch.setattr(v.os,'open',opened);monkeypatch.setattr(v.os,'fsync',fsync)
    receipt=v.publish_safe_output(f.root,f.header)
    assert receipt['fsynced'] is True and synced==[(receipt['output_dev'],receipt['output_ino'])]
    assert {row['file_id'] for row in receipt['reports']}==set(v.PUBLIC_FILES)
    assert output.read_bytes()==b'prior=safe\npublic_records_safe=true\n'
    for fd in reports+outputs:
        with pytest.raises(OSError):os.fstat(fd)


@pytest.mark.parametrize('fault',['source_bytes','source_inode','source_mode','key_bytes','helper_bytes','missing_outcome',
                                'integer_closed','boolean_exit','boolean_attempt','extra_field','before_conflict'])
def test_missing_changed_or_type_confused_evidence_cannot_become_ready(setup_fixture,fault):
    f=setup_fixture;v.before(f.root,f.header);v.install(f.root,f.header)
    path=f.root/'public/helper-outcome.json';value=json.loads(path.read_text())
    if fault=='source_bytes':f.source.write_bytes(b'changed source')
    elif fault=='source_inode':
        raw=f.source.read_bytes();f.source.rename(f.source.with_name('source-old'));f.source.write_bytes(raw)
    elif fault=='source_mode':f.source.chmod(0o600)
    elif fault=='key_bytes':f.key.write_bytes(b'changed signing key')
    elif fault=='helper_bytes':f.helper.write_bytes(b'unreviewed helper')
    elif fault=='missing_outcome':path.unlink()
    elif fault=='before_conflict':
        before=v.read_json(f.root/'public/setup-before.json');before['status']='UNKNOWN';v.write_json(f.root/'public/setup-before.json',before)
    else:
        if fault=='integer_closed':value['children_closed']=1
        elif fault=='boolean_exit':value['exit_code']=False
        elif fault=='boolean_attempt':value['attempts']=True
        else:value['extra']='unverified'
        v.write_json(path,value)
    assert v.after(f.root,f.header)!=0
    assert v.read_json(f.root/'public/setup-after.json')['status']=='UNKNOWN'
    assert not f.probes


def test_post_snapshot_is_rechecked_after_payload_probe(setup_fixture,monkeypatch):
    f=setup_fixture;v.before(f.root,f.header);v.install(f.root,f.header)
    def late_change(result):f.key.write_bytes(b'late change');return result
    monkeypatch.setattr(v,'payloads',late_change)
    assert v.after(f.root,f.header)!=0
    assert v.read_json(f.root/'public/setup-after.json')['system_matches_before'] is False


@pytest.mark.parametrize('code,output',[(7,b'not json'),(7,b'{"status":"ready","children_closed":true,"source_restored":true}'),
                                     (0,b'{"status":"ready","children_closed":1,"source_restored":true}'),
                                     (0,b'{"status":"UNKNOWN","status":"ready","children_closed":true,"source_restored":true}')])
def test_helper_failure_or_contradiction_preserves_failure_and_unknown(setup_fixture,monkeypatch,code,output):
    f=setup_fixture;v.before(f.root,f.header)
    monkeypatch.setattr(v.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=code,stdout=output))
    assert v.install(f.root,f.header)==(code if code else 2)
    assert v.after(f.root,f.header)!=0 and not f.probes
    outcome=v.read_json(f.root/'public/helper-outcome.json')
    assert outcome['status']=='UNKNOWN' and outcome['exit_code']==code and outcome['children_closed'] is None


@pytest.mark.parametrize('mutation',['none','extra','phase','stage','status','duplicate','code','bool_code'])
def test_only_closed_helper_failure_stage_reaches_its_own_public_phase(setup_fixture,monkeypatch,mutation):
    f=setup_fixture;v.before(f.root,f.header)
    reply={'protocol':'ci-chromium-failure-v1','status':'UNKNOWN','failure_phase':'root-worker','failure_stage':'source'}
    code=2
    if mutation=='extra':reply['extra']='CANARY_SECRET'
    elif mutation in ('phase','stage','status'):reply['failure_'+mutation if mutation!='status' else 'status']='CANARY_SECRET'
    elif mutation=='code':code=1
    elif mutation=='bool_code':code=True
    raw=json.dumps(reply).encode()
    if mutation=='duplicate':raw=raw[:-1]+b',"failure_stage":"source"}'
    monkeypatch.setattr(v.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=code,stdout=raw))
    assert v.install(f.root,f.header)!=0
    value=v.read_json(f.root/'public/helper-outcome.json')
    assert value['status']=='UNKNOWN' and value['children_closed'] is None and value['source_restored'] is None
    assert value['failure_stage']==('source' if mutation=='none' else None)
    assert value['failure_phase']==('root-worker' if mutation=='none' else None)
    assert v.public_safe(value) and 'CANARY_SECRET' not in json.dumps(value)
    assert v.after(f.root,f.header)!=0 and not f.probes


@pytest.mark.parametrize('fault',['stage','phase','ready'])
def test_invalid_failure_field_discards_whole_helper_dto_before_safe_upload(setup_fixture,monkeypatch,fault):
    f=setup_fixture;v.before(f.root,f.header);v.install(f.root,f.header);assert v.after(f.root,f.header)==0
    value=v.outcome(f.header,2,False,1,failure={'failure_phase':'root-worker','failure_stage':'source'})
    if fault=='ready':value={**v.read_json(f.root/'public/helper-outcome.json'),'failure_phase':'root-worker','failure_stage':'source'}
    else:value['failure_'+fault]='CANARY_SECRET'
    v.write_json(f.root/'public/helper-outcome.json',value)
    assert not v.public_safe(value) and v.project_public(f.root,f.header)
    projected=v.read_json(f.root/'public/helper-outcome.json')
    assert projected==v.unknown_record(f.header,'helper') and projected['failure_stage'] is None
    output=f.root/'safe-output';output.write_bytes(b'');output.chmod(0o600)
    monkeypatch.setenv('GITHUB_OUTPUT',str(output));v.publish_safe_output(f.root,f.header)
    assert output.read_bytes()==b'public_records_safe=true\n' and 'CANARY_SECRET' not in json.dumps(projected)


def test_before_checks_complete_source_predicate_before_any_attempt(setup_fixture,monkeypatch):
    f=setup_fixture;calls=[]
    def refuse(expected):calls.append(expected);raise v.Unavailable('fixed refusal')
    monkeypatch.setattr(v,'source_predicate',refuse)
    with pytest.raises(v.Unavailable):v.before(f.root,f.header)
    assert calls==[v.snapshot()['source']] and not f.calls and not (f.root/'state.json').exists()


@pytest.mark.parametrize('fault',['none','raw_hash','invalid_profile','late_metadata','helper_hash'])
def test_held_source_preflight_executes_only_hash_locked_pure_parser(monkeypatch,fault):
    raw=(b'Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu\n'
         b'Suites: noble noble-updates noble-backports noble-security\n'
         b'Components: main restricted universe multiverse\n'
         b'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')
    if fault=='invalid_profile':raw=raw.replace(b'Types: deb',b'Types: deb-src')
    source=Path('/synthetic/source-not-opened');closed=[]
    row=SimpleNamespace(st_dev=1,st_ino=2,st_uid=0,st_gid=0,st_mode=0o100644,st_nlink=1,
                        st_size=len(raw),st_mtime_ns=1,st_ctime_ns=1)
    expected={k:getattr(row,'st_'+k) for k in ('dev','ino','uid','gid','nlink','size')}
    expected.update(mode=0o644,sha256=hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(v,'SYSTEM_FILES',{'source':(source,16384)})
    native_open,native_pread,native_fstat,native_close=v.os.open,v.os.pread,v.os.fstat,v.os.close
    monkeypatch.setattr(v.os,'open',lambda path,*a:123 if path==source else native_open(path,*a))
    monkeypatch.setattr(v.os,'pread',lambda fd,*a:raw+(b'x' if fault=='raw_hash' else b'') if fd==123 else
                        (b'raise RuntimeError("CANARY_MUST_NEVER_EXECUTE")' if fault=='helper_hash' else native_pread(fd,*a)))
    monkeypatch.setattr(v.os,'fstat',lambda fd:row if fd==123 else native_fstat(fd))
    monkeypatch.setattr(v.os,'close',lambda fd:closed.append(fd) if fd==123 else native_close(fd))
    native_lstat=Path.lstat
    monkeypatch.setattr(Path,'lstat',lambda path,*a,**kw:(SimpleNamespace(**{**vars(row),'st_ctime_ns':2}) if fault=='late_metadata' else row) if path==source else native_lstat(path,*a,**kw))
    monkeypatch.setattr(v,'helper_metadata',lambda:{'sha256':v.HELPER_SHA})
    if fault=='none':v.source_predicate(expected)
    else:
        with pytest.raises(RuntimeError if fault=='invalid_profile' else v.Unavailable):v.source_predicate(expected)
    assert closed==[123]


def test_unobservable_helper_launch_records_an_attempt_without_claiming_retirement(setup_fixture,monkeypatch):
    f=setup_fixture;v.before(f.root,f.header)
    monkeypatch.setattr(v.subprocess,'run',lambda *a,**kw: (_ for _ in ()).throw(MemoryError('synthetic postfork failure')))
    assert v.install(f.root,f.header)!=0
    assert v.read_json(f.root/'state.json')['attempts']==1
    record=v.read_json(f.root/'public/helper-outcome.json')
    assert record['status']=='UNKNOWN' and record['attempts']==1 and record['exit_code'] is None
    assert record['children_closed'] is None and record['source_restored'] is None
    assert v.after(f.root,f.header)!=0 and not f.probes


def test_replaced_invocation_counter_cannot_launch_or_attest_an_install(setup_fixture,monkeypatch):
    f=setup_fixture;v.before(f.root,f.header)
    original=v.snapshot
    def replace_counter():
        path=f.root/'state.json';raw=path.read_bytes()
        path.rename(f.root/'old-state.json');path.write_bytes(raw);path.chmod(0o600)
        return original()
    monkeypatch.setattr(v,'snapshot',replace_counter)
    assert v.install(f.root,f.header)!=0 and not f.calls
    assert v.read_json(f.root/'public/helper-outcome.json')['status']=='UNKNOWN'


@pytest.mark.parametrize('fault',['state_missing','state_reset','claim_missing','claim_replaced','claim_and_state_lost'])
def test_named_authority_loss_or_replacement_never_rearms_the_helper(setup_fixture,fault):
    f=setup_fixture;v.before(f.root,f.header)
    initial=(f.root/'state.json').read_bytes()
    assert v.install(f.root,f.header)==0 and len(f.calls)==1
    state=f.root/'state.json';claim=f.root/'launch-claim.json'
    if fault=='state_missing':state.unlink()
    if fault in ('state_reset','claim_and_state_lost'):
        state.rename(f.root/'used-state.json');state.write_bytes(initial);state.chmod(0o600)
    if fault in ('claim_missing','claim_and_state_lost'):claim.unlink()
    elif fault=='claim_replaced':
        raw=claim.read_bytes();claim.rename(f.root/'used-claim.json');claim.write_bytes(raw);claim.chmod(0o600)
    try:code=v.install(f.root,f.header)
    except (OSError,v.Unavailable):code=2
    assert code!=0 and len(f.calls)==1
    assert v.after(f.root,f.header)!=0 and not f.probes


@pytest.mark.parametrize('replace',[False,True])
def test_claim_loss_after_attempt_fsync_blocks_launch_and_every_reentry(setup_fixture,monkeypatch,replace):
    f=setup_fixture;v.before(f.root,f.header)
    state=f.root/'state.json';identity=(state.stat().st_dev,state.stat().st_ino)
    original=v.os.fsync;changed=[]
    def change_after_fsync(fd):
        result=original(fd);info=v.os.fstat(fd)
        if not changed and (info.st_dev,info.st_ino)==identity:
            changed.append(True);claim=f.root/'launch-claim.json';raw=claim.read_bytes()
            claim.rename(f.root/'used-claim.json')
            if replace:claim.write_bytes(raw);claim.chmod(0o600)
        return result
    monkeypatch.setattr(v.os,'fsync',change_after_fsync)
    assert v.install(f.root,f.header)!=0
    monkeypatch.setattr(v.os,'fsync',original)
    assert v.install(f.root,f.header)!=0 and not f.calls
    assert v.read_json(state)['attempts']==1


def test_concurrent_install_calls_share_one_exclusive_launch_claim(setup_fixture,monkeypatch):
    f=setup_fixture;v.before(f.root,f.header)
    entered,release=threading.Event(),threading.Event();results=[]
    original=v.subprocess.run
    def wait_helper(*args,**kw):
        entered.set()
        assert release.wait(2)
        return original(*args,**kw)
    monkeypatch.setattr(v.subprocess,'run',wait_helper)
    worker=threading.Thread(target=lambda:results.append(v.install(f.root,f.header)))
    worker.start()
    try:
        assert entered.wait(2)
        denied=v.install(f.root,f.header)
    finally:
        release.set();worker.join(2)
    assert not worker.is_alive() and denied!=0 and results==[0] and len(f.calls)==1


@pytest.mark.parametrize('phase',['before','helper','after'])
@pytest.mark.parametrize('fault',['cross_phase','wrong_pin_or_type','unknown_field','boolean_coercion'])
def test_each_public_phase_discards_its_whole_invalid_record(setup_fixture,monkeypatch,phase,fault):
    f=setup_fixture;v.before(f.root,f.header);v.install(f.root,f.header);assert v.after(f.root,f.header)==0
    name={'before':'setup-before.json','helper':'helper-outcome.json','after':'setup-after.json'}[phase]
    path=f.root/'public'/name;value=v.read_json(path);canary='7a'*32
    if fault=='cross_phase':
        if phase=='before':value['exit_code']=0
        elif phase=='helper':value['sdk']={'versions':{'pytest':canary}}
        else:value['helper']=v.helper_metadata()
    elif fault=='wrong_pin_or_type':
        if phase=='helper':value['exit_code']=canary
        else:value['sdk']['versions']['pytest']=canary
    elif fault=='unknown_field':value['unregistered']=canary
    elif phase=='before':value['helper']['nlink']=True
    elif phase=='helper':value['attempts']=True
    else:value['payloads']['chromium']['probe']['exit_code']=False
    v.write_json(path,value)
    assert not v.public_safe(value) and v.project_public(f.root,f.header)
    assert v.read_json(path)==v.unknown_record(f.header,phase)
    assert v.read_json(f.root/'public/setup-after.json')==v.unknown_record(f.header,'after')
    encoded=json.dumps([v.read_json(f.root/'public'/file) for file in v.PUBLIC_FILES])
    assert canary not in encoded
    output=f.root/'safe-output';output.write_bytes(b'');output.chmod(0o600)
    monkeypatch.setenv('GITHUB_OUTPUT',str(output));v.publish_safe_output(f.root,f.header)
    assert output.read_bytes()==b'public_records_safe=true\n'


def test_absent_before_step_writes_unknown_placeholders_without_inventing_an_attempt(setup_fixture):
    f=setup_fixture
    assert v.after(f.root,f.header)!=0 and not f.calls and not f.probes
    assert v.read_json(f.root/'public/helper-outcome.json')['attempts'] is None
    assert v.read_json(f.root/'public/setup-before.json')['status']=='UNKNOWN'


def test_invalid_public_contents_are_projected_to_unknown_before_upload_authorization(setup_fixture,monkeypatch):
    f=setup_fixture;v.before(f.root,f.header);v.install(f.root,f.header)
    (f.root/'public/helper-outcome.json').write_bytes(b'RAW_CONFIG_OR_ENV_MUST_NOT_UPLOAD')
    assert v.after(f.root,f.header)!=0
    records=[v.read_json(f.root/'public'/name) for name in v.PUBLIC_FILES]
    assert all(v.public_safe(record) for record in records)
    assert 'RAW_CONFIG_OR_ENV' not in json.dumps(records)
    assert records[1]['status']==records[2]['status']=='UNKNOWN'
    output=f.root/'github-output';output.write_bytes(b'previous=safe\n');output.chmod(0o600)
    monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    v.publish_safe_output(f.root,f.header)
    assert output.read_bytes()==b'previous=safe\npublic_records_safe=true\n'


def test_json_writer_refuses_hardlinked_targets_before_truncation(tmp_path):
    original=tmp_path/'owned';original.write_bytes(b'preserve original');original.chmod(0o600)
    alias=tmp_path/'alias';os.link(original,alias)
    with pytest.raises(v.Unavailable):v.write_json(alias,{'value':'replacement'})
    assert original.read_bytes()==b'preserve original'


@pytest.mark.parametrize('fault',['pin','revision','missing_headless','override'])
def test_sdk_metadata_requires_every_original_pin_and_exact_two_browser_profiles(tmp_path,monkeypatch,fault):
    path=tmp_path/'registry.json'
    rows=[{'name':name,'revision':'1217','browserVersion':v.VERSION} for name in ('chromium','chromium-headless-shell')]
    if fault=='revision':rows[0]['revision']='9999'
    elif fault=='missing_headless':rows.pop()
    elif fault=='override':rows[0]['revisionOverrides']={'ubuntu24.04-x64':'9999'}
    path.write_text(json.dumps({'browsers':rows}))
    versions=dict(v.PINS)
    if fault=='pin':versions['PyJWT']='0.0.0'
    monkeypatch.setattr(v.importlib.metadata,'version',lambda name:versions[name])
    monkeypatch.setattr(v.importlib.metadata,'distribution',lambda _:SimpleNamespace(locate_file=lambda _:path))
    with pytest.raises(v.Unavailable):v.sdk()


@pytest.mark.parametrize('fault',['none','marker','executable','wrong_version','changed_binary'])
def test_both_native_payloads_are_complete_executable_and_stable_before_admission(tmp_path,monkeypatch,fault):
    home=tmp_path/'user'
    cache=home/'.cache/ms-playwright'
    targets=[('chromium-1217','chrome-linux64/chrome'),
             ('chromium_headless_shell-1217','chrome-headless-shell-linux64/chrome-headless-shell')]
    for directory,name in targets:
        binary=cache/directory/name;binary.parent.mkdir(parents=True)
        binary.write_bytes(b'SYNTHETIC_BINARY_NEVER_EXECUTED');binary.chmod(0o755)
        (cache/directory/'INSTALLATION_COMPLETE').write_bytes(b'')
    first=cache/targets[0][0]/targets[0][1]
    if fault=='marker':(cache/targets[0][0]/'INSTALLATION_COMPLETE').unlink()
    elif fault=='executable':first.chmod(0o644)
    calls=[]
    def probe(binary):
        calls.append(binary)
        if fault=='changed_binary':binary.write_bytes(b'changed payload')
        return {'status':'UNKNOWN' if fault=='wrong_version' else 'ready'}
    monkeypatch.setattr(v.pwd,'getpwuid',lambda _:SimpleNamespace(pw_dir=str(home)))
    monkeypatch.setattr(v,'version_probe',probe)
    result={}
    if fault=='none':
        assert set(v.payloads(result))=={'chromium','chromium-headless-shell'} and len(calls)==2
    else:
        with pytest.raises((v.Unavailable,OSError)):v.payloads(result)
        if fault in ('marker','executable'):assert not calls


@pytest.mark.parametrize('fault',['none','timeout','wrong_version','unobserved_launch','live_group'])
def test_version_probe_is_only_one_bounded_binary_flag_and_never_fakes_retirement(monkeypatch,fault):
    calls=[]
    class Process:
        pid=321
        returncode=None if fault=='timeout' else 0
        stdout=io.BytesIO()
        def communicate(self,timeout):
            assert 0<=timeout<=4
            if fault=='timeout':raise subprocess.TimeoutExpired('synthetic-version',timeout)
            return (('Google Chrome for Testing '+('999.0.0.0' if fault=='wrong_version' else v.VERSION)+'\n').encode(),None)
        def poll(self):return self.returncode
        def wait(self,timeout):
            assert 0<=timeout<=5
            self.returncode=-9 if fault=='timeout' else 0
            return self.returncode
    def launch(args,**kw):
        calls.append((args,kw))
        if fault=='unobserved_launch':raise MemoryError('synthetic postfork failure')
        return Process()
    signals=[]
    def killpg(pid,number):
        assert pid==321
        signals.append(number)
        if number==0 and fault!='live_group':raise ProcessLookupError()
    monkeypatch.setattr(v.subprocess,'Popen',launch)
    monkeypatch.setattr(v.os,'killpg',killpg)
    record=v.version_probe(Path('/owned/chrome'))
    assert calls[0][0]==['/owned/chrome','--version']
    assert calls[0][1]['start_new_session'] is True
    assert calls[0][1]['stdin']==subprocess.DEVNULL and calls[0][1]['stderr']==subprocess.DEVNULL
    assert set(calls[0][1]['env'])=={'PATH','LANG'}
    assert record['status']==('ready' if fault=='none' else 'UNKNOWN')
    if fault=='unobserved_launch':assert record['pid'] is None and record['direct_process_reaped'] is None and not signals
    if fault=='timeout':assert signal.SIGKILL in signals and record['direct_process_reaped'] is True
