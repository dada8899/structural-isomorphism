"""Run the frozen real R10 cold storage producer against a waiting peer's DB."""
from pathlib import Path
import json
import os
import subprocess
import sys
from uuid import uuid4
from .source_v10_reference import reconstruct

CHILD = r'''
import hashlib,json,os,runpy,sqlite3,sys
from pathlib import Path
root,path,manifest_path,history_script,output=sys.argv[1:]
root=Path(root);path=Path(path);manifest=json.loads(Path(manifest_path).read_text())
loaded=runpy.run_path(history_script,run_name='frozen_history_observer')['loaded']
loaded(root,manifest['files'])
from services.auth_store import AuthStore
from research import ResearchStore
files,modules=loaded(root,manifest['files'])
identity=(path.stat().st_dev,path.stat().st_ino)
def catalog():
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:return conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
    finally:conn.close()
before=catalog();auth=AuthStore(path)
assert catalog()==before,'historical Auth factory changed the existing Auth graph'
store=ResearchStore(auth)
with store.transaction() as conn:
    assert conn.execute('SELECT id,version FROM research_schema').fetchall()[0][:]==(1,10)
    store._check_structure_version(conn,10);store._check_v10(conn)
    assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert conn.execute('PRAGMA foreign_keys').fetchone()[0]==1
    assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
assert (path.stat().st_dev,path.stat().st_ino)==identity
files,modules=loaded(root,manifest['files'])
guard=sys.modules.get('audit_bootstrap');closed=0
if guard is not None:
    for conn in guard.handles:
        try:conn.execute('SELECT 1')
        except sqlite3.ProgrammingError:closed+=1
        else:raise AssertionError('historical cold producer leaked a native connection')
Path(output).write_text(json.dumps({'version':10,'identity':list(identity),'auth_graph_unchanged':True,'source_files':files,'loaded_modules':modules,'pid':os.getpid(),'native_closed_on_creator':closed}))
'''


def produce(path):
    path=Path(path);current=Path(__file__).resolve().parents[3]
    package=path.parent/('frozen10-'+str(uuid4()))
    package,_problem,manifest_path=reconstruct(current,package)
    output=package/'cold-result.json';log=package/'cold-producer.log'
    environment={**os.environ,'STRUCTURAL_ENV':'dev','PYTHONPATH':str(package/'web/backend')+os.pathsep+str(package)}
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:
        environment['REVIEW_SOURCE_ROOT']=str(package)
        environment['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+environment['PYTHONPATH']
    with log.open('wb') as stream:
        result=subprocess.run([sys.executable,'-B','-c',CHILD,str(package),str(path),str(manifest_path),str(current/'web/backend/tests/source_v10_history_producer.py'),str(output)],cwd=package,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=20)
    assert result.returncode==0,log.read_text()
    value=json.loads(output.read_text());manifest=json.loads(manifest_path.read_text())
    assert value['version']==10 and value['auth_graph_unchanged']
    assert value['source_files'] and all(manifest['files'][name]['sha256']==digest for name,digest in value['source_files'].items())
    assert value['loaded_modules'] and all(name in value['source_files'] for name in value['loaded_modules'].values())
    return value
