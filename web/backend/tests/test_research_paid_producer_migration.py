"""Real nonempty v5->v6, preserving old financial facts on every fault."""
import sqlite3

import pytest

from .test_research_paid_schema import legacy,snapshot,rows
from .test_research_persistence import stack
from api import auth
from research import ResearchStore
from research.store import V6_SCHEMA,V6_AUX,V5_AUX,V5_GUARDS,PRODUCER_DDL


@pytest.fixture
def v5(legacy,monkeypatch):
    client,path,old,provider,ids=legacy
    with monkeypatch.context() as boundary:
        boundary.setattr(ResearchStore,'_migrate_v6',lambda self:None)
        store=ResearchStore(auth._store())
    with store.transaction() as conn:assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==5
    return client,path,store,provider,ids


def test_nonempty_v5_upgrade_preserves_old_policies_money_receipts_and_inodes(v5):
    _,path,_,_,_=v5;before=rows(path)
    locks={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    store=ResearchStore(auth._store())
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==6
        for table,(columns,values) in before.items():
            if table=='research_schema':continue
            selected=','.join('"'+name+'"' for name in columns)
            assert [tuple(r) for r in conn.execute('SELECT '+selected+' FROM '+table+' ORDER BY rowid')]==values
        assert set(r[0] for r in conn.execute('SELECT status FROM research_reservations'))=={'HELD','SENT','UNKNOWN','SETTLED'}
        assert conn.execute('SELECT count(*) FROM research_paid_approvals').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_provider_sessions').fetchone()[0]==0
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert {p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}==locks
    ResearchStore(auth._store())


FAULTS=[(phase,name) for phase in ('CREATE TABLE','INSERT INTO','DROP TABLE','ALTER TABLE') for name in V6_SCHEMA]
FAULTS += [('SQL',sql) for sql in (*PRODUCER_DDL,*V6_AUX,*V5_GUARDS)]
FAULTS += [('SQL','DROP '+('INDEX' if ddl.startswith('CREATE UNIQUE INDEX') else 'TRIGGER')+' IF EXISTS '+(ddl.split()[3] if ddl.startswith('CREATE UNIQUE INDEX') else ddl.split()[2])) for ddl in (*V5_AUX,*V5_GUARDS)]
FAULTS += [('SQL','UPDATE research_schema SET version=6'),('COMMIT',None)]


@pytest.mark.parametrize('phase,target',FAULTS)
def test_v6_every_write_boundary_rollback_is_exact_v5(v5,monkeypatch,phase,target):
    _,path,store,_,_=v5;before=snapshot(path);original=sqlite3.connect;raised=[];restored=[]
    marker=target if phase=='SQL' else phase+' '+target+('_v6' if phase in ('CREATE TABLE','INSERT INTO','ALTER TABLE') else '') if target else None
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if marker and sql.startswith(marker) and not raised:
                raised.append(True);raise sqlite3.OperationalError('owned producer migration fault')
            return super().execute(sql,*args,**kwargs)
        def commit(self):
            if phase=='COMMIT' and self.in_transaction and not raised:
                raised.append(True);raise sqlite3.OperationalError('owned producer migration fault')
            return super().commit()
        def close(self):
            restored.append(self.execute('PRAGMA foreign_keys').fetchone()[0]);super().close()
    monkeypatch.setattr(sqlite3,'connect',lambda *a,**k:original(*a,**k,factory=Fault))
    with pytest.raises(sqlite3.OperationalError,match='owned producer migration fault'):store._migrate_v6()
    monkeypatch.setattr(sqlite3,'connect',original)
    assert raised and restored==[1] and snapshot(path)==before
    ResearchStore(auth._store())
