"""Real browser -> mounted main app -> canonical auth/SQLite.

Only unrelated legacy search/model lifespan is disabled. No research API,
authorization, storage, projection, or page response is mocked.
"""
from __future__ import annotations

import json
import re
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"


@pytest.fixture
def server(tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(BACKEND) + os.pathsep + str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
        "AUTH_DATA_DIR": str(tmp_path / "auth"), "AUTH_ENABLED": "true", "AUTH_DEV_MODE": "true",
        "JWT_SECRET": "research-browser-synthetic-secret-32-characters", "AUTH_LINK_BASE_URL": base,
        "STRUCTURAL_ENV": "test", "STRUCTURAL_RESEARCH_ENABLED": "true", "ADMIN_NOTIFICATION_EMAIL": "",
        "STRUCTURAL_SSO_SECRET": "research-browser-sso-synthetic-secret-32-characters",
        "STRUCTURAL_SSO_DATA_DIR": str(tmp_path / "sso"), "STRUCTURAL_SSO_BETA_ORIGIN": base,
        "STRUCTURAL_FAVORITES_PATH": str(tmp_path / "favorites.jsonl"), "STRUCTURAL_LOG_FILE": str(tmp_path / "app.jsonl"),
        "STRUCTURAL_PRIVACY_HMAC_KEY": "0123456789abcdef" * 4,
    })
    for key in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "SMTP_PASSWORD"):
        env.pop(key, None)
    processes = []
    log = (tmp_path / "uvicorn.log").open("w+")

    last_env=dict(env)
    def start(*, fault="none", seed_owner_report=False, c0_port=0, d1_sources=False):
        nonlocal last_env
        run_env={**env,"STRUCTURAL_C0_ENABLED":"true" if c0_port else "false",
                 "STRUCTURAL_D1_SOURCES_ENABLED":"true" if d1_sources else "false","STRUCTURAL_D1_PUBLIC_GET_ENABLED":"false"}
        last_env=run_env
        # Bind every real legacy store to this test's private directory before
        # importing the actual main app; never touch the source default DB.
        launcher = """
import sys
from pathlib import Path
from api import report_account, report, favorites, sso
from services.report_store import ReportStore
report_account._store = ReportStore(Path(sys.argv[1]))
report._store = report_account._store
favorites._legacy_data_file = lambda: Path(sys.argv[1]).parent / 'unused-legacy-favorites.jsonl'
if sys.argv[4] == 'seed-owner-report':
    subject = sso._subject_id('browser-a@example.test')
    if not report_account._store.list_by_owner(subject):
        from tests.test_report_api import _create_current_v2_report
        item, _ = _create_current_v2_report(report_account._store)
        report_account._store.claim_by_anon('device-owner', subject)
if sys.argv[3] == 'legacy-delete-failure':
    from services.auth_store import AuthStore
    def fail_delete(self, email, **kwargs):
        raise OSError('synthetic legacy cleanup fault')
    AuthStore.delete_account_data = fail_delete
if int(sys.argv[5]):
    from api import auth
    from research import ResearchStore, BudgetLedger
    BudgetLedger(ResearchStore(auth._store())).provision_fixture(int(sys.argv[5]))
import main
import uvicorn
uvicorn.run(main.app, fd=int(sys.argv[2]), lifespan='off', access_log=False, log_level='warning')
"""
        process = subprocess.Popen([
            os.getenv("STRUCTURE_RESEARCH_TEST_PYTHON", sys.executable), "-c", launcher,
            str(tmp_path / "legacy-history.db"), str(listener.fileno()), fault,
            "seed-owner-report" if seed_owner_report else "no-seed",
            str(c0_port),
        ], cwd=BACKEND, env=run_env, pass_fds=(listener.fileno(),), stdout=log, stderr=log)
        processes.append(process)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.flush(); log.seek(0)
                raise AssertionError("Main app failed to start: " + log.read()[-2000:])
            try:
                if httpx.get(base + "/research", timeout=.5, trust_env=False).status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            time.sleep(.05)
        raise AssertionError("Main app readiness timed out")

    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)

    def run_worker(task_id):
        return subprocess.run([os.getenv("STRUCTURE_RESEARCH_TEST_PYTHON",sys.executable),"-m","research.worker","--once","--task",task_id],cwd=BACKEND,env=last_env,capture_output=True,text=True,timeout=15)

    def run_source_worker(task_id,port,*,drop=False):
        code="""
from functools import partial
import sys
from api import auth
from research import ResearchStore,ResearchRunner
from research.source_policy import PinnedPublicTransport
from web.backend.tests.source_http_fixture import get_local,drop_after_response
if __name__=='__main__':
    worker=drop_after_response if sys.argv[3]=='drop' else get_local
    print(ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(worker,int(sys.argv[2])))).run_once(sys.argv[1]))
"""
        return subprocess.run([os.getenv("STRUCTURE_RESEARCH_TEST_PYTHON",sys.executable),"-c",code,task_id,str(port),"drop" if drop else "normal"],cwd=BACKEND,env=last_env,capture_output=True,text=True,timeout=15)

    def stop_all():
        for process in processes:stop(process)

    try:
        process = start()
        yield {"base": base, "path": tmp_path / "auth" / "auth.sqlite3", "start": start, "stop": stop, "process":process, "root": tmp_path,"run_worker":run_worker,"run_source_worker":run_source_worker,"stop_all":stop_all}
    finally:
        for process in processes:
            stop(process)
        listener.close()
        log.close()


@pytest.fixture
def c0_server(server,tmp_path):
    from web.backend.tests.research_http_fixture import ResearchHTTPFixture
    provider=ResearchHTTPFixture(tmp_path/"c0-provider.sqlite3")
    server["stop"](server["process"])
    server["start"](c0_port=provider.port)
    try:yield server,provider
    finally:server["stop_all"]();provider.close()


def login(context, base, email="browser-a@example.test"):
    request = context.request.post(base + "/api/auth/request-link", data={"email":email}, headers={"Origin":base})
    assert request.status == 200, request.text()
    verified = context.request.post(base + "/api/auth/verify", data={"token":request.json()["dev_token"]}, headers={"Origin":base})
    assert verified.status == 200, verified.text()


def fill(page, text="午间合成排队现象：等待时间增加"):
    page.get_by_label("原始问题", exact=False).fill(text)
    page.get_by_label("希望解释或改变什么", exact=False).fill("希望缩短等待时间")
    page.get_by_label("问题摘要", exact=False).fill("合成排队问题的结构摘要与待确认因素")
    page.get_by_label("已知约束", exact=False).fill("本机合成数据")


def test_d1_page_preview_confirm_real_worker_and_private_mobile_records(server):
    from web.backend.tests.source_http_fixture import source_server
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with source_server() as (port,calls),sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport={"width":390,"height":844})
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            fill(page);page.locator("#confirmed").check();page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 1")
            expect(page.locator("#source-section")).to_be_visible()
            page.locator("#source-query").fill("queue theory");page.locator("#source-preview").click()
            expect(page.locator("#source-status")).to_contain_text("尚未开始读取")
            assert calls==[]
            page.locator("#source-confirm").click()
            expect(page.locator("#source-status")).to_contain_text("已排队")
            url=base+"/api"+page.url.split(base)[1]
            task=context.request.get(url).json()["data"]["task"]["id"]
            result=server["run_source_worker"](task,port)
            assert result.returncode==0,result.stderr
            assert result.stdout.strip()=="COMPLETED" and calls==["/discovery","/article"]
            page.locator("#source-refresh").click()
            expect(page.locator("#source-status")).to_contain_text("证据仍不足")
            expect(page.locator("#source-records article")).to_have_count(4)
            expect(page.locator("#task-budget")).to_contain_text("2 / 4")
            expect(page.locator("#original-input")).to_have_value("午间合成排队现象：等待时间增加")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            context.request.post(base+"/api/auth/logout",headers={"Origin":base})
            page.locator("#source-refresh").click()
            expect(page.locator("#source-section")).to_be_hidden()
            expect(page.locator("#source-records article")).to_have_count(0)
        finally:context.close();browser.close()


def test_d1_page_lost_start_receipt_reload_replays_original_key(server):
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            fill(page);page.locator("#confirmed").check();page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 1")
            page.locator("#source-query").fill("queue theory");page.locator("#source-preview").click()
            expect(page.locator("#source-confirm")).to_be_visible()
            def lose_receipt(route):
                response=route.fetch();assert response.status==200
                route.abort("failed")
            page.route("**/api/research/*/source-tasks",lose_receipt,times=1)
            page.locator("#source-confirm").click()
            expect(page.locator("#source-status")).to_contain_text(re.compile("fetch|Failed|失败",re.I))
            url=base+"/api"+page.url.split(base)[1]
            original=context.request.get(url).json()["data"]["task"]["id"]
            page.reload()
            expect(page.locator("#source-status")).to_contain_text("核对上次确认的原操作")
            assert context.request.get(url).json()["data"]["task"]["id"]==original
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_tasks").fetchone()[0]==1
                assert conn.execute("SELECT count(*) FROM research_source_approvals").fetchone()[0]==1
                assert conn.execute("SELECT count(*) FROM research_source_requests").fetchone()[0]==0
        finally:context.close();browser.close()


def _d1_page_with_records(server,context,port):
    base=server["base"];login(context,base)
    page=context.new_page();page.goto(base+"/research")
    fill(page);page.locator("#confirmed").check();page.locator("#save").click()
    expect(page.locator("#status")).to_contain_text("已保存修订 1")
    page.locator("#source-query").fill("queue theory");page.locator("#source-preview").click()
    expect(page.locator("#source-confirm")).to_be_visible();page.locator("#source-confirm").click()
    expect(page.locator("#source-status")).to_contain_text("已排队")
    url=base+"/api"+page.url.split(base)[1]
    tid=context.request.get(url).json()["data"]["task"]["id"]
    result=server["run_source_worker"](tid,port)
    assert result.returncode==0 and result.stdout.strip()=="COMPLETED",result.stderr
    page.locator("#source-refresh").click()
    expect(page.locator("#source-records article")).to_have_count(4)
    return page,url,tid


def test_d1_source_link_uses_public_canonical_url_without_provider_reference(server):
    from web.backend.tests.source_http_fixture import source_server
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with source_server() as (port,_),sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            page,url,tid=_d1_page_with_records(server,context,port)
            response=context.request.get(url+f"/records?task_id={tid}&kind=sources")
            assert response.status==200,response.text()
            source,=response.json()["data"]["items"]
            assert "provider_ref" not in source
            link=page.locator("#source-records article a")
            expect(link).to_have_attribute("href",source["canonical_url"])
            expect(link).to_have_text(source["canonical_url"])
        finally:context.close();browser.close()


def test_d1_task_switch_clears_old_cards_before_empty_new_records(server):
    from web.backend.tests.source_http_fixture import source_server
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with source_server() as (port,calls),sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            page,url,old=_d1_page_with_records(server,context,port)
            page.locator("#reload").click()
            expect(page.locator("#status")).to_contain_text("已从账户读取")
            expect(page.locator("#source-records article")).to_have_count(4)
            page.locator("#source-query").fill("queue theory");page.locator("#source-preview").click()
            expect(page.locator("#source-confirm")).to_be_visible();page.locator("#source-confirm").click()
            expect(page.locator("#source-status")).to_contain_text("已排队")
            expect(page.locator("#source-records article")).to_have_count(0)
            new=context.request.get(url).json()["data"]["task"]["id"]
            assert new!=old
            page.locator("#source-refresh").click()
            expect(page.locator("#source-status")).to_contain_text("尚无可展示")
            expect(page.locator("#source-records article")).to_have_count(0)
            assert calls==["/discovery","/article"]
        finally:context.close();browser.close()


def test_d1_input_switch_rejects_late_old_records_and_clears_cards(server):
    from web.backend.tests.source_http_fixture import source_server
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with source_server() as (port,_),sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            page,url,old=_d1_page_with_records(server,context,port)
            def hold(route):
                response=route.fetch();assert response.status==200 and response.json()["data"]["items"]
                held.append((route,response))
                page.evaluate("() => document.body.setAttribute('data-record-held','true')")
            page.route("**/api/research/*/records?*",hold,times=1)
            page.locator("#source-refresh").click()
            expect(page.locator("body")).to_have_attribute("data-record-held","true")
            page.locator("#original-input").fill("新修订的问题，不继承旧来源卡片")
            page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 2")
            expect(page.locator("#source-records article")).to_have_count(0)
            assert context.request.get(url).json()["data"]["task"] is None
            route,response=held.pop();route.fulfill(response=response)
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            expect(page.locator("#source-records article")).to_have_count(0)
            expect(page.locator("#original-input")).to_have_value("新修订的问题，不继承旧来源卡片")
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def test_d1_closed_unknown_keeps_original_observation_visible(server):
    from web.backend.tests.source_http_fixture import source_server
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with source_server() as (port,_),sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            fill(page);page.locator("#confirmed").check();page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 1")
            page.locator("#source-query").fill("queue theory");page.locator("#source-preview").click()
            expect(page.locator("#source-confirm")).to_be_visible();page.locator("#source-confirm").click()
            expect(page.locator("#source-status")).to_contain_text("已排队")
            url=base+"/api"+page.url.split(base)[1]
            tid=context.request.get(url).json()["data"]["task"]["id"]
            result=server["run_source_worker"](tid,port,drop=True)
            assert result.returncode==0 and result.stdout.strip()=="FAILED",result.stderr
            page.locator("#source-refresh").click()
            expect(page.locator("#task-budget")).to_contain_text("结果未知 1 次，其中执行已闭合 1 次")
            expect(page.locator("#task-message")).to_contain_text("原结果仍未知")
            actual=context.request.get(url).json()["data"]["source_observations"][0]
            expect(page.locator("#task-notes")).to_contain_text(actual["started_at"])
            expect(page.locator("#task-notes")).to_contain_text("未恢复旧结果")
        finally:context.close();browser.close()


def test_real_page_revisions_restart_private_access_and_mobile(server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width":375,"height":812})
        other = browser.new_context()
        try:
            base = server["base"]
            login(context, base)
            page = context.new_page()
            page.goto(base + "/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page, '<img src=x onerror="window.researchXss=true">合成问题')
            page.get_by_role("button", name="保存问题", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            saved_url = page.url
            assert "/research/" in saved_url and "?" not in saved_url
            page.get_by_label("原始问题", exact=False).fill("第二版合成研究问题")
            page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 2")
            assert page.locator("details").count() == 2
            assert not page.evaluate("Boolean(window.researchXss)")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            # Real application process restart, same disk DB and browser session.
            server["stop"](server["process"])
            server["start"]()
            page.goto(saved_url)
            expect(page.get_by_role("status")).to_contain_text("已从账户读取")
            expect(page.get_by_label("原始问题", exact=False)).to_have_value("第二版合成研究问题")
            page.locator("summary").last.click()
            expect(page.locator("pre").last).to_contain_text('<img src=x onerror="window.researchXss=true">')
            assert not page.evaluate("Boolean(window.researchXss)")
            page.screenshot(path=str(server["root"] / "research-mobile.png"), full_page=True)
            login(other, base, "browser-b@example.test")
            blocked = other.new_page()
            blocked.goto(saved_url)
            expect(blocked.get_by_role("status")).to_contain_text("不存在或当前无法访问")
            expect(blocked.locator("#problem-form")).to_be_hidden()
            assert "第二版合成研究问题" not in blocked.locator("body").inner_text()
            # Existing rendered content is cleared after current-session expiry.
            context.request.post(base + "/api/auth/logout", headers={"Origin":base})
            page.get_by_role("button", name="重新读取已存版本").click()
            expect(page.locator("#problem-form")).to_be_hidden()
            assert "第二版合成研究问题" not in page.locator("body").inner_text()
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0] == 2
        finally:
            context.close(); other.close(); browser.close()


def test_real_commit_lost_browser_receipt_reuses_original_key(server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        try:
            base = server["base"]
            login(context, base)
            page = context.new_page()
            page.goto(base + "/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page)
            calls = []

            def lose_receipt(route):
                # Execute the actual API and DB commit; drop only its browser
                # receipt. No canned response or substitute application logic.
                response = route.fetch()
                assert response.status == 200
                calls.append(route.request.headers["idempotency-key"])
                route.abort("failed")

            page.route("**/api/research", lose_receipt, times=1)
            page.get_by_role("button", name="保存问题", exact=True).click()
            expect(page.get_by_role("status")).to_have_attribute("data-error", "true")
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_controls").fetchone()[0] == 1
            with page.expect_request("**/api/research") as retried:
                page.get_by_role("button", name="保存问题", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            assert retried.value.headers["idempotency-key"] == calls[0]
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_controls").fetchone()[0] == 1
                assert conn.execute("SELECT count(*) FROM research_idempotency").fetchone()[0] == 1
            page.get_by_label("原始问题", exact=False).fill("回执丢失的第二版问题")
            # The same receipt-loss boundary also applies to revision writes.
            page.route("**/api/research/*/revisions", lose_receipt, times=1)
            page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_have_attribute("data-error", "true")
            page.get_by_role("button", name="重新读取已存版本").click()
            expect(page.get_by_role("status")).to_contain_text("已从账户读取")
            expect(page.locator("#revision-label")).to_have_text("当前修订 2")
            with page.expect_request("**/api/research/*/revisions") as retried_revision:
                page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 2")
            assert retried_revision.value.headers["idempotency-key"] == calls[1]
            assert retried_revision.value.post_data_json["data"]["expected_revision"] == 1
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0] == 2
        finally:
            context.close(); browser.close()


def test_nfc_pending_digest_reconciles_after_real_revision_commit_and_reopen(server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        try:
            base = server["base"]
            login(context, base)
            page = context.new_page()
            page.goto(base + "/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            original = "原始观察 cafe\u0301 必须保留分解字符"
            fill(page, original)
            page.get_by_label("希望解释或改变什么", exact=False).fill("观察 cafe\u0301 的等待时间")
            page.get_by_label("问题摘要", exact=False).fill("这是 cafe\u0301 结构问题的足够长摘要")
            page.get_by_label("已知约束", exact=False).fill("cafe\u0301 约束")
            page.get_by_label("还不知道什么", exact=False).fill("cafe\u0301 未知")
            page.get_by_role("button", name="保存问题", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            expect(page.get_by_label("原始问题", exact=False)).to_have_value(original)
            page.get_by_label("问题摘要", exact=False).fill("第二次 cafe\u0301 结构问题的足够长摘要")
            page.get_by_label("希望解释或改变什么", exact=False).fill("第二次 cafe\u0301 目标")
            page.get_by_label("已知约束", exact=False).fill("第二次 cafe\u0301 约束")
            page.get_by_label("还不知道什么", exact=False).fill("第二次 cafe\u0301 未知")
            lost_keys = []

            def lose_receipt(route):
                response = route.fetch()
                assert response.status == 200
                lost_keys.append(route.request.headers["idempotency-key"])
                route.abort("failed")

            page.route("**/api/research/*/revisions", lose_receipt, times=1)
            page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("保存结果尚未确认")
            for control in ("#original-input", "#objective", "#summary", "#constraints", "#unknowns", "#entry", "#confirmed"):
                expect(page.locator(control)).to_be_enabled()
            page.reload()
            expect(page.get_by_role("status")).to_contain_text("已从账户读取")
            expect(page.locator("#revision-label")).to_have_text("当前修订 2")
            expect(page.locator("#objective")).to_have_value("第二次 café 目标")
            expect(page.locator("#original-input")).to_have_value(original)
            with page.expect_request("**/api/research/*/revisions") as replay:
                page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 2")
            assert replay.value.headers["idempotency-key"] == lost_keys[0]
            assert replay.value.post_data_json["data"]["problem"]["original_input"] == original
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0] == 2
                latest = json.loads(conn.execute("SELECT problem_json FROM research_revisions WHERE revision=2").fetchone()[0])
                assert latest["original_input"] == original
                assert latest["objective"] == "第二次 café 目标"
                assert latest["constraints"] == ["第二次 café 约束"]
                assert latest["unknowns"] == ["第二次 café 未知"]
        finally:
            context.close(); browser.close()


def test_inflight_form_is_frozen_until_actual_commit_receipt_then_reenabled(server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        held = []
        try:
            base = server["base"]
            login(context, base)
            page = context.new_page()
            page.goto(base + "/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page, "提交中的原始合成问题")

            def hold_receipt(route):
                response = route.fetch()
                assert response.status == 200
                held.append((route, response))
                # A test boundary marker only: no application data/state is
                # injected. The real HTTP commit has already completed.
                page.evaluate("document.body.setAttribute('data-receipt-held', 'true')")

            page.route("**/api/research", hold_receipt, times=1)
            page.get_by_role("button", name="保存问题", exact=True).click()
            expect(page.locator("body")).to_have_attribute("data-receipt-held", "true")
            assert len(held) == 1
            expect(page.get_by_role("status")).to_contain_text("正在保存")
            for control in ("#original-input", "#objective", "#summary", "#constraints", "#unknowns", "#entry", "#confirmed", "#save", "#reload"):
                expect(page.locator(control)).to_be_disabled()
            assert page.locator("#problem-form input:enabled, #problem-form textarea:enabled, #problem-form select:enabled, #problem-form button:enabled").count() == 0
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_controls").fetchone()[0] == 1
            # User typing cannot alter a disabled submitted textarea.
            page.locator("#original-input").press("End")
            page.keyboard.type("不应悄悄成为待覆盖的新稿")
            expect(page.locator("#original-input")).to_have_value("提交中的原始合成问题")
            route, response = held.pop()
            route.fulfill(response=response)
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            for control in ("#original-input", "#objective", "#summary", "#constraints", "#unknowns", "#entry", "#confirmed"):
                expect(page.locator(control)).to_be_enabled()
            page.locator("#original-input").fill("收到回执后可以编辑的新稿")
            page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 2")
            expect(page.locator("#original-input")).to_have_value("收到回执后可以编辑的新稿")
            invalid_draft = "校验失败后仍应保留\u202e的新稿"
            page.locator("#original-input").fill(invalid_draft)
            page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_have_attribute("data-error", "true")
            expect(page.locator("#original-input")).to_be_enabled()
            expect(page.locator("#original-input")).to_have_value(invalid_draft)
            page.locator("#original-input").fill("修正后可以继续保存的新稿")
            page.get_by_role("button", name="保存为新修订", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 3")
        finally:
            for route, _ in held:
                route.abort()
            context.close(); browser.close()


def test_invalid_sso_poison_clears_previously_rendered_research(server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        try:
            base = server["base"]
            login(context, base)
            page = context.new_page()
            page.goto(base + "/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page, "不能在凭据失效后继续呈现的合成问题")
            page.get_by_role("button", name="保存问题", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            context.add_cookies([{"name":"structural_beta_session", "value":"invalid-synthetic-sso", "url":base}])
            page.get_by_role("button", name="重新读取已存版本").click()
            expect(page.locator("#problem-form")).to_be_hidden()
            expect(page.locator("#history")).to_be_hidden()
            assert "不能在凭据失效后继续呈现的合成问题" not in page.locator("body").inner_text()
        finally:
            context.close(); browser.close()


@pytest.mark.parametrize("outcome",["completed","pending","rejected","unknown"])
def test_account_delete_page_reports_actual_outcome_without_restore_promises(server,outcome):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch()
        context=browser.new_context()
        try:
            base=server["base"]
            login(context,base)
            created=context.request.post(base+"/api/research",headers={"Idempotency-Key":"ui-delete","Origin":base},data={
                "schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{"problem":{
                    "entry":"phenomenon","original_input":"UI-DELETE-SYNTHETIC-CANARY","objective":"目标",
                    "summary":"真实账户删除界面的合成问题记录","variables":[],"constraints":[],"unknowns":[],"confirmed":False,
                }},
            })
            assert created.status == 200,created.text()
            assert context.request.post(base+"/api/favorites/AAPL",headers={"Origin":base}).status == 201
            if outcome == "pending":
                server["stop"](server["process"])
                server["start"](fault="legacy-delete-failure")
            page=context.new_page()
            page.goto(base+"/reports")
            expect(page.locator("#myr-account")).to_contain_text("browser-a@example.test")
            expect(page.locator("#myr-list")).to_contain_text("还没有保存的报告")
            expect(page.locator("#myr-favorites")).to_contain_text("AAPL")
            page.get_by_text("永久删除账户与关联数据",exact=True).click()
            page.locator("#myr-delete-confirmation").fill("DELETE")
            if outcome == "rejected":
                assert context.request.post(base+"/api/auth/logout",headers={"Origin":base}).status == 200
            if outcome == "unknown":
                def lose_receipt(route):
                    response=route.fetch()
                    assert response.status == 200
                    route.abort("failed")
                page.route("**/api/me/delete",lose_receipt,times=1)
            page.locator("#myr-delete").click()
            if outcome == "completed":
                page.wait_for_url(base+"/?account=deleted")
                with sqlite3.connect(server["path"]) as conn:
                    assert conn.execute("SELECT state FROM auth_deletion_jobs").fetchone()[0] == "completed"
                    assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0] == 0
            elif outcome == "pending":
                expect(page.locator("#myr-account-status")).to_contain_text("访问已停止，清理尚未完成")
                expect(page.locator("#myr-delete")).to_be_disabled()
                expect(page.locator("#myr-export")).to_be_disabled()
                expect(page.locator("#myr-logout")).to_be_enabled()
                expect(page.locator("#research-favorites")).to_be_hidden()
                assert "AAPL" not in page.locator("body").inner_text()
                assert "job" not in page.locator("#myr-account-status").inner_text()
                with sqlite3.connect(server["path"]) as conn:
                    assert conn.execute("SELECT state FROM auth_deletion_jobs").fetchone()[0] == "pending"
                    assert conn.execute("SELECT lifecycle FROM auth_users").fetchone()[0] == "deleting"
                    assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0] == 0
                page.locator("#myr-logout").click()
                expect(page.locator("#myr-account")).to_contain_text("尚未登录")
                assert not any(cookie["name"] in {"phase_session","structural_beta_session"} for cookie in context.cookies())
            elif outcome == "rejected":
                expect(page.locator("#myr-account-status")).to_contain_text("本次删除请求未获准")
                expect(page.locator("#myr-delete")).to_be_enabled()
                with sqlite3.connect(server["path"]) as conn:
                    assert conn.execute("SELECT count(*) FROM auth_deletion_jobs").fetchone()[0] == 0
                    assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0] == 1
            else:
                expect(page.locator("#myr-account-status")).to_contain_text("删除结果尚未确认")
                expect(page.locator("#myr-delete")).to_be_disabled()
                expect(page.locator("#myr-export")).to_be_disabled()
                assert "账户与数据仍保留" not in page.locator("#myr-account-status").inner_text()
                with sqlite3.connect(server["path"]) as conn:
                    assert conn.execute("SELECT state FROM auth_deletion_jobs").fetchone()[0] == "completed"
        finally:
            context.close();browser.close()


def test_public_report_page_stops_showing_resource_during_pending_account_cleanup(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch()
        owner=browser.new_context()
        visitor=browser.new_context()
        try:
            base=server["base"]
            server["stop"](server["process"])
            seeded=server["start"](seed_owner_report=True)
            login(owner,base)
            with sqlite3.connect(server["root"]/"legacy-history.db") as conn:
                report_id,token,query=conn.execute("SELECT id,share_token,query FROM reports").fetchone()
            page=visitor.new_page()
            page.goto(base+"/report/share/"+token)
            expect(page.locator("#report-meta")).to_contain_text(query)
            server["stop"](seeded)
            server["start"](fault="legacy-delete-failure")
            failed=owner.request.post(base+"/api/me/delete",headers={"Origin":base},data={"confirmation":"DELETE"})
            assert failed.status == 500 and failed.json()["access_ended"] is True
            with sqlite3.connect(server["root"]/"legacy-history.db") as conn:
                assert conn.execute("SELECT share_token FROM reports WHERE id=?",(report_id,)).fetchone()[0] == token
            page.reload()
            expect(page.locator("#report-error")).to_be_visible()
            assert query not in page.locator("body").inner_text()
            feedback=visitor.request.post(base+f"/api/report/{report_id}/feedback",data={"section":None,"vote":1,"note":"BROWSER-AFTER-FENCE"})
            assert feedback.status == 404
            with sqlite3.connect(server["root"]/"legacy-history.db") as conn:
                assert conn.execute("SELECT count(*) FROM report_feedback WHERE note='BROWSER-AFTER-FENCE'").fetchone()[0] == 0
        finally:
            owner.close();visitor.close();browser.close()


def test_c0_page_real_task_worker_money_and_draft_survive_status_refresh(c0_server):
    server,provider=c0_server
    provider.note_override='<img src=x onerror="window.c0Xss=true"> 合成本机笔记，不是真实研究结论。'
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport={"width":375,"height":812})
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page,"已保存的C0演练问题")
            page.locator("#confirmed").check()
            page.locator("#save").click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            page.locator("#original-input").fill("尚未保存的草稿，不应被任务响应覆盖")
            page.locator("#task-start").click()
            expect(page.locator("#task-phase")).to_have_text("等待本机执行")
            expect(page.locator("#original-input")).to_have_value("尚未保存的草稿，不应被任务响应覆盖")
            saved_url=page.url
            data=context.request.get(base+"/api"+page.url.split(base)[1]).json()["data"]
            tid=data["task"]["id"]
            worker=server["run_worker"](tid)
            assert worker.returncode==0,worker.stderr
            assert worker.stdout.strip()=="COMPLETED"
            page.locator("#task-refresh").click()
            expect(page.locator("#task-phase")).to_contain_text("尚无真实研究结论")
            expect(page.locator("#task-budget")).to_contain_text("USD 0.007000")
            expect(page.locator("#task-budget")).to_contain_text("USD 0.000000")
            expect(page.locator("#original-input")).to_have_value("尚未保存的草稿，不应被任务响应覆盖")
            assert page.locator("#task-notes pre").count()==2
            expect(page.locator("#task-notes pre").first).to_contain_text('<img src=x')
            assert page.evaluate("Boolean(window.c0Xss)") is False
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            server["stop_all"]();server["start"](c0_port=provider.port)
            page.goto(saved_url)
            expect(page.locator("#task-phase")).to_contain_text("尚无真实研究结论")
            expect(page.locator("#task-budget")).to_contain_text("USD 0.007000")
            assert server["run_worker"](tid).stdout.strip()=="COMPLETED" and provider.count()==2
            page.screenshot(path=str(server["root"]/"c0-mobile.png"),full_page=True)
        finally:context.close();browser.close()


def test_c0_page_cancel_unknown_reconcile_never_restarts_task(c0_server):
    server,provider=c0_server
    provider.drop.add("discover_sources")
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page);page.locator("#confirmed").check();page.locator("#save").click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            page.locator("#task-start").click()
            expect(page.locator("#task-phase")).to_contain_text("等待本机执行")
            data=context.request.get(base+"/api"+page.url.split(base)[1]).json()["data"];tid=data["task"]["id"]
            assert server["run_worker"](tid).stdout.strip()=="RECONCILING"
            page.locator("#task-refresh").click()
            expect(page.locator("#task-message")).to_contain_text("预留保持占用")
            expect(page.locator("#task-budget")).to_contain_text("USD 0.007000")
            page.locator("#task-cancel").click()
            expect(page.locator("#task-phase")).to_have_text("已停止后续步骤")
            expect(page.locator("#task-budget")).to_contain_text("USD 0.007000")
            page.locator("#task-reconcile").click()
            assert server["run_worker"](tid).stdout.strip()=="CANCELLED"
            page.locator("#task-refresh").click()
            expect(page.locator("#task-budget")).to_contain_text("USD 0.004000")
            expect(page.locator("#task-budget")).to_contain_text("USD 0.000000")
            expect(page.locator("#task-phase")).to_have_text("已停止后续步骤")
            assert page.locator("#task-notes pre").count()==0 and provider.count()==1
        finally:context.close();browser.close()


def test_late_task_start_receipt_does_not_rebind_newer_saved_problem(c0_server):
    server,provider=c0_server
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page);page.locator("#confirmed").check();page.locator("#save").click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            def hold(route):
                response=route.fetch();assert response.status==200
                held.append((route,response))
                page.evaluate("document.body.setAttribute('data-task-receipt-held','true')")
            page.route("**/api/research/*/tasks",hold,times=1)
            page.locator("#task-start").click()
            expect(page.locator("body")).to_have_attribute("data-task-receipt-held","true")
            page.locator("#original-input").fill("启动旧修订期间保存的新问题")
            page.locator("#save").click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 2")
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator("#task-message")).to_contain_text("当前问题保持不变")
            expect(page.locator("#revision-label")).to_have_text("当前修订 2")
            expect(page.locator("#original-input")).to_have_value("启动旧修订期间保存的新问题")
            expect(page.locator("#task-other")).to_be_visible()
            page.locator("#task-other").click()
            expect(page.locator("#task-phase")).to_have_text("等待本机执行")
            expect(page.locator("#original-input")).to_be_disabled()
            assert provider.count()==0
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def _two_window_revision_fixture(context,base):
    login(context,base)
    first=context.new_page();first.goto(base+"/research")
    expect(first.get_by_role("status")).to_contain_text("尚未保存")
    fill(first,"窗口A载入的原问题")
    first.locator("#confirmed").check();first.locator("#save").click()
    expect(first.get_by_role("status")).to_contain_text("已保存修订 1")
    second=context.new_page();second.goto(first.url)
    expect(second.locator("#revision-label")).to_have_text("当前修订 1")
    first.locator("#original-input").fill("窗口A未保存的草稿")
    second.locator("#original-input").fill("窗口B已保存的最新问题")
    second.locator("#save").click()
    expect(second.get_by_role("status")).to_contain_text("已保存修订 2")
    first.locator("#task-refresh").click()
    expect(first.get_by_role("status")).to_contain_text("表单仍基于修订 1")
    expect(first.locator("#revision-label")).to_have_text("当前修订 1")
    expect(first.locator("#original-input")).to_have_value("窗口A未保存的草稿")
    return first,second


def test_task_refresh_never_rebases_other_window_save_base(c0_server):
    server,provider=c0_server
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];page,_=_two_window_revision_fixture(context,base)
            with page.expect_request("**/api/research/*/revisions") as saving, page.expect_response("**/api/research/*/revisions") as response:
                page.locator("#save").click()
            assert saving.value.post_data_json["data"]["expected_revision"]==1
            assert response.value.status==409
            expect(page.locator("#original-input")).to_have_value("窗口A未保存的草稿")
            data=context.request.get(base+"/api"+page.url.split(base)[1]).json()["data"]
            assert len(data["revisions"])==2 and data["current_problem"]["original_input"]=="窗口B已保存的最新问题"
            page.locator("#reload").click()
            expect(page.locator("#revision-label")).to_have_text("当前修订 2")
            expect(page.locator("#original-input")).to_have_value("窗口B已保存的最新问题")
            page.locator("#original-input").fill("明确载入修订2后保存的新稿")
            with page.expect_request("**/api/research/*/revisions") as accepted:
                page.locator("#save").click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 3")
            assert accepted.value.post_data_json["data"]["expected_revision"]==2
            assert provider.count()==0
        finally:context.close();browser.close()


def test_task_refresh_never_rebases_other_window_run_base(c0_server):
    server,provider=c0_server
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];page,_=_two_window_revision_fixture(context,base)
            with page.expect_request("**/api/research/*/tasks") as starting,page.expect_response("**/api/research/*/tasks") as response:
                page.locator("#task-start").click()
            assert starting.value.post_data_json["data"]=={"input_revision":1,"expected_research_version":1,"mode":"research"}
            assert response.value.status==409
            expect(page.locator("#task-message")).to_contain_text("明确载入最新修订")
            expect(page.locator("#original-input")).to_have_value("窗口A未保存的草稿")
            data=context.request.get(base+"/api"+page.url.split(base)[1]).json()["data"]
            assert data["task"] is None and len(data["revisions"])==2
            page.locator("#reload").click()
            expect(page.locator("#revision-label")).to_have_text("当前修订 2")
            with page.expect_request("**/api/research/*/tasks") as accepted:
                page.locator("#task-start").click()
            expect(page.locator("#task-phase")).to_have_text("等待本机执行")
            assert accepted.value.post_data_json["data"]=={"input_revision":2,"expected_research_version":2,"mode":"research"}
            data=context.request.get(base+"/api"+page.url.split(base)[1]).json()["data"]
            assert data["task"]["input_revision"]==2 and provider.count()==0
        finally:context.close();browser.close()


def test_late_cancel_receipt_cannot_replace_newer_same_revision_task(c0_server):
    server,provider=c0_server
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            expect(page.get_by_role("status")).to_contain_text("尚未保存")
            fill(page);page.locator("#confirmed").check();page.locator("#save").click()
            expect(page.get_by_role("status")).to_contain_text("已保存修订 1")
            page.locator("#task-start").click()
            expect(page.locator("#task-phase")).to_have_text("等待本机执行")
            url=base+"/api"+page.url.split(base)[1]
            one=context.request.get(url).json()["data"]["task"]["id"]
            def hold(route):
                response=route.fetch();assert response.status==200
                held.append((route,response))
                page.evaluate("document.body.setAttribute('data-cancel-receipt-held','true')")
            page.route("**/api/research/*/cancel",hold,times=1)
            page.locator("#task-cancel").click()
            expect(page.locator("body")).to_have_attribute("data-cancel-receipt-held","true")
            actual=context.request.get(url).json()["data"]
            assert actual["execution"]=="CANCELLED"
            new=context.request.post(url+"/tasks",headers={"Origin":base,"Idempotency-Key":"legitimate-next-task"},data={"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{"input_revision":1,"expected_research_version":actual["research_version"],"mode":"research"}})
            assert new.status==200,new.text()
            two=new.json()["data"]["task"]["id"];assert two!=one
            with page.expect_response(url) as refreshed:
                page.locator("#reload").click()
            assert refreshed.value.json()["data"]["task"]["id"]==two
            expect(page.get_by_role("status")).to_contain_text("已从账户读取")
            expect(page.locator("#task-phase")).to_have_text("等待本机执行")
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator("#task-message")).to_contain_text("当前问题保持不变")
            expect(page.locator("#task-phase")).to_have_text("等待本机执行")
            expect(page.locator("#task-cancel")).to_be_visible()
            expect(page.locator("#task-cancel")).to_be_enabled()
            assert context.request.get(url).json()["data"]["task"]["id"]==two
            with page.expect_request("**/api/research/*/cancel") as stopping:
                page.locator("#task-cancel").click()
            expect(page.locator("#task-phase")).to_have_text("已停止后续步骤")
            assert stopping.value.post_data_json["data"]["task_id"]==two
            assert provider.count()==0
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


# Research-entry coverage uses the real mounted API/auth/SQLite. Only the
# unrelated KB endpoint is replaced in these tests; this proves UI handling,
# never KB retrieval quality. Held research receipts always come from route.fetch.
def _entry_create(context, base, number):
    from uuid import uuid4
    problem = {"entry":"phenomenon", "original_input":f"真实保存流程使用的合成现象 {number}",
               "objective":"验证保存和恢复，不构成真实研究", "summary":f"列表研究 {number} 的合成问题摘要",
               "variables":[], "constraints":[], "unknowns":[], "confirmed":True}
    response = context.request.post(base+"/api/research", headers={"Origin":base,"Idempotency-Key":str(uuid4())},
                                    data={"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{"problem":problem}})
    assert response.status == 200, response.text()
    return response.json()["data"]


def test_entry_original_draft_kb_and_real_saved_source_chain(server):
    from web.backend.tests.source_http_fixture import source_server
    server["stop"](server["process"]); server["start"](d1_sources=True)
    with source_server() as (port, calls), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width":430,"height":900})
        try:
            base=server["base"]; login(context,base)
            page=context.new_page(); seen=[]
            def kb(route):
                seen.append(route.request.post_data_json)
                route.fulfill(json={"results":[{"id":"queue","name":"合成排队线索","domain":"运筹","description":"变量映射尚待核验","score":.99,"relevance":.99}]})
            page.route("**/api/search", kb)
            page.goto(base+"/research")
            expect(page.locator("#problem-form")).to_be_visible()
            expect(page.locator("#research-list-status")).to_contain_text("还没有")
            original="午间窗口等待时间逐渐增加，需要解释这个现象"
            page.locator("#original-input").fill(original)
            expect(page.locator("#summary")).to_have_value(original)
            expect(page.locator("#confirmed")).not_to_be_checked()
            long_original="长"*1001
            page.locator("#original-input").fill(long_original)
            expect(page.locator("#summary")).to_have_value("")
            expect(page.locator("#summary-hint")).to_contain_text("不会截断")
            expect(page.locator("#original-input")).to_have_value(long_original)
            page.locator("#summary").fill("用户自行填写的摘要不会被后续原文覆盖")
            page.locator("#original-input").fill(original)
            expect(page.locator("#summary")).to_have_value("用户自行填写的摘要不会被后续原文覆盖")
            assert seen==[] and calls==[]
            page.locator("#objective").fill("缩短等待；私有目标不进入来源查询")
            before=page.locator("#problem-form").evaluate("f=>Array.from(f.querySelectorAll('textarea,select')).map(e=>[e.id,e.value])")
            page.locator("#kb-search").click()
            expect(page.locator("#kb-results article")).to_have_count(1)
            assert seen==[{"query":original,"top_k":12,"rewrite":False,"lang":"zh"}]
            assert page.locator("#problem-form").evaluate("f=>Array.from(f.querySelectorAll('textarea,select')).map(e=>[e.id,e.value])")==before
            assert "99%" not in page.locator("#kb-results").inner_text()
            expect(page.locator("#kb-status")).to_contain_text("待核验")
            page.locator("#confirmed").check(); page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 1")
            expect(page.locator("#research-list-items a")).to_have_count(1)
            link=page.locator("#research-list-items a")
            assert link.get_attribute("target")=="_blank" and "noopener" in link.get_attribute("rel")
            with context.expect_page() as opened: link.click()
            reopened=opened.value
            expect(reopened.locator("#original-input")).to_have_value(original)
            assert reopened.evaluate("window.opener===null")
            reopened.close()
            page.locator("#source-query").fill("queue theory")
            with page.expect_request("**/source-preview") as preview: page.locator("#source-preview").click()
            expect(page.locator("#source-status")).to_contain_text("尚未开始读取")
            assert preview.value.post_data_json["data"]["query"]=="queue theory" and calls==[]
            expect(page.locator("#source-plan")).to_contain_text("最多读取 4 次 GET")
            assert original not in page.locator("#source-plan").inner_text()
            plan=page.locator("#source-plan").inner_text()
            page.locator("#research-list-refresh").click()
            expect(page.locator("#research-list-status")).to_contain_text("已读取 1")
            expect(page.locator("#source-plan")).to_have_text(plan)
            expect(page.locator("#source-confirm")).to_be_visible()
            assert calls==[]
            page.locator("#source-confirm").click()
            expect(page.locator("#source-status")).to_contain_text("已排队")
            task=context.request.get(base+"/api"+page.url.split(base)[1]).json()["data"]["task"]["id"]
            worker=server["run_source_worker"](task,port)
            assert worker.returncode==0 and worker.stdout.strip()=="COMPLETED" and calls==["/discovery","/article"]
            page.locator("#source-refresh").click()
            expect(page.locator("#source-records article")).to_have_count(4)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            for selector in ("#kb-search","#save","#research-list-refresh","#research-list-items a","#source-preview"):
                assert page.locator(selector).first.bounding_box()["height"]>=44
            page.locator("#kb-search").focus()
            assert page.locator("#kb-search").evaluate("e=>document.activeElement===e")
            page.screenshot(path=str(server["root"] / "entry-mobile.png"),full_page=True)
        finally: context.close(); browser.close()


def test_entry_kb_input_generations_and_revocation_reject_late_results(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(); context=browser.new_context(); held=[]
        try:
            base=server["base"]; login(context,base)
            page=context.new_page(); page.goto(base+"/research")
            expect(page.locator("#problem-form")).to_be_visible()
            def kb(route):
                if route.request.post_data_json["query"]=="现象 A 的旧请求需要延迟": held.append(route)
                else: route.fulfill(json={"results":[{"name":"现象 B 的新线索","domain":"本地","description":"仅界面合成数据"}]})
            page.route("**/api/search",kb)
            page.locator("#original-input").fill("现象 A 的旧请求需要延迟"); page.locator("#kb-search").click()
            page.wait_for_function("document.querySelector('#kb-search').disabled")
            # Let Playwright receive the outbound request before changing input.
            page.wait_for_timeout(100)
            assert len(held)==1
            page.locator("#original-input").fill("现象 B 的当前输入保持不变"); page.locator("#kb-search").click()
            expect(page.locator("#kb-results")).to_contain_text("现象 B")
            held.pop().fulfill(json={"results":[{"name":"现象 A 旧线索不得出现"}]})
            expect(page.locator("#kb-results")).to_contain_text("现象 B")
            assert "现象 A" not in page.locator("#kb-results").inner_text()
            page.locator("#original-input").fill("现象 A 的旧请求需要延迟"); page.locator("#kb-search").click()
            page.wait_for_timeout(100); assert len(held)==1
            context.request.post(base+"/api/auth/logout",headers={"Origin":base})
            page.locator("#research-list-refresh").click()
            expect(page.locator("#problem-form")).to_be_hidden()
            expect(page.locator("#my-research")).to_be_hidden()
            held.pop().fulfill(json={"results":[{"name":"撤权后禁止复现的线索"}]})
            expect(page.locator("#kb-results article")).to_have_count(0)
            assert "撤权后禁止复现" not in page.locator("body").inner_text()
        finally:
            for route in held: route.abort()
            context.close(); browser.close()


def test_entry_index_real_pagination_invalid_cursor_and_late_receipt(server):
    from uuid import uuid4
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(); context=browser.new_context(); held=[]
        try:
            base=server["base"]; login(context,base)
            for number in range(22): _entry_create(context,base,number)
            page=context.new_page(); page.goto(base+"/research")
            expect(page.locator("#research-list-items article")).to_have_count(20)
            page.locator("#original-input").fill("当前尚未保存的问题，分页必须完整保留")
            page.locator("#summary").fill("分页不应改写的自定义摘要")
            before=page.locator("#original-input").input_value()
            with page.expect_response(re.compile(r"/api/research\?limit=20&cursor=")) as next_page:
                page.locator("#research-list-more").click()
            assert next_page.value.status==200 and next_page.value.json()["data"]["next_cursor"] is None
            expect(page.locator("#research-list-items article")).to_have_count(22)
            expect(page.locator("#original-input")).to_have_value(before)
            page.locator("#research-list-refresh").click()
            expect(page.locator("#research-list-items article")).to_have_count(20)
            anchor_href=page.locator("#research-list-items a").last.get_attribute("href")
            anchor=context.request.get(base+"/api"+anchor_href).json()["data"]
            problem=dict(anchor["current_problem"])
            problem={key:problem[key] for key in ("entry","original_input","objective","summary","variables","constraints","unknowns","confirmed")}
            problem["summary"]="分页锚点实际被修改，原游标应失效"
            changed=context.request.post(base+"/api"+anchor_href+"/revisions",headers={"Origin":base,"Idempotency-Key":str(uuid4())},data={"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{"expected_revision":anchor["current_problem"]["revision"],"problem":problem}})
            assert changed.status==200,changed.text()
            page.locator("#research-list-more").click()
            expect(page.locator("#research-list-status")).to_contain_text("分页位置失效")
            expect(page.locator("#research-list-items article")).to_have_count(0)
            expect(page.locator("#original-input")).to_have_value(before)
            page.locator("#research-list-refresh").click()
            expect(page.locator("#research-list-items article")).to_have_count(20)
            def hold_page(route):
                response=route.fetch(); assert response.status==200
                held.append((route,response))
            page.route("**/api/research?limit=20&cursor=*",hold_page,times=1)
            page.locator("#research-list-more").click()
            page.wait_for_timeout(100); assert len(held)==1
            page.locator("#research-list-refresh").click()
            expect(page.locator("#research-list-items article")).to_have_count(20)
            expect(page.locator("#research-list-status")).to_contain_text("已读取 20")
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator("#research-list-items article")).to_have_count(20)
            expect(page.locator("#summary")).to_have_value("分页不应改写的自定义摘要")
        finally:
            for route,_ in held: route.abort()
            context.close(); browser.close()


def test_entry_list_reopen_preserves_unknown_save_and_late_auth_list(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=server["base"];login(context,base)
            _entry_create(context,base,"先前研究")
            page=context.new_page();page.goto(base+"/research")
            expect(page.locator("#research-list-items article")).to_have_count(1)
            fill(page,"保存回执未知时仍需保留完整原始输入")
            keys=[]
            def lose(route):
                response=route.fetch(); assert response.status==200
                keys.append(route.request.headers["idempotency-key"]);route.abort("failed")
            page.route("**/api/research",lose,times=1)
            page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("尚未确认")
            pending=page.evaluate("sessionStorage.getItem('structure-research-pending:new')")
            page.locator("#research-list-refresh").click()
            expect(page.locator("#research-list-items article")).to_have_count(2)
            with context.expect_page() as reopened:page.locator("#research-list-items a").first.click()
            expect(reopened.value.locator("#problem-form")).to_be_visible()
            reopened.value.close()
            expect(page.locator("#original-input")).to_have_value("保存回执未知时仍需保留完整原始输入")
            assert page.evaluate("sessionStorage.getItem('structure-research-pending:new')")==pending
            with page.expect_request("**/api/research") as replay:page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 1")
            assert replay.value.headers["idempotency-key"]==keys[0]
            with sqlite3.connect(server["path"]) as conn:assert conn.execute("SELECT count(*) FROM research_controls").fetchone()[0]==2
            expect(page.locator("#research-list-status")).to_contain_text("已读取 2")
            def hold_index(route):
                response=route.fetch();assert response.status==200
                held.append((route,response))
            page.route("**/api/research?limit=20",hold_index,times=1)
            page.locator("#research-list-refresh").click()
            page.wait_for_timeout(100);assert len(held)==1
            context.request.post(base+"/api/auth/logout",headers={"Origin":base})
            page.locator("#reload").click()
            expect(page.locator("#problem-form")).to_be_hidden()
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator("#research-list-items article")).to_have_count(0)
            expect(page.locator("#my-research")).to_be_hidden()
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def test_entry_kb_unavailable_is_honest_and_account_switch_clears_private_view(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];login(context,base)
            _entry_create(context,base,"账户 A")
            page=context.new_page();page.goto(base+"/research")
            expect(page.locator("#research-list-items article")).to_have_count(1)
            page.locator("#original-input").fill("不应启动收费兜底的原始现象")
            page.route("**/api/search",lambda route:route.fulfill(status=503,json={"detail":{"code":"FEATURE_DISABLED","message":"<img src=x onerror=alert(1)>"}}))
            page.locator("#kb-search").click()
            expect(page.locator("#kb-status")).to_contain_text("未启动模型或收费研究")
            expect(page.locator("#original-input")).to_have_value("不应启动收费兜底的原始现象")
            assert "<img" not in page.locator("#kb-status").inner_text()
            login(context,base,"browser-b@example.test")
            page.locator("#research-list-refresh").click()
            expect(page.locator("#problem-form")).to_be_hidden()
            expect(page.locator("#research-list-items article")).to_have_count(0)
            expect(page.locator("#status")).to_contain_text("账户已变化")
        finally:context.close();browser.close()


def test_entry_changed_source_query_rejects_held_real_preview(server):
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=server["base"];login(context,base)
            page=context.new_page();page.goto(base+"/research")
            fill(page);page.locator("#confirmed").check();page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 1")
            def hold(route):
                response=route.fetch();assert response.status==200
                held.append((route,response))
            page.route("**/source-preview",hold,times=1)
            page.locator("#source-query").fill("queue theory")
            page.locator("#source-preview").click()
            page.wait_for_timeout(100);assert len(held)==1
            page.locator("#source-query").fill("network theory")
            route,response=held.pop()
            with page.expect_response("**/source-preview"):route.fulfill(response=response)
            expect(page.locator("#source-preview")).to_be_enabled()
            expect(page.locator("#source-plan")).to_have_text("")
            expect(page.locator("#source-confirm")).to_be_hidden()
            page.locator("#source-preview").click()
            expect(page.locator("#source-plan")).to_contain_text("network theory")
            assert "queue theory" not in page.locator("#source-plan").inner_text()
            assert context.request.get(base+"/api"+page.url.split(base)[1]).json()["data"]["task"] is None
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


@pytest.mark.parametrize("fault,action",[
    ("503","list"),("503","kb"),("503","reload"),
    ("500","list"),("403","list"),("404","list"),("409","list"),
    ("network","list"),("bad-json","list"),("bad-user","list"),("ok-false","list"),
])
def test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain(server,fault,action):
    """Fault only one /auth/me receipt; auth, commits and recovery stay real."""
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];login(context,base)
            saved=_entry_create(context,base,"账户暂时无法核对的对照")
            research=saved["research"]["id"]
            page=context.new_page();page.goto(base+"/research/"+research)
            expect(page.locator("#research-list-status")).to_contain_text("已读取 1")
            fill(page,"暂时核对失败时必须完整保留的未确认提交原文")
            page.locator("#summary").fill("人工编辑的摘要不能因服务暂时不可用而销毁")
            page.locator("#confirmed").check()
            page.locator("#source-query").fill("queue theory")
            keys=[]
            def lose_commit_receipt(route):
                response=route.fetch();assert response.status==200
                keys.append(route.request.headers["idempotency-key"])
                route.abort("failed")
            page.route("**/api/research/*/revisions",lose_commit_receipt,times=1)
            page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("尚未确认")
            snapshot=page.locator("#problem-form").evaluate("f=>Array.from(f.querySelectorAll('input,textarea,select')).map(e=>[e.id,e.value,e.checked])")
            slot="structure-research-pending:"+research
            pending=page.evaluate("slot=>sessionStorage.getItem(slot)",slot)
            assert json.loads(pending)["key"]==keys[0]
            private_calls=[];checks=[]
            def observe(request):
                path=request.url.split(base)[-1]
                if path=="/api/auth/me":checks.append(path)
                elif path.startswith(("/api/search","/api/research")):private_calls.append(path)
            page.on("request",observe)
            def fail_auth_receipt(route):
                real=route.fetch();assert real.status==200
                if fault=="network":route.abort("failed")
                elif fault=="bad-json":route.fulfill(status=200,content_type="application/json",body="{")
                elif fault=="bad-user":route.fulfill(json={"ok":True,"user":{"email":"browser-a@example.test","created_at":{}}})
                elif fault=="ok-false":route.fulfill(json={"ok":False,"user":{"email":"browser-a@example.test","created_at":"invalid-placeholder"}})
                else:route.fulfill(status=int(fault),json={"ok":False,"error":"auth unavailable"})
            page.route("**/api/auth/me",fail_auth_receipt,times=1)
            page.locator({"list":"#research-list-refresh","kb":"#kb-search","reload":"#reload"}[action]).click()
            expect(page.locator("#status")).to_contain_text("账户状态暂时无法核对")
            expect(page.locator("#problem-form")).to_be_visible()
            expect(page.locator("#save")).to_be_enabled()
            assert page.locator("#problem-form").evaluate("f=>Array.from(f.querySelectorAll('input,textarea,select')).map(e=>[e.id,e.value,e.checked])")==snapshot
            expect(page.locator("#source-query")).to_have_value("queue theory")
            assert page.evaluate("slot=>sessionStorage.getItem(slot)",slot)==pending
            page.wait_for_timeout(80)
            assert private_calls==[] and len(checks)==1
            # The same canonical session is valid; no retry occurred until the
            # test explicitly asks for recovery, including the original key.
            assert context.request.get(base+"/api/auth/me").status==200
            page.locator("#research-list-refresh").click()
            expect(page.locator("#research-list-status")).to_contain_text("已读取 1")
            assert page.evaluate("slot=>sessionStorage.getItem(slot)",slot)==pending
            with page.expect_request("**/api/research/*/revisions") as replay:page.locator("#save").click()
            expect(page.locator("#status")).to_contain_text("已保存修订 2")
            assert replay.value.headers["idempotency-key"]==keys[0]
            with sqlite3.connect(server["path"]) as conn:
                assert conn.execute("SELECT count(*) FROM research_revisions WHERE research_id=?",(research,)).fetchone()[0]==2
        finally:context.close();browser.close()


def test_entry_auth_real_401_clears_private_draft_and_stops_chain(server):
    server["stop"](server["process"]);server["start"](d1_sources=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server["base"];login(context,base)
            saved=_entry_create(context,base,"真实失权清理对照")
            page=context.new_page();page.goto(base+"/research/"+saved["research"]["id"])
            expect(page.locator("#research-list-status")).to_contain_text("已读取 1")
            page.locator("#source-query").fill("queue theory");page.locator("#source-preview").click()
            expect(page.locator("#source-confirm")).to_be_visible()
            fill(page,"真实失权后不能继续展示的私有原文")
            page.locator("#summary").fill("真实失权后需要清空的人工摘要")
            context.request.post(base+"/api/auth/logout",headers={"Origin":base})
            assert context.request.get(base+"/api/auth/me").status==401
            calls=[]
            page.on("request",lambda request:calls.append(request.url) if request.url.startswith((base+"/api/research",base+"/api/search")) else None)
            page.locator("#research-list-refresh").click()
            expect(page.locator("#status")).to_contain_text("账户访问已失效")
            expect(page.locator("#problem-form")).to_be_hidden()
            expect(page.locator("#original-input")).to_have_value("")
            expect(page.locator("#summary")).to_have_value("")
            expect(page.locator("#confirmed")).not_to_be_checked()
            expect(page.locator("#source-plan")).to_have_text("")
            expect(page.locator("#research-list-items article")).to_have_count(0)
            expect(page.locator("#kb-results article")).to_have_count(0)
            assert calls==[]
        finally:context.close();browser.close()
