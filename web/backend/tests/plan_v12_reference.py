"""Offline test-only reconstruction of the reviewed R12 producer's code closure."""
import hashlib,json
from pathlib import Path


def reconstruct(current_root,destination):
    current_root=Path(current_root).resolve();destination=Path(destination).resolve()
    reference=current_root/'web/backend/tests/reference/plan_v12'
    manifest_path=reference/'manifest.json';manifest=json.loads(manifest_path.read_text())
    assert not destination.exists(),'historical package destination must be new'
    destination.mkdir(mode=0o700)
    for relative,entry in manifest['files'].items():
        name=Path(relative)
        assert not name.is_absolute() and '..' not in name.parts and relative.startswith('web/backend/') and name.suffix=='.py'
        source=(reference/'overrides'/name) if entry['source']=='reference' else current_root/name
        assert entry['source'] in ('reference','current_exact')
        assert source.is_file() and not source.is_symlink()
        assert source.resolve().is_relative_to(reference.resolve() if entry['source']=='reference' else current_root)
        for parent in source.parents:
            if parent==current_root:break
            assert not parent.is_symlink(),'historical dependency cannot traverse symlink'
        content=source.read_bytes()
        if entry['source']=='current_exact':
            from .method_v13_reference import historical_bytes
            content=historical_bytes(current_root,relative,entry['sha256'])
        assert hashlib.sha256(content).hexdigest()==entry['sha256'],'historical dependency changed: '+relative
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    problem=reference/'problem.json'
    assert hashlib.sha256(problem.read_bytes()).hexdigest()==manifest['problem_sha256']
    assert not (destination/'.git').exists()
    return destination,problem,manifest_path


def produce(current_root,destination,state,output):
    """Fresh subprocess, with path/hash checks before any historical HTTP write."""
    import os,subprocess,sys
    current_root=Path(current_root).resolve();destination=Path(destination)
    package,problem,manifest_path=reconstruct(current_root,destination)
    environment={**os.environ,'PLAN12_ROOT':str(package),'PLAN12_MANIFEST':str(manifest_path),
        'PYTHONPATH':str(package/'web/backend')+os.pathsep+str(package)}
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:
        environment['REVIEW_SOURCE_ROOT']=str(package)
        environment['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+environment['PYTHONPATH']
    script=current_root/'web/backend/tests/plan_v12_history_producer.py'
    log=Path(output).with_suffix('.producer.log')
    with log.open('wb') as stream:
        result=subprocess.run([sys.executable,str(script),str(state),str(output),str(problem)],cwd=package,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=20)
    assert result.returncode==0,log.read_text()
    original=json.loads(Path(output).read_text());manifest=json.loads(manifest_path.read_text())
    assert original['source_files']=={name:entry['sha256'] for name,entry in manifest['files'].items()}
    assert original['loaded_modules']==manifest['loaded_modules']
    return original
