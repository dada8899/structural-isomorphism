"""Offline exact historical bytes; line deltas, never version-marker emulation."""
import hashlib,json,os,subprocess,sys
from pathlib import Path


def historical_bytes(root,relative,expected):
    root=Path(root).resolve();relative=Path(relative)
    assert not relative.is_absolute() and '..' not in relative.parts and relative.suffix=='.py'
    source=root/relative
    assert source.is_file() and not source.is_symlink()
    for parent in source.parents:
        if parent==root:break
        assert not parent.is_symlink()
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()==expected:return raw
    entries=json.loads((root/'web/backend/tests/reference/method_v13/deltas.json').read_text())
    patch=entries[relative.as_posix()]
    assert patch['original_sha256']==expected and hashlib.sha256(raw).hexdigest()==patch['current_sha256'],'historical dependency mismatch: '+relative.as_posix()
    lines=raw.decode().splitlines(keepends=True)
    for start,end,text in reversed(patch['hunks']):lines[start:end]=text.splitlines(keepends=True)
    raw=''.join(lines).encode()
    assert hashlib.sha256(raw).hexdigest()==expected
    return raw


def reconstruct(root,destination,mode):
    root=Path(root).resolve();destination=Path(destination).resolve()
    manifest_path=root/'web/backend/tests/reference/method_v13/manifest.json'
    manifest=json.loads(manifest_path.read_text())['cases'][mode]
    assert not destination.exists();destination.mkdir(mode=0o700)
    for relative,entry in manifest['files'].items():
        assert relative.startswith('web/backend/')
        raw=historical_bytes(root,relative,entry['sha256'])
        path=destination/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return destination,manifest_path


def produce(root,destination,state,output,*,mode='native'):
    root=Path(root).resolve();package,manifest=reconstruct(root,destination,mode)
    env={**os.environ,'METHOD13_ROOT':str(package),'METHOD13_MANIFEST':str(manifest),
        'PYTHONPATH':str(package/'web/backend')+os.pathsep+str(package)}
    guard=sys.modules.get('audit_bootstrap')
    if guard:
        env['REVIEW_SOURCE_ROOT']=str(package)
        env['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+env['PYTHONPATH']
    script=root/'web/backend/tests/method_v13_history_producer.py'
    declared=json.loads(manifest.read_text())
    assert hashlib.sha256(script.read_bytes()).hexdigest()==declared['producer_sha256']
    assert hashlib.sha256((root/'web/backend/tests/reference/plan_v12/problem.json').read_bytes()).hexdigest()==declared['problem_sha256']
    log=Path(output).with_suffix('.producer.log')
    with log.open('wb') as stream:
        result=subprocess.run([sys.executable,str(script),str(state),str(output),mode],cwd=package,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=45)
    assert result.returncode==0,log.read_text()
    value=json.loads(Path(output).read_text());expected=json.loads(manifest.read_text())['cases'][mode]
    assert value['source_files']=={name:entry['sha256'] for name,entry in expected['files'].items()}
    assert value['loaded_modules']==expected['loaded_modules']
    return value
