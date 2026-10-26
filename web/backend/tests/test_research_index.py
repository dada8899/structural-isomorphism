"""Actual research routes/auth/SQLite; no index, permission or DB mocks."""
import base64
from contextlib import closing
import json
import sqlite3
import importlib
import logging
import sys
import time
import jwt
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from .test_research_persistence import stack,app,problem,post,login,trusted_sso
from .test_research_lifecycle import lifecycle
from .test_research_c0 import c0,start as c0_start
from api import auth
from research import ResearchStore,ResearchRunner


def save(client,title,key=None):
    body=problem("PRIVATE-ORIGINAL-INDEX-CANARY")
    body.update(summary=title,objective="PRIVATE-OBJECTIVE-INDEX-CANARY")
    response=post(client,"/api/research",{"problem":body},key or str(uuid4()))
    assert response.status_code==200,response.text
    return response.json()["data"]["research"]["id"]


def listing(client,**params):
    response=client.get("/api/research",params=params)
    assert response.status_code==200,response.text
    assert response.headers["cache-control"]=="no-store"
    assert response.headers["referrer-policy"]=="no-referrer"
    data=response.json()["data"]
    assert set(data)=={"items","next_cursor"} and len(data["items"])<=20
    for item in data["items"]:
        assert set(item)=={"research_id","title","current_input_revision","updated_at","current_task"}
        assert len(item["title"])<=160
        if item["current_task"] is not None:assert set(item["current_task"])=={"execution","evidence"}
    assert "PRIVATE-ORIGINAL" not in response.text and "PRIVATE-OBJECTIVE" not in response.text
    return data


def business_rows(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'research_%'")]
        return {name:conn.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in tables}


def decode(cursor):return json.loads(base64.urlsafe_b64decode(cursor+"="*((-len(cursor))%4)))
def encode(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(",",":"),ensure_ascii=False).encode()).decode().rstrip("=")


def test_empty_index_does_not_create_principal_research_grants_tasks_or_fees(stack):
    client,path=stack
    ResearchStore(auth._store())
    before=business_rows(path)
    assert listing(client)=={"items":[],"next_cursor":None}
    assert business_rows(path)==before
    with closing(sqlite3.connect(path)) as conn, conn:
        for table in ("research_principals","research_controls","research_grants","research_tasks","research_funding_accounts","research_reservations","research_cost_observations"):
            assert conn.execute("SELECT count(*) FROM "+table).fetchone()[0]==0


def test_twenty_one_tied_records_paginate_without_duplicates_and_survive_reopen(stack):
    client,path=stack
    ids=[save(client,f"研究摘要第{n:02d}项：当前问题待验证") for n in range(21)]
    with closing(sqlite3.connect(path)) as conn, conn:conn.execute("UPDATE research_controls SET updated_at='2026-10-17T00:00:00.000000Z'")
    before=business_rows(path)
    first=listing(client)
    assert len(first["items"])==20 and first["next_cursor"]
    second=listing(client,cursor=first["next_cursor"])
    result=first["items"]+second["items"]
    assert [r["research_id"] for r in result]==sorted(ids,reverse=True)
    assert len({r["research_id"] for r in result})==21 and second["next_cursor"] is None
    assert all(r["current_task"] is None and r["current_input_revision"]==1 for r in result)
    with closing(sqlite3.connect(path)) as conn, conn:pid=conn.execute("SELECT id FROM research_principals").fetchone()[0]
    cursor=decode(first["next_cursor"])
    assert set(cursor)=={"operation","scope","updated_at","research_id"} and pid not in json.dumps(cursor)
    with TestClient(app()) as reopened:
        reopened.cookies.update(client.cookies)
        assert listing(reopened)==first
        assert listing(reopened,cursor=first["next_cursor"])==second
    assert business_rows(path)==before


def test_unicode_xss_title_is_bounded_json_text_and_latest_revision(stack):
    client,_=stack
    title='<img src=x onerror="alert(1)">'+'😀'*170
    rid=save(client,title)
    item,=listing(client)["items"]
    assert item["title"]==title[:160] and item["research_id"]==rid
    changed=problem();changed["summary"]="新的当前问题摘要，不继承旧标题"
    assert post(client,f"/api/research/{rid}/revisions",{"expected_revision":1,"problem":changed}).status_code==200
    assert listing(client)["items"][0]["title"]==changed["summary"]


def test_task_summary_only_uses_latest_task_of_current_input(c0):
    client,path,store,provider=c0
    rid,first=c0_start(client,"index-history")
    assert ResearchRunner(store).run_once(first)=="COMPLETED"
    item,=listing(client)["items"]
    assert item["current_task"]=={"execution":"COMPLETED","evidence":"INSUFFICIENT"}
    second=post(client,f"/api/research/{rid}/tasks",{"input_revision":1,"expected_research_version":client.get(f"/api/research/{rid}").json()["data"]["research_version"],"mode":"research"})
    assert second.status_code==200,second.text
    assert listing(client)["items"][0]["current_task"]=={"execution":"QUEUED","evidence":"UNASSESSED"}
    changed=problem();changed["summary"]="第二版尚未开始任务的问题摘要"
    assert post(client,f"/api/research/{rid}/revisions",{"expected_revision":1,"problem":changed}).status_code==200
    item,=listing(client)["items"]
    assert item["current_input_revision"]==2 and item["current_task"] is None
    assert provider.count()==2


def test_other_account_and_cross_owner_cursor_do_not_leak(stack):
    client,_=stack
    mine={save(client,f"本人摘要{n}号研究记录") for n in range(2)}
    cursor=listing(client,limit=1)["next_cursor"]
    with TestClient(app()) as other:
        login(other,"index-other@example.test")
        assert listing(other)=={"items":[],"next_cursor":None}
        theirs=save(other,"另一账户的研究摘要，仅本人可见")
        assert {r["research_id"] for r in listing(other)["items"]}=={theirs}
        rejected=other.get("/api/research",params={"cursor":cursor})
        assert rejected.status_code==422
        assert all(rid not in rejected.text for rid in mine)
    assert {r["research_id"] for r in listing(client)["items"]}==mine


def test_same_email_new_generation_never_inherits_index_or_cursor(stack):
    client,_=stack
    ids={save(client,f"原代际摘要{n}号研究记录") for n in range(2)}
    cursor=listing(client,limit=1)["next_cursor"]
    old=client.cookies.get("phase_session")
    auth._store().delete_account_data("research-a@example.test")
    login(client)
    assert listing(client)=={"items":[],"next_cursor":None}
    assert client.get("/api/research",params={"cursor":cursor}).status_code==422
    new=save(client,"新代际自己的研究摘要，没有继承")
    assert {r["research_id"] for r in listing(client)["items"]}=={new} and new not in ids
    client.cookies.clear();client.cookies.set("phase_session",old)
    response=client.get("/api/research")
    assert response.status_code==401 and all(rid not in response.text for rid in ids)


def test_revoked_acl_hidden_on_each_page_and_principal_revocation_denied(stack):
    client,path=stack
    ids=[save(client,f"权限核对第{n}条研究摘要") for n in range(3)]
    first=listing(client,limit=1);anchor=first["items"][0]["research_id"]
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=?",(anchor,))
    assert anchor not in {r["research_id"] for r in listing(client)["items"]}
    response=client.get("/api/research",params={"cursor":first["next_cursor"]})
    assert response.status_code==409 and anchor not in response.text
    with closing(sqlite3.connect(path)) as conn, conn:conn.execute("UPDATE research_principals SET status='revoked'")
    assert client.get("/api/research").status_code==404


def test_deleted_account_index_cannot_read_old_records(lifecycle):
    client,_,_=lifecycle
    rid=save(client,"删除前的私有研究摘要，仅本人可见")
    response=client.post("/api/me/delete",json={"confirmation":"DELETE"},headers={"Origin":"http://testserver"})
    assert response.status_code==200,response.text
    denied=client.get("/api/research")
    assert denied.status_code==401 and rid not in denied.text


@pytest.mark.parametrize("credentials,expected",[("conflict",409),("poisoned",401),("logout",401),("same_sso",200),("sso_only",401)])
def test_index_uses_same_canonical_credentials_before_returning_titles(stack,credentials,expected):
    client,_=stack;rid=save(client,"凭据隔离摘要：不得越过失效会话")
    if credentials=="conflict":
        with TestClient(app()) as other:login(other,"index-other@example.test")
        client.cookies.set("structural_beta_session",trusted_sso("index-other@example.test"))
    elif credentials=="poisoned":client.cookies.set("structural_beta_session","invalid")
    elif credentials=="logout":
        old=client.cookies.get("phase_session")
        assert client.post("/api/auth/logout",headers={"Origin":"http://testserver"}).status_code==200
        client.cookies.clear();client.cookies.set("phase_session",old)
    else:
        client.cookies.set("structural_beta_session",trusted_sso("research-a@example.test"))
        if credentials=="sso_only":client.cookies.delete("phase_session")
    response=client.get("/api/research")
    assert response.status_code==expected,response.text
    if expected!=200:assert rid not in response.text and "凭据隔离摘要" not in response.text


@pytest.mark.parametrize("query",["owner=x","principal_id=x","epoch=1","limit=0","limit=21","limit=-1","limit=01","limit=1.0","limit=true","limit=","limit=1&limit=1","cursor=x&cursor=x","cursor=","cursor=%0A","cursor="+'x'*1025,"limit=1&unknown=x"])
def test_strict_query_keys_limit_and_cursor_boundaries(stack,query):
    client,_=stack
    response=client.get("/api/research?"+query)
    assert response.status_code==422,response.text
    assert set(response.json()["error"])>={"code"}


@pytest.mark.parametrize("change",["namespace","shape","foreign_scope","unknown_anchor","invalid_date","duplicate","not_object"])
def test_cursor_strict_shape_scope_namespace_and_anchor(stack,change):
    client,_=stack
    for n in range(2):save(client,f"游标校验第{n}条研究摘要")
    valid=listing(client,limit=1)["next_cursor"];value=decode(valid)
    expected=422
    if change=="namespace":value["operation"]="source-records"
    elif change=="shape":value["owner_id"]=str(uuid4())
    elif change=="foreign_scope":value["scope"]="0"*64
    elif change=="unknown_anchor":value["research_id"]=str(uuid4());expected=409
    elif change=="invalid_date":value["updated_at"]="2026-99-99T00:00:00.000000Z"
    elif change=="not_object":value=[]
    cursor=encode(value)
    if change=="duplicate":cursor=base64.urlsafe_b64encode(('{"operation":"x",'+json.dumps(value)[1:]).encode()).decode().rstrip("=")
    response=client.get("/api/research",params={"cursor":cursor})
    assert response.status_code==expected,response.text


def test_boundary_update_expires_cursor_without_showing_stale_data(stack):
    client,_=stack
    for n in range(2):save(client,f"边界更新第{n}条研究摘要")
    first=listing(client,limit=1);rid=first["items"][0]["research_id"]
    revised=problem();revised["summary"]="修改边界后需要从列表首页重新读取"
    assert post(client,f"/api/research/{rid}/revisions",{"expected_revision":1,"problem":revised}).status_code==200
    assert client.get("/api/research",params={"cursor":first["next_cursor"]}).status_code==409
    assert listing(client)["items"][0]["title"]==revised["summary"]


def _actual_main_index_probe(root):
    """Current15 Owner/session and records persist across two genuine Main scopes.

    This is not a legacy_auth/Research11 migration claim: the existing current
    production fixture creates the database and actual registration authority.
    """
    from contextlib import contextmanager, closing
    from urllib.parse import parse_qs, urlsplit
    from .test_formal_main_admission import smtp, prepared, BETA, envelope
    with pytest.MonkeyPatch.context() as patch:
        with contextmanager(smtp.__wrapped__)() as mail:
            with contextmanager(prepared.__wrapped__)(root,patch,mail) as configured:
                main,admission,paths,messages=configured
                path=paths.STATE_ROOT/'auth.sqlite3'
                email='research-a@example.test'
                with TestClient(main.app,base_url=BETA) as client:
                    assert admission.require(main.app,'research_basic') is None
                    assert 'search' not in main.app_state
                    requested=client.post('/api/auth/request-link',json={'email':email},headers={'Origin':BETA})
                    assert requested.status_code==200 and 'dev_token' not in requested.json()
                    message=next(m for m in reversed(messages) if m['To']==email)
                    link=message.get_body(preferencelist=('plain',)).get_content().strip().split()[-1]
                    token=parse_qs(urlsplit(link).query)['token'][0]
                    try:verified=client.post('/api/auth/verify',json={'token':token},headers={'Origin':BETA})
                    finally:token=None;link=None
                    assert verified.status_code==200
                    body=problem('PRIVATE-ORIGINAL-INDEX-CANARY')
                    body.update(summary='原应用挂载的研究列表，仍按本人权限读取',objective='PRIVATE-OBJECTIVE-INDEX-CANARY')
                    made=client.post('/api/research',json=envelope({'problem':body}),
                                     headers={'Origin':BETA,'Idempotency-Key':str(uuid4())})
                    assert made.status_code==200
                    rid=made.json()['data']['research']['id']
                    cookie=client.cookies.get('phase_session');assert cookie
                    before=path.stat()
                    tables=('research_controls','research_revisions','research_principals','research_grants')
                    with closing(sqlite3.connect(path)) as conn:
                        rows={name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in tables}
                assert id(main.app) not in admission._STATE
                with TestClient(main.app,base_url=BETA) as mounted:
                    assert admission.require(main.app,'research_basic') is None
                    assert 'search' not in main.app_state
                    mounted.cookies.update(client.cookies)
                    same_cookie=mounted.cookies.get('phase_session')==cookie;assert same_cookie
                    result=listing(mounted)
                    assert [item['research_id'] for item in result['items']]==[rid]
                    assert mounted.get(f'/api/research/{rid}').status_code==200
                    mounted.cookies.clear()
                    assert mounted.get('/api/research').status_code==401
                    with closing(sqlite3.connect(path)) as conn:
                        assert conn.execute('SELECT count(*) FROM research_controls').fetchone()[0]==1
                        assert {name:conn.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall() for name in tables}==rows
                    after=path.stat();assert (after.st_dev,after.st_ino)==(before.st_dev,before.st_ino)
                assert id(main.app) not in admission._STATE
    print('owned-index-real-main-ok')


def test_actual_main_app_mount_uses_same_owner_auth_and_persistent_records(tmp_path):
    from .research_process_fixture import _run_owned_probe
    from pathlib import Path
    root=tmp_path/'actual-main-index';root.mkdir()
    program="""
import sys
from pathlib import Path
source=Path(SOURCE_ROOT)
sys.path[:0]=[str(source/'web/backend'),str(source)]
from web.backend.tests.test_research_index import _actual_main_index_probe
_actual_main_index_probe(Path(DATA_ROOT))
""".replace('DATA_ROOT',repr(str(root))).replace('SOURCE_ROOT',repr(str(Path(__file__).resolve().parents[3])))
    # Offline producers use dir_fd-relative mkdir. The existing probe's data
    # working directory is owned scratch; source imports stay absolute.
    result=_run_owned_probe(program,root)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'owned-index-real-main-ok' in result.stdout


def test_duplicate_valid_cursor_is_rejected_not_silently_collapsed(stack):
    client,_=stack
    for n in range(2):save(client,f"重复游标第{n}条研究摘要")
    cursor=listing(client,limit=1)["next_cursor"]
    assert client.get("/api/research",params=[("cursor",cursor),("cursor",cursor)]).status_code==422
    assert len(listing(client,cursor=cursor)["items"])==1


def test_expired_signed_session_cannot_read_index(stack):
    client,_=stack;rid=save(client,"到期会话不能读取这条研究标题")
    claims=auth._decode_jwt(client.cookies.get("phase_session"))
    claims["exp"]=int(time.time())-60
    token=jwt.encode(claims,auth._jwt_secret(),algorithm="HS256")
    client.cookies.clear();client.cookies.set("phase_session",token)
    response=client.get("/api/research")
    assert response.status_code==401 and rid not in response.text and "到期会话" not in response.text
