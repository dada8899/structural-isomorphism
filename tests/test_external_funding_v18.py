"""Actual marked private SQLite/legacy Native ledger; no external sender/key."""
import asyncio
from contextlib import closing
from dataclasses import replace
import sqlite3
from uuid import uuid4

import httpx
import pytest
from web.backend.tests.test_formal_main_admission import BETA,envelope,login,prepared,problem,smtp

def uid():return str(uuid4())

@pytest.fixture
def existing_v17(prepared):
 main,admission,paths,messages=prepared
 from api import auth
 from research import first_answer,plan_native
 from research.external_first_answer_catalog import provision_isolated_v17
 from research.external_first_answer_file_writer import approve_isolated_file
 from research.external_funding_v18 import OwnerKeyRegistration
 from web.backend.tests.test_research_first_answer import identity
 from web.backend.tests.test_plan_runtime_transport import provider
 result={}
 async def setup(server):
  async with main.lifespan(main.app):
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
    await login(client,messages)
    response=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'v18-public-fixture'})
    assert response.status_code==200,response.text
    service=admission._STATE[id(main.app)].service;actor=identity(client)
    authority=plan_native.create_controlled_runtime_fixture_authority(service.store,actor,server,approved_cap_units=300_000_000,risk_margin_units=2_129_920)
    provision=plan_native.issue_native_provision(service.store,authority);permit=plan_native.mint_runtime_permit(provision);resource=plan_native.open_plan_resource(permit)
    try:plan_native.install_native_funding(service.store,provision,resource)
    finally:plan_native.retire_installation(service.store)
    with service.store.transaction() as conn:
     owner=conn.execute('SELECT principal_id,generation,owner_gate_id FROM research_plan_native_funding WHERE id=1').fetchone()
     old=tuple(conn.execute('SELECT * FROM research_funding_accounts').fetchone())
    result.update(owner=tuple(owner),old=old)
 with provider() as (server,calls,_):asyncio.run(setup(server));assert calls==[]
 path=paths.private_auth_path();first_answer.provision_first_answers_v16(path)
 marker=path.with_name('STRUCTURE-EXTERNAL-LEDGER-FIXTURE');marker.write_bytes(b'isolated external ledger candidate, no provider\n');marker.chmod(0o600)
 proof=approve_isolated_file(path);provision_isolated_v17(proof)
 record=OwnerKeyRegistration(uid(),uid(),*result['owner'],uid(),uid())
 return path,record,result['old']

def migrate(path,record):
 from research.formula_runtime import _offline_maintenance
 from research.external_funding_v18 import apply_owner_key_v18
 with _offline_maintenance(path,(17,18)) as (target,cap):return apply_owner_key_v18(target,cap,record)

def connection(path):
 from research.financial_guard import install_default_hook
 conn=sqlite3.connect(path,isolation_level=None);conn.row_factory=sqlite3.Row
 install_default_hook(conn);conn.execute('PRAGMA foreign_keys=ON');return conn

def test_canonical18_registration_preserves_old_and_reopens_exact(existing_v17):
 path,record,old=existing_v17;inode=path.stat().st_ino
 assert migrate(path,record)['may_send'] is False and path.stat().st_ino==inode
 from research.external_funding_v18 import read_binding,TABLE
 from research.store import ResearchStore
 with closing(connection(path)) as conn:
  conn.execute('BEGIN');ResearchStore._check_v18(conn)
  assert tuple(conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(old[0],)).fetchone())==old
  facts=read_binding(conn);assert facts['payer_identity_status']=='unknown' and facts['payer_id'] is None and facts['credential_source']=='owner_supplied'
  assert tuple(conn.execute('SELECT settled,held,upper_booked FROM research_funding_accounts WHERE id=?',(record.account_id,)).fetchone())==(0,0,0)
  assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==2
  conn.rollback()
 assert migrate(path,record)['schema']==18
 with pytest.raises(Exception,match='cannot_rebind'):migrate(path,replace(record,credential_incarnation=uid()))

def test_invalid_registration_rolls_back_catalog_and_ledger(existing_v17):
 path,record,old=existing_v17
 with pytest.raises(Exception,match='owner_changed'):migrate(path,replace(record,owner_generation='0'*32))
 with closing(connection(path)) as conn:
  conn.execute('BEGIN')
  assert conn.execute('SELECT version FROM main.research_schema').fetchone()[0]==17
  assert conn.execute("SELECT 1 FROM main.sqlite_schema WHERE name='research_external_owner_funding'").fetchone() is None
  assert tuple(conn.execute('SELECT * FROM research_funding_accounts').fetchone())==old
  conn.rollback()

def test_fixed_new_account_and_binding_cannot_be_mutated_directly(existing_v17):
 path,record,_=existing_v17;migrate(path,record)
 from research.external_funding_v18 import TABLE
 with closing(connection(path)) as conn:
  for sql,args in [("UPDATE research_funding_accounts SET held=1 WHERE id=?",(record.account_id,)),
   ('UPDATE '+TABLE+" SET payer_identity_status='known'",()),('DELETE FROM '+TABLE,()),
   ("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,status,cap) VALUES(?,?,'live','deepseek','CNY','unverified',0)",(uid(),uid()))]:
   with pytest.raises(sqlite3.DatabaseError):conn.execute(sql,args)

def test18_generic_paid_scope_stays_closed(existing_v17):
 path,record,_=existing_v17;migrate(path,record)
 from research.paid_control import _transaction_scope,_current_scope
 with closing(connection(path)) as conn:
  conn.execute('BEGIN IMMEDIATE')
  with _transaction_scope(conn,write=True):
   with pytest.raises(PermissionError):_current_scope(conn)
  conn.rollback()

@pytest.fixture
def money_db(tmp_path):
 """SQL backstop fixture, separate from canonical migration proof above."""
 from research.store import V5_SCHEMA
 from research.external_funding_v18 import DDL,install_hook
 from research.external_first_answer_file_writer import install_closed_hooks
 path=tmp_path/'project-cap.sqlite3';conn=sqlite3.connect(path,isolation_level=None)
 conn.execute('PRAGMA foreign_keys=ON');conn.execute('CREATE TABLE research_principals(id TEXT PRIMARY KEY)')
 conn.execute(V5_SCHEMA['research_funding_accounts'])
 for key in ('old-a','old-b','new-external'):
  conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,status,cap) VALUES(?,?,'live','deepseek','CNY','unverified',0)",(key,key))
 for table in ('research_external_first_answer_runs','research_plan_native_runs','research_plan_dispatches'):
  conn.execute('CREATE TABLE '+table+'(id TEXT PRIMARY KEY,account_id TEXT,state TEXT,cost_state TEXT)')
 conn.execute('CREATE TABLE research_reservations(id TEXT PRIMARY KEY,account_id TEXT,status TEXT)')
 install_hook(conn);install_closed_hooks(conn)
 for ddl in DDL:conn.execute(ddl)
 yield path,conn
 conn.close()

def test_global_cap_serializes_two_accounts_for_last_room(money_db):
 from concurrent.futures import ThreadPoolExecutor
 path,conn=money_db
 conn.execute("UPDATE research_funding_accounts SET settled=298000000 WHERE id='old-a'")
 def reserve(account):
  c=sqlite3.connect(path,isolation_level=None,timeout=3)
  from research.external_first_answer_file_writer import install_closed_hooks
  install_closed_hooks(c)
  try:
   c.execute('BEGIN IMMEDIATE');c.execute('UPDATE research_funding_accounts SET held=held+1500000 WHERE id=?',(account,));c.commit();return 'reserved'
  except sqlite3.IntegrityError:c.rollback();return 'cap-rejected'
  finally:c.close()
 with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(reserve,('old-b','new-external')))==['cap-rejected','reserved']
 assert conn.execute('SELECT sum(settled+held+upper_booked) FROM research_funding_accounts').fetchone()[0]==299500000

def test_net_zero_held_to_booked_not_double_charged_or_blocked(money_db):
 from research.external_funding_v18 import require_room
 _,conn=money_db
 conn.execute("UPDATE research_funding_accounts SET held=300000000 WHERE id='old-a'")
 conn.execute("INSERT INTO research_external_first_answer_runs VALUES('uncertain','new-external','unknown',NULL)")
 conn.execute("UPDATE research_funding_accounts SET held=0,upper_booked=300000000 WHERE id='old-a'")
 assert conn.execute('SELECT sum(settled+held+upper_booked) FROM research_funding_accounts').fetchone()[0]==300000000
 conn.execute("DELETE FROM research_external_first_answer_runs")
 conn.execute('BEGIN IMMEDIATE')
 try:assert require_room(conn,2129920,consuming=True)==300000000
 finally:conn.rollback()

@pytest.mark.parametrize('table,state_column,state,cost',[('research_external_first_answer_runs','state','unknown',None),
 ('research_plan_native_runs','state','closed','held'),('research_plan_dispatches','state','unknown','unknown'),('research_reservations','status','UNKNOWN',None)])
def test_unknown_from_any_original_or_new_domain_blocks_new_money_and_consume(money_db,table,state_column,state,cost):
 from research.external_funding_v18 import project_unresolved,require_room
 _,conn=money_db
 if table=='research_reservations':conn.execute('INSERT INTO '+table+' VALUES(?,?,?)',('same-id','old-a',state))
 else:conn.execute('INSERT INTO '+table+' VALUES(?,?,?,?)',('same-id','old-a',state,cost))
 assert project_unresolved(conn)
 with pytest.raises(sqlite3.IntegrityError,match='unknown'):conn.execute("UPDATE research_funding_accounts SET held=1 WHERE id='new-external'")
 conn.execute("INSERT INTO research_external_first_answer_runs VALUES('next','new-external','confirmed',NULL)")
 with pytest.raises(sqlite3.IntegrityError,match='unknown'):conn.execute("UPDATE research_external_first_answer_runs SET state='consumed' WHERE id='next'")
 conn.execute('BEGIN')
 try:
  with pytest.raises(Exception,match='unknown'):require_room(conn,1000,consuming=True,excluding=('research_external_first_answer_runs','next'))
 finally:conn.rollback()

def test_exclusion_is_exact_table_and_id_not_account(money_db):
 from research.external_funding_v18 import project_unresolved
 _,conn=money_db
 conn.execute("INSERT INTO research_external_first_answer_runs VALUES('same','new-external','consumed',NULL)")
 assert not project_unresolved(conn,excluding=('research_external_first_answer_runs','same'))
 conn.execute("INSERT INTO research_plan_native_runs VALUES('same','old-a','unknown','unknown')")
 assert project_unresolved(conn,excluding=('research_external_first_answer_runs','same'))

def test_all_v17_declarations_are_unchanged_subset():
 from research.store import ResearchStore
 assert ResearchStore._current_structure_declarations(version=17).items()<=ResearchStore._current_structure_declarations(version=18).items()
