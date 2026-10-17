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


@pytest.mark.parametrize('viewport',[{'width':1280,'height':900},{'width':430,'height':932}])
def test_source_reopen_explains_explicit_read_without_losing_draft_or_refetching_provider(server,viewport):
    """Real auth/store/Source worker; only Source transport uses the loopback fixture."""
    from urllib.parse import urlsplit
    from web.backend.tests.source_http_fixture import source_server
    server['stop'](server['process']);server['start'](d1_sources=True)
    with source_server() as (port,calls),sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport=viewport)
        try:
            base=server['base'];login(context,base)
            page=context.new_page();page.goto(base+'/research')
            fill(page);page.locator('#confirmed').check();page.locator('#save').click()
            expect(page.locator('#status')).to_contain_text('已保存修订 1')
            page.locator('#source-query').fill('queue theory');page.locator('#source-preview').click()
            expect(page.locator('#source-confirm')).to_be_visible()
            expect(page.locator('#source-status')).to_contain_text('预览完成')
            expect(page.locator('#source-reopen-hint')).to_be_visible()
            expect(page.locator('#source-plan')).to_contain_text('queue theory')
            assert page.locator('#source-reopen-hint').get_attribute('role') is None and calls==[]
            page.locator('#source-confirm').click()
            expect(page.locator('#source-status')).to_contain_text('已排队')
            view=base+'/api'+urlsplit(page.url).path
            task=context.request.get(view).json()['data']['task']['id']
            worker=server['run_source_worker'](task,port)
            assert worker.returncode==0 and worker.stdout.strip()=='COMPLETED'
            assert calls==['/discovery','/article']
            page.locator('#source-refresh').click()
            expect(page.locator('#source-records article')).to_have_count(4)
            with sqlite3.connect(server['path']) as conn:
                before=conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]
            requests=[]
            page.on('request',lambda request:requests.append((request.method,urlsplit(request.url).path)))
            page.reload()
            expect(page.locator('#task-phase')).to_contain_text('来源整理结束')
            expect(page.locator('#source-records article')).to_have_count(0)
            expect(page.locator('#source-status')).to_have_text('')
            expect(page.locator('#source-reopen-hint')).to_contain_text('尚未读取不代表没有记录')
            button=page.get_by_role('button',name='核对并读取已保存来源笔记',exact=True)
            expect(button).to_be_visible()
            expect(button).to_have_attribute('aria-describedby','source-reopen-hint')
            assert not any('/records' in path or method=='POST' for method,path in requests)
            page.locator('#original-input').fill('重开之后手写且尚未保存的新现象输入')
            page.locator('#summary').fill('重开之后手写且尚未保存的摘要需要保留')
            page.locator('#confirmed').uncheck()
            button.focus();page.keyboard.press('Enter')
            expect(page.locator('#source-records article')).to_have_count(4)
            assert set(page.locator('#source-records h3').all_text_contents())=={'来源','短摘录','待验证判断','研究缺口'}
            expect(page.locator('#source-status')).to_contain_text('已从账户读取来源与笔记')
            expect(page.locator('#original-input')).to_have_value('重开之后手写且尚未保存的新现象输入')
            expect(page.locator('#summary')).to_have_value('重开之后手写且尚未保存的摘要需要保留')
            expect(page.locator('#confirmed')).not_to_be_checked()
            assert calls==['/discovery','/article']
            assert context.request.get(view).json()['data']['task']['id']==task
            assert not any(method=='POST' for method,_path in requests)
            with sqlite3.connect(server['path']) as conn:
                assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==before
            assert button.bounding_box()['height']>=44
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(server['root'] / 'source-reopen-explicit-read.png'),full_page=True)
        finally:context.close();browser.close()


_METHOD_SEED = r'''
import json,sys
from pathlib import Path
from contextlib import ExitStack,contextmanager
from types import SimpleNamespace
import pytest
from web.backend.tests.test_research_persistence import stack,post
from web.backend.tests.test_research_d1_integration import source_stack
from web.backend.tests.test_research_paid_approval import approved_inputs
from web.backend.tests.test_research_paid_api import paid_api,make_preview,confirm_data
from web.backend.tests.test_research_paid_budget_loop import execution
from web.backend.tests.test_research_owned_return import response_body,tcp_reply
from research.authorization import AuthorizationGate
from research.paid_provider_session import persist_budget_return,BudgetedOwnedSession
root=Path(sys.argv[1]);output=Path(sys.argv[2]);kind=sys.argv[3];root.mkdir(exist_ok=True)
with ExitStack() as scope:
    patch=pytest.MonkeyPatch();scope.callback(patch.undo)
    def enter(fixture,*args):return scope.enter_context(contextmanager(fixture.__wrapped__)(*args))
    if kind.startswith('history'):
        from web.backend.tests import test_research_d1_integration as source_fixture
        original_problem=source_fixture.problem
        def full_problem():
            value=original_problem('原始现象 e\u0301 😀\n原来的第二行，保留原文。'+('原始长问题的每一句都需要保留。'*120))
            value.update(objective='原来的研究目标',summary='历史种子的原问题摘要与真实保存链',constraints=['原约束一','原约束二'],unknowns=['原来的未知'],
                variables=[{'id':'arrival','label':'原到达数量','role':'input','unit_id':'count','observation':'原观测 e\u0301','provenance':'user_observed'},
                           {'id':'service','label':'原服务时间','role':'parameter','unit_id':'s','observation':None,'provenance':'user_assumed'}])
            return value
        patch.setattr(source_fixture,'problem',full_problem)
    base=enter(stack,root,patch)
    sources=enter(source_stack,base,patch)
    approved=enter(approved_inputs,sources,SimpleNamespace(param=True))
    data=enter(paid_api,approved)
    client,path,store,rid,excerpt,resolver=data
    selected_handle=make_preview(data)['manifest']['handles'][0]['handle']
    raw=json.loads(response_body())
    candidate=json.loads(raw['choices'][0]['message']['content'])
    candidate['summary']='离线待核记录。'+('仍需核对输入与观察条件。'*35)
    candidate['mechanisms']=[{'label':'排队关系候选','mechanism':'这是一项需要检验的解释。'+('需要核对当前样本。'*60),
        'variable_map':[{'source':'arrival','target':'观察中的到达数量','rationale':'变量对应需要进一步检查。'}],
        'conditions':['测量窗口与样本条件需要核对。'],'nontransferable':['不同样本的结论不能直接沿用。'],'evidence_handles':[selected_handle]}]
    raw['choices'][0]['message']['content']=json.dumps(candidate,ensure_ascii=False)
    if kind=='null':raw['choices']=[]
    with execution(data,body=json.dumps(raw,ensure_ascii=False).encode()) as (session,confirmation,wire,pid):
        receipt=session.receive()
        assert (receipt._value.candidate is not None)==(kind!='null')
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            returned=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        report=None
        if kind!='pending':
            response=post(client,f'/api/research/{rid}/reconcile',{'task_id':confirmation['task_id'],'expected_task_version':2},'browser-typed-seed')
            assert response.status_code==200
            report=response.json()['data']['method_result']
            if kind=='null':assert report is None
            else:assert report and report['result_ref']==returned and report['received_at']==receipt._time
        with store.transaction() as conn:
            expected=(3,0) if kind=='pending' else (0,2)
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==expected
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==(0 if kind=='pending' else 1)
        assert wire['requests']==1
        facts={'research_id':rid,'task_id':confirmation['task_id'],'result_ref':returned if kind=='pending' else (report['result_ref'] if report else None),
            'received_at':receipt._time if kind=='pending' else (report['received_at'] if report else None), 'excerpt_id':excerpt,'owner_email':'research-a@example.test','auth_path':str(path)}
        if kind.startswith('history'):
            facts['original_problem']=client.get(f'/api/research/{rid}').json()['data']['current_problem']
        if kind=='history-same':
            from web.backend.tests.test_research_paid_producers import identity
            draft=make_preview(data,'history-second-preview')
            approved2=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft),'history-second-confirm')
            assert approved2.status_code==200,approved2.text
            raw2=json.loads(json.dumps(raw));body2=json.loads(raw2['choices'][0]['message']['content']);body2['summary']='第二份同修订待核记录。';raw2['choices'][0]['message']['content']=json.dumps(body2,ensure_ascii=False)
            with tcp_reply(json.dumps(raw2,ensure_ascii=False).encode()) as (factory,wire2):
                with BudgetedOwnedSession.offline_start(store,identity(client),session.proof.source,approved2.json()['data']['approval_ref'],connection_factory=factory) as second:
                    returned2=second.receive()
                    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=returned2)
                    completed2=post(client,f'/api/research/{rid}/reconcile',{'task_id':approved2.json()['data']['task_id'],'expected_task_version':2},'history-second-reconcile')
                    assert completed2.status_code==200 and completed2.json()['data']['method_result']
                    facts['second_result']=completed2.json()['data']['method_result'];facts['second_task_id']=approved2.json()['data']['task_id']
                    assert wire2['requests']==1
        if kind=='history-revision':
            previous=facts['original_problem'];changed={key:previous[key] for key in ('entry','original_input','objective','summary','variables','constraints','unknowns','confirmed')}
            changed.update(original_input='这是修订二的新问题，不能替换历史原问题',summary='这是修订二的新问题摘要')
            revised=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':changed},'history-new-revision')
            assert revised.status_code==200,revised.text
        if kind=='history-pages':
            from web.backend.tests.test_research_d1_integration import start_current
            for number in range(41):
                started=start_current(client,rid,'history queue '+chr(65+number//26)+chr(65+number%26));assert started.status_code==200,started.text
                task=started.json()['data']['task']
                stopped=post(client,f'/api/research/{rid}/cancel',{'task_id':task['id'],'expected_task_version':task['version']},'history-page-stop-'+str(number))
                assert stopped.status_code==200,stopped.text
            with store.transaction() as conn:facts['task_order']=[row[0] for row in conn.execute('SELECT id FROM research_tasks WHERE research_id=? ORDER BY start_version DESC,id DESC',(rid,))]
            assert len(facts['task_order'])==43
        output.write_text(json.dumps(facts,ensure_ascii=False))
'''


@pytest.fixture
def method_server(tmp_path,request):
    """Real B seed -> protected typed commit -> independently started real main.

    Original backend fixtures run unchanged in the release interpreter. There
    is no successful research GET replacement or fabricated protected body.
    """
    seed=tmp_path/'method-seed';metadata=tmp_path/'method-seed.json'
    runtime=os.getenv('STRUCTURE_RESEARCH_TEST_PYTHON',sys.executable)
    env=dict(os.environ)
    env.update({'PYTHONPATH':str(BACKEND)+os.pathsep+str(ROOT),'PYTHONDONTWRITEBYTECODE':'1',
                'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','DO_NOT_TRACK':'1'})
    for key in ('OPENROUTER_API_KEY','DEEPSEEK_API_KEY','SMTP_PASSWORD'):env.pop(key,None)
    prepared=subprocess.run([runtime,'-c',_METHOD_SEED,str(seed),str(metadata),getattr(request,'param','normal')],cwd=BACKEND,env=env,capture_output=True,text=True,timeout=60)
    assert prepared.returncode==0,'Real method seed failed: '+prepared.stderr[-1600:]
    facts=json.loads(metadata.read_text())
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
    base=f'http://127.0.0.1:{listener.getsockname()[1]}'
    env.update({'AUTH_DATA_DIR':str(seed/'auth'),'AUTH_ENABLED':'true','AUTH_DEV_MODE':'true',
        'JWT_SECRET':'research-synthetic-auth-secret-32-characters','AUTH_LINK_BASE_URL':base,
        'STRUCTURAL_SSO_SECRET':'research-synthetic-sso-secret-32-characters','STRUCTURAL_SSO_DATA_DIR':str(seed/'sso'),
        'STRUCTURAL_SSO_BETA_ORIGIN':base,'STRUCTURAL_ENV':'test','STRUCTURAL_RESEARCH_ENABLED':'true',
        'STRUCTURAL_D1_SOURCES_ENABLED':'true','STRUCTURAL_D1_PUBLIC_GET_ENABLED':'false',
        'STRUCTURAL_FAVORITES_PATH':str(seed/'favorites.jsonl'),'STRUCTURAL_LOG_FILE':str(seed/'main.jsonl'),
        'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,'ADMIN_NOTIFICATION_EMAIL':''})
    launcher=r'''
import sys
from pathlib import Path
from api import report_account,report,favorites
from services.report_store import ReportStore
report_account._store=ReportStore(Path(sys.argv[2]))
report._store=report_account._store
favorites._legacy_data_file=lambda:Path(sys.argv[2]).parent/'unused-favorites.jsonl'
import main,uvicorn
uvicorn.run(main.app,fd=int(sys.argv[1]),lifespan='off',access_log=False,log_level='warning')
'''
    processes=[];log=(tmp_path/'method-main.log').open('w+')
    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    def start(*,auth_enabled=True):
        run_env={**env,'AUTH_ENABLED':'true' if auth_enabled else 'false'}
        process=subprocess.Popen([runtime,'-c',launcher,str(listener.fileno()),str(seed/'legacy-history.db')],cwd=BACKEND,env=run_env,
                                 pass_fds=(listener.fileno(),),stdout=log,stderr=log)
        processes.append(process)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            assert process.poll() is None,'Real main method server exited'
            try:
                if httpx.get(base+'/research',timeout=.5,trust_env=False).status_code==200:return process
            except httpx.HTTPError:pass
            time.sleep(.05)
        raise AssertionError('Real method main readiness timed out')
    def withdraw_source():
        code=r'''
import sys
from api import auth
from research import ResearchStore
from research.authorization import AuthorizationGate
store=ResearchStore(auth._store())
with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(sys.argv[1],)).fetchone()[0]
with AuthorizationGate(store).owner_gate(pid),store.transaction(write=True) as conn:
    conn.execute("DELETE FROM research_evidence_objects WHERE id=? AND kind='excerpts'",(sys.argv[2],))
'''
        result=subprocess.run([runtime,'-c',code,facts['research_id'],facts['excerpt_id']],cwd=BACKEND,env=env,capture_output=True,text=True,timeout=15)
        assert result.returncode==0,'Source withdrawal control failed'
    try:
        process=start()
        yield {'base':base,'facts':facts,'process':process,'start':start,'stop':stop,'root':tmp_path,'env':env,'runtime':runtime,'withdraw_source':withdraw_source}
    finally:
        for process in processes:stop(process)
        listener.close();log.close()


@pytest.mark.parametrize('viewport',[{'width':1280,'height':900},{'width':430,'height':932}])
def test_method_result_real_b_typed_http_reopen_restart_and_local_citations(method_server,viewport):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport=viewport)
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            url=base+'/research/'+facts['research_id']
            response=context.request.get(base+'/api/research/'+facts['research_id'])
            assert response.status==200,response.text()
            report=response.json()['data']['method_result']
            assert report['result_ref']==facts['result_ref'] and report['received_at']==facts['received_at']
            page=context.new_page();page.goto(url)
            expect(page.locator('#method-body')).to_contain_text(report['sections']['summary'])
            expect(page.locator('#method-status')).to_contain_text('未运行真实模型')
            expect(page.locator('#method-status')).to_contain_text('证据不足／未经独立评审')
            expect(page.locator('#method-revision')).to_have_text(str(report['input_revision']))
            expect(page.locator('#method-time')).to_have_attribute('datetime',report['received_at'])
            for citation in report['citations']:
                expect(page.locator('#method-citations')).to_contain_text(citation['quote'])
                expect(page.locator('#method-citations')).to_contain_text(citation['attribution'])
            visible=page.locator('#method-section').inner_text()
            for internal in ('MethodHypothesisResultView-v1','OwnedMethodBody-v1',report['candidate_digest'],report['input_digest']):assert internal not in visible
            page.locator('#method-record-details summary').click()
            expect(page.locator('#method-result-ref')).to_have_text(report['result_ref'])
            page.locator('#method-record-details summary').click()
            assert page.locator('#method-section a').count()==0
            reference=page.get_by_role('button',name='查看引用 1',exact=True)
            reference.focus();page.keyboard.press('Enter')
            expect(page.locator('#method-citation-1')).to_be_focused()
            assert reference.bounding_box()['height']>=44
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            body=page.locator('#method-body').inner_text();citations=page.locator('#method-citations').inner_text()
            page.reload()
            expect(page.locator('#method-body')).to_have_text(body,use_inner_text=True)
            expect(page.locator('#method-time')).to_have_attribute('datetime',report['received_at'])
            method_server['stop'](method_server['process']);method_server['start']()
            page.reload()
            expect(page.locator('#method-body')).to_have_text(body,use_inner_text=True)
            expect(page.locator('#method-citations')).to_have_text(citations,use_inner_text=True)
            assert context.request.get(base+'/api/research/'+facts['research_id']).json()['data']['method_result']==report
            expect(page.locator('#research-list-items a')).to_have_count(1)
            with context.expect_page() as opened:page.locator('#research-list-items a').click()
            expect(opened.value.locator('#method-body')).to_have_text(body,use_inner_text=True)
            opened.value.close()
            page.screenshot(path=str(method_server['root']/'method-result.png'),full_page=True)
        finally:context.close();browser.close()


@pytest.mark.parametrize('method_server',['pending'],indirect=True)
def test_method_result_consumes_real_reconcile_view_without_generation(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#task-reconcile')).to_be_visible()
            with page.expect_response('**/reconcile') as response:page.locator('#task-reconcile').click()
            assert response.value.status==200
            report=response.value.json()['data']['method_result']
            assert report['result_ref']==facts['result_ref']
            expect(page.locator('#method-body')).to_contain_text(report['sections']['summary'])
            expect(page.locator('#method-time')).to_have_attribute('datetime',facts['received_at'])
        finally:context.close();browser.close()


@pytest.mark.parametrize('method_server',['null'],indirect=True)
def test_method_result_real_bad_b_never_becomes_visible_body(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            assert context.request.get(base+'/api/research/'+facts['research_id']).json()['data']['method_result'] is None
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-status')).to_contain_text('未取得可展示')
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#method-meta')).to_be_hidden()
            assert page.locator('#method-citations article').count()==0
        finally:context.close();browser.close()


@pytest.mark.parametrize('method_server',['pending'],indirect=True)
def test_method_result_cancelled_pending_body_stays_hidden(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#task-cancel')).to_be_visible()
            page.locator('#task-cancel').click()
            expect(page.locator('#task-phase')).to_contain_text('已停止')
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#method-meta')).to_be_hidden()
        finally:context.close();browser.close()


def test_method_result_changed_input_and_late_real_a_cannot_restore_old_body(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            def hold(route):
                response=route.fetch();assert response.status==200
                held.append((route,response))
            page.route('**/api/research/'+facts['research_id'],hold,times=1)
            page.locator('#task-refresh').click();page.wait_for_timeout(100)
            assert len(held)==1
            page.locator('#original-input').fill('换成新的研究现象，旧方法记录不能沿用')
            expect(page.locator('#method-body')).to_have_text('')
            page.locator('#save').click()
            expect(page.locator('#status')).to_contain_text('已保存修订 2')
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator('#task-refresh')).to_be_enabled()
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#original-input')).to_have_value('换成新的研究现象，旧方法记录不能沿用')
            fresh=context.request.get(base+'/api/research/'+facts['research_id']).json()['data']
            assert fresh.get('method_result') is None
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def test_method_result_actual_auth503_preserves_draft_but_requires_fresh_read(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            snapshot=page.locator('#problem-form').evaluate("f=>Array.from(f.querySelectorAll('input,textarea,select')).map(e=>[e.id,e.value,e.checked])")
            pending=page.evaluate("Object.fromEntries(Object.entries(sessionStorage))")
            method_server['stop'](method_server['process']);closed=method_server['start'](auth_enabled=False)
            requests=[]
            page.on('request',lambda request:requests.append(request.url) if '/api/research' in request.url else None)
            page.locator('#research-list-refresh').click()
            expect(page.locator('#status')).to_contain_text('暂时无法核对')
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#method-meta')).to_be_hidden()
            assert page.locator('#problem-form').evaluate("f=>Array.from(f.querySelectorAll('input,textarea,select')).map(e=>[e.id,e.value,e.checked])")==snapshot
            assert page.evaluate("Object.fromEntries(Object.entries(sessionStorage))")==pending and requests==[]
            method_server['stop'](closed);method_server['start']()
            page.locator('#research-list-refresh').click()
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            expect(page.locator('#method-body')).to_have_text('')
            page.locator('#task-refresh').click()
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            context.request.post(base+'/api/auth/logout',headers={'Origin':base})
            page.locator('#task-refresh').click()
            expect(page.locator('#problem-form')).to_be_hidden()
            expect(page.locator('#method-section')).to_be_hidden()
            expect(page.locator('#method-body')).to_have_text('')
        finally:context.close();browser.close()


def test_method_result_cross_owner_and_source_withdrawal_remove_private_body(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();other=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            login(other,base,'method-other@example.test')
            blocked=other.new_page();blocked.goto(base+'/research/'+facts['research_id'])
            expect(blocked.locator('#problem-form')).to_be_hidden()
            expect(blocked.locator('#method-body')).to_have_text('')
            method_server['withdraw_source']()
            page.locator('#task-refresh').click()
            expect(page.locator('#problem-form')).to_be_visible()
            expect(page.locator('#original-input')).to_be_enabled()
            expect(page.locator('#method-status')).to_contain_text('正文当前不可用')
            expect(page.locator('#method-body')).to_have_text('')
            assert '离线待核记录' not in page.locator('#method-section').inner_text()
        finally:context.close();other.close();browser.close()


def test_method_view_client_schema_rejects_corruption_of_real_backend_view(method_server):
    """Client-only negative checks use the actual validator, not mock GET proof."""
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            response=context.request.get(base+'/api/research/'+facts['research_id'])
            assert response.status==200
            data=response.json()['data']
            source=(ROOT/'web/frontend/assets/research.js').read_text()
            start=source.index('  function validMethod(data) {');end=source.index('  function renderMethod(',start)
            validator=source[start:end]
            id_line=next(line.strip() for line in source.splitlines() if line.strip().startswith('const validId ='))
            program="const payload=JSON.parse(require('fs').readFileSync(0,'utf8')); const researchId=payload.research.id; const selectedTask=null;\n"+id_line+'\n'+validator+r'''
if (!validMethod(payload)) throw Error('real backend view rejected');
const changes=[
 v=>delete v.method_result.schema_version,
 v=>{v.method_result.sections.summary=3},
 v=>{v.method_result.model_analysis_ran=true},
 v=>{v.method_result.input_digest='0'.repeat(64)},
 v=>{v.task.version++},
 v=>{v.method_result.is_historical=true},
 v=>{v.research.id='00000000-0000-4000-8000-000000000000'},
 v=>{v.execution='FAILED'},
 v=>{v.execution='CANCELLED'},
 v=>{v.method_result.citations[0].quote='x'},
 v=>{v.method_result.sections.mechanisms[0].evidence_handles=['missing']},
 v=>{v.method_result.sections.summary='x'.repeat(1001)},
 v=>{v.method_result.citations.push(v.method_result.citations[0])}
];
for (const change of changes) {
 const value=JSON.parse(JSON.stringify(payload));change(value);
 if (validMethod(value)!==null) throw Error('corrupted client shape accepted');
}
console.log('13 malformed client views rejected; real HTTP view accepted');
'''
            result=subprocess.run(['node','-e',program],input=json.dumps(data),capture_output=True,text=True,timeout=15)
            assert result.returncode==0,result.stderr
        finally:context.close();browser.close()


def test_method_result_new_explicit_source_task_clears_current_method_body(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport={'width':430,'height':932})
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            page.locator('#source-query').fill('queue theory');page.locator('#source-preview').click()
            expect(page.locator('#source-confirm')).to_be_visible()
            # Merely editing/previewing a query does not generate or execute.
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            with page.expect_response('**/source-tasks') as started:page.locator('#source-confirm').click()
            assert started.value.status==200
            assert started.value.json()['data']['task']['id']!=facts['task_id']
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#method-meta')).to_be_hidden()
        finally:context.close();browser.close()


@pytest.mark.parametrize('late_status',[404,401])
@pytest.mark.parametrize('save_new_revision',[True,False],ids=['saved','draft'])
def test_method_result_late_actual_access_error_cannot_clear_new_problem(method_server,late_status,save_new_revision):
    """Hold a real rejected GET, then accept a newer save or local edit."""
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            owner_cookies=context.cookies()
            if late_status==404:
                login(context,base,'late-foreign-owner@example.test')
            else:
                assert context.request.post(base+'/api/auth/logout',headers={'Origin':base}).status==200
            def hold(route):
                response=route.fetch();assert response.status==late_status
                held.append((route,response))
            page.route('**/api/research/'+facts['research_id'],hold,times=1)
            page.locator('#task-refresh').click()
            for _ in range(50):
                if held:break
                page.wait_for_timeout(20)
            assert len(held)==1
            if late_status==401:login(context,base,facts['owner_email'])
            else:
                context.clear_cookies();context.add_cookies(owner_cookies)
            draft='另一份新问题，迟到的旧访问错误不应清除当前输入'
            page.locator('#original-input').fill(draft)
            if save_new_revision:
                with page.expect_response('**/revisions') as saved:page.locator('#save').click()
                assert saved.value.status==200
                assert saved.value.json()['data']['current_problem']['revision']==2
                expect(page.locator('#status')).to_contain_text('已保存修订 2')
            pending=page.evaluate("Object.fromEntries(Object.entries(sessionStorage))")
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator('#task-refresh')).to_be_enabled()
            expect(page.locator('#problem-form')).to_be_visible()
            expect(page.locator('#original-input')).to_have_value(draft)
            assert page.evaluate("Object.fromEntries(Object.entries(sessionStorage))")==pending
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#method-meta')).to_be_hidden()
            if save_new_revision:
                fresh=context.request.get(base+'/api/research/'+facts['research_id'])
                assert fresh.status==200
                assert fresh.json()['data']['current_problem']['original_input']==draft
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def test_method_result_successful_old_write_cannot_revive_revoked_private_view(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            def hold(route):
                response=route.fetch();assert response.status==200
                held.append((route,response))
            page.route('**/api/research/*/revisions',hold,times=1)
            page.locator('#original-input').fill('退出前已经提交，迟到成功回执也不能恢复私有页面')
            page.locator('#save').click()
            for _ in range(50):
                if held:break
                page.wait_for_timeout(20)
            assert len(held)==1
            assert held[0][1].json()['data']['current_problem']['revision']==2
            assert context.request.post(base+'/api/auth/logout',headers={'Origin':base}).status==200
            page.locator('#research-list-refresh').click()
            expect(page.locator('#problem-form')).to_be_hidden()
            pending=page.evaluate("Object.fromEntries(Object.entries(sessionStorage))")
            assert any(key.startswith('structure-research-pending:') for key in pending)
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator('#status')).to_contain_text('较早的来源读取已失效')
            expect(page.locator('#problem-form')).to_be_hidden()
            expect(page.locator('#original-input')).to_have_value('')
            expect(page.locator('#method-section')).to_be_hidden()
            expect(page.locator('#method-body')).to_have_text('')
            assert page.evaluate("Object.fromEntries(Object.entries(sessionStorage))")==pending
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


@pytest.mark.parametrize('refresh',['task-refresh','source-refresh'])
def test_method_current_source_unavailable_preserves_problem_and_explains_missing_body(method_server,refresh):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport={'width':430,'height':932})
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            expect(page.locator('#status')).to_contain_text('已从账户读取保存的问题')
            method_server['withdraw_source']()
            with page.expect_response(base+'/api/research/'+facts['research_id']) as response:
                page.locator('#'+refresh).click()
            assert response.value.status==200
            assert response.value.json()['data']['method_result'] is None
            assert response.value.json()['data']['method_result_state']=='unavailable'
            assert context.request.get(base+'/api/auth/me').status==200
            expect(page.locator('#problem-form')).to_be_visible()
            expect(page.locator('#original-input')).to_be_enabled()
            expect(page.locator('#method-status')).to_contain_text('正文当前不可用')
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#method-citations')).to_have_text('')
            expect(page.locator('#method-meta')).to_be_hidden()
            expect(page.locator('#status')).to_be_visible()
            expect(page.locator('#status')).to_contain_text('正文当前不可用')
            expect(page.locator('#status')).to_have_attribute('data-error','true')
            assert '已从账户读取保存的问题' not in page.locator('body').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(method_server['root']/('body-unavailable-'+refresh+'.png')),full_page=True)
        finally:context.close();browser.close()


@pytest.mark.parametrize('method_server',['history-revision','history-same'],indirect=True)
@pytest.mark.parametrize('viewport',[{'width':1280,'height':900},{'width':430,'height':932}])
def test_history_real_result_original_problem_native_new_tab_restart_and_readonly(method_server,viewport):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport=viewport)
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            rid=facts['research_id'];task=facts['task_id'];url=base+'/research/'+rid+'?task_id='+task
            saved=context.request.get(base+'/api/research/'+rid,params={'task_id':task})
            assert saved.status==200
            data=saved.json()['data'];report=data['method_result'];original=facts['original_problem']
            assert data['is_historical'] is report['is_historical'] is True
            page=context.new_page();page.goto(base+'/research/'+rid)
            expect(page.locator('#task-history-items a')).not_to_have_count(0)
            draft='当前标签里的新草稿，打开历史不能丢失'
            page.locator('#original-input').fill(draft)
            link=page.locator('#task-history-items a[href="/research/'+rid+'?task_id='+task+'"]')
            expect(link).to_have_attribute('target','_blank');expect(link).to_have_attribute('rel','noopener')
            assert link.bounding_box()['height']>=44
            link.focus()
            with context.expect_page() as opened:page.keyboard.press('Enter')
            history=opened.value
            expect(history.locator('#view-context')).to_contain_text('历史流程')
            assert history.evaluate('window.opener===null')
            expect(page.locator('#original-input')).to_have_value(draft)
            for identifier,key in [('original-input','original_input'),('objective','objective'),('entry','entry'),('summary','summary')]:
                expect(history.locator('#'+identifier)).to_have_value(original[key])
                expect(history.locator('#'+identifier)).to_be_disabled()
            for identifier in ('constraints','unknowns'):
                expect(history.locator('#'+identifier)).to_have_value('\n'.join(original[identifier]))
            assert history.locator('#confirmed').is_checked()==original['confirmed']
            roles={'state':'状态','parameter':'参数','input':'输入','constraint':'约束','output':'输出'}
            origins={'user_observed':'用户观察','user_assumed':'用户假设','system_proposed':'系统提议'}
            for variable in original['variables']:
                for value in (variable['id'],variable['label'],'角色：'+roles[variable['role']],'单位：'+(variable['unit_id'] or '待确认'),'观测：'+(variable['observation'] if variable['observation'] is not None else '待补充'),'来源：'+origins[variable['provenance']]):
                    expect(history.locator('#variables')).to_contain_text(value)
            expect(history.locator('#problem-created')).to_have_attribute('datetime',original['created_at'])
            assert history.locator('#original-input').evaluate('e=>e.scrollHeight<=e.clientHeight+2')
            expect(history.locator('#method-body')).to_contain_text(report['sections']['summary'])
            expect(history.locator('#method-title')).to_have_text('历史方法假说记录')
            expect(history.locator('#method-revision')).to_have_text(str(original['revision']))
            expect(history.locator('#method-time')).to_have_attribute('datetime',facts['received_at'])
            expect(history.locator('#method-record-details details')).not_to_have_attribute('open','')
            history.locator('#method-record-details summary').focus();history.keyboard.press('Enter')
            expect(history.locator('#method-result-ref')).to_be_visible()
            expect(history.locator('#method-result-ref')).to_have_text(facts['result_ref'])
            expect(history.locator('#task-current')).to_have_attribute('href','/research/'+rid)
            posts=[];history.on('request',lambda request:posts.append(request.url) if request.method=='POST' and '/api/research' in request.url else None)
            for identifier in ('save','task-start','task-cancel','task-reconcile','task-resume','source-preview','source-confirm'):
                history.locator('#'+identifier).dispatch_event('click')
            history.locator('#problem-form').dispatch_event('submit')
            history.wait_for_timeout(100)
            assert posts==[]
            with history.expect_response(lambda response:response.url==base+'/api/research/'+rid+'?task_id='+task) as refreshed:
                history.locator('#task-refresh').click()
            assert refreshed.value.status==200
            expect(history.locator('#method-time')).to_have_attribute('datetime',facts['received_at'])
            method_server['stop'](method_server['process']);method_server['start']()
            history.reload()
            expect(history.locator('#method-body')).to_contain_text(report['sections']['summary'])
            expect(history.locator('#method-time')).to_have_attribute('datetime',facts['received_at'])
            expect(history.locator('#method-result-ref')).to_have_text(facts['result_ref'])
            expect(history.locator('#original-input')).to_have_value(original['original_input'])
            assert history.url==url and posts==[]
            assert history.evaluate('document.documentElement.scrollWidth<=innerWidth')
            history.screenshot(path=str(method_server['root']/'history-readonly.png'),full_page=True)
        finally:context.close();browser.close()


@pytest.mark.parametrize('pending_stage',['source-approvals','source-tasks'])
def test_fixed_task_and_history_never_replay_real_pending_source_intent(method_server,pending_stage):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();observed=[]
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            rid=facts['research_id'];page=context.new_page();page.goto(base+'/research/'+rid)
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            page.locator('#source-query').fill('queue history pending');page.locator('#source-preview').click()
            expect(page.locator('#source-confirm')).to_be_visible()
            def lose_receipt(route):
                response=route.fetch();assert response.status==200
                observed.append(response.json());route.abort()
            page.route('**/api/research/*/'+pending_stage,lose_receipt,times=1)
            page.locator('#source-confirm').click()
            expect(page.locator('#source-status')).to_contain_text('fetch')
            assert len(observed)==1
            slot='structure-research-pending:source:'+pending_stage+':'+rid
            storage=page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')
            assert slot in storage
            posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' and '/api/research' in request.url else None)
            task=facts['task_id'];page.goto(base+'/research/'+rid+'?task_id='+task)
            view=context.request.get(base+'/api/research/'+rid,params={'task_id':task}).json()['data']
            assert view['is_historical']==(pending_stage=='source-tasks')
            expect(page.locator('#view-context')).to_contain_text('历史流程' if view['is_historical'] else '固定任务只读')
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            for identifier in ('save','task-start','task-cancel','task-reconcile','task-resume','source-preview','source-confirm'):
                page.locator('#'+identifier).dispatch_event('click')
            page.locator('#problem-form').dispatch_event('submit')
            page.locator('#reload').click()
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            page.wait_for_timeout(100)
            assert posts==[]
            assert page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')==storage
            expect(page.locator('#task-current')).to_have_attribute('href','/research/'+rid)
        finally:context.close();browser.close()


@pytest.mark.parametrize('method_server',['history-pages'],indirect=True)
def test_history_real_43_tasks_inclusive_pages_no_gaps_duplicates_or_lost_anchor(method_server):
    from urllib.parse import urlparse,parse_qs
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport={'width':430,'height':932})
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id']);seen=[];sizes=[]
            while True:
                expect(page.locator('#task-history-items a')).not_to_have_count(0)
                links=page.locator('#task-history-items a').all()
                identifiers=[parse_qs(urlparse(link.get_attribute('href')).query)['task_id'][0] for link in links]
                sizes.append(len(identifiers));assert not set(seen).intersection(identifiers);seen+=identifiers
                if not page.locator('#task-history-more').is_visible():break
                anchor=parse_qs(urlparse(page.locator('#task-history-more').get_attribute('href')).query)['task_id'][0]
                assert anchor not in seen
                with context.expect_page() as opened:page.locator('#task-history-more').click()
                page=opened.value
                expect(page.locator('#task-history-items a').first).to_have_attribute('href','/research/'+facts['research_id']+'?task_id='+anchor)
                expect(page.locator('#view-context')).to_contain_text('历史流程')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert sizes==[20,20,3] and seen==facts['task_order'] and len(set(seen))==43
            link=page.locator('#task-history-items a[href="/research/'+facts['research_id']+'?task_id='+facts['task_id']+'"]')
            with context.expect_page() as opened:link.click()
            expect(opened.value.locator('#method-result-ref')).to_have_text(facts['result_ref'])
            expect(opened.value.locator('#method-body')).to_contain_text('离线待核记录')
            page.screenshot(path=str(method_server['root']/'history-last-page.png'),full_page=True)
        finally:context.close();browser.close()


@pytest.mark.parametrize('save_new_revision',[False,True],ids=['draft','saved'])
def test_late_real_source_unavailable_200_cannot_overwrite_new_problem(method_server,save_new_revision):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            method_server['withdraw_source']()
            def hold(route):
                response=route.fetch();assert response.status==200
                assert response.json()['data']['method_result'] is None and response.json()['data']['method_result_state']=='unavailable'
                held.append((route,response))
            page.route('**/api/research/'+facts['research_id'],hold,times=1)
            page.locator('#task-refresh').click()
            for _ in range(50):
                if held:break
                page.wait_for_timeout(20)
            assert len(held)==1
            draft='这是新的问题，迟到的正文不可用回执不能覆盖它'
            page.locator('#original-input').fill(draft)
            if save_new_revision:
                page.locator('#save').click();expect(page.locator('#status')).to_contain_text('已保存修订 2')
            notice=page.locator('#status').inner_text();pending=page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator('#task-refresh')).to_be_enabled()
            expect(page.locator('#original-input')).to_have_value(draft)
            expect(page.locator('#original-input')).to_be_enabled()
            expect(page.locator('#status')).to_have_text(notice)
            expect(page.locator('#method-body')).to_have_text('')
            assert page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')==pending
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


@pytest.mark.parametrize('method_server',['history-revision'],indirect=True)
def test_unavailable_historical_body_preserves_original_readonly_problem_and_navigation(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();url=base+'/research/'+facts['research_id']+'?task_id='+facts['task_id'];page.goto(url)
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            method_server['withdraw_source']()
            with page.expect_response(base+'/api/research/'+facts['research_id']+'?task_id='+facts['task_id']) as response:page.locator('#task-refresh').click()
            assert response.value.status==200 and response.value.json()['data']['method_result_state']=='unavailable'
            expect(page.locator('#original-input')).to_have_value(facts['original_problem']['original_input'])
            expect(page.locator('#original-input')).to_be_disabled()
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#method-meta')).to_be_hidden()
            expect(page.locator('#method-record-details')).to_be_hidden()
            expect(page.locator('#status')).to_contain_text('正文当前不可用')
            expect(page.locator('#task-history-items a')).not_to_have_count(0)
            assert context.request.get(base+'/api/auth/me').status==200
        finally:context.close();browser.close()


def test_current_real_cross_owner404_remains_visible_and_clears_private_content(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            page=context.new_page();page.goto(base+'/research/'+facts['research_id'])
            expect(page.locator('#method-body')).to_contain_text('离线待核记录')
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            login(context,base,'current-foreign-owner@example.test')
            with page.expect_response(base+'/api/research/'+facts['research_id']) as response:page.locator('#task-refresh').click()
            assert response.value.status==404 and context.request.get(base+'/api/auth/me').status==200
            expect(page.locator('#problem-form')).to_be_hidden()
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#task-history-section')).to_be_hidden()
            expect(page.locator('#status')).to_have_text(response.value.json()['error']['message'])
            expect(page.locator('#status')).to_be_visible()
        finally:context.close();browser.close()


@pytest.mark.parametrize('method_server',['history-same'],indirect=True)
def test_history_client_validation_rejects_mismatched_task_flags_and_bad_navigation(method_server):
    """Client-only corruptions of actual historical GET, not fake HTTP success."""
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            response=context.request.get(base+'/api/research/'+facts['research_id'],params={'task_id':facts['task_id']});assert response.status==200
            data=response.json()['data'];source=(ROOT/'web/frontend/assets/research.js').read_text()
            validator=source[source.index('  function validMethod(data) {'):source.index('  function renderMethod(')]
            navigation=source[source.index('  function validTaskHistory(data) {'):source.index('  function renderTaskHistory(')]
            definitions='\n'.join(line.strip() for line in source.splitlines() if line.strip().startswith(('const validId =','const recordTime =')))
            program="const payload=JSON.parse(require('fs').readFileSync(0,'utf8')); const researchId=payload.research.id; let selectedTask=payload.task.id;\n"+definitions+'\n'+validator+'\n'+navigation+r"""
if (!validMethod(payload) || !validTaskHistory(payload)) throw Error('real historical GET rejected');
const bodyChanges=[v=>{v.method_result.is_historical=false},v=>{v.current_problem.digest='0'.repeat(64)},v=>{v.current_problem.research_id='00000000-0000-4000-8000-000000000000'},v=>{v.method_result.input_revision++},v=>{delete v.research.current_revision},v=>{v.research.current_revision=1.5}];
for (const change of bodyChanges) {const v=structuredClone(payload);change(v);if(validMethod(v)!==null)throw Error('bad historical body accepted')}
const navChanges=[v=>{v.research.id='00000000-0000-4000-8000-000000000000'},v=>{v.task_history[0].task_id='javascript:alert(1)'},v=>{v.task_history.push(v.task_history[0])},v=>{v.next_task_id=v.task_history[0].task_id},v=>{v.next_task_id='bad'},v=>{v.task_history[0].research_id='foreign'},v=>{v.task_history[0].input_revision=0},v=>{delete v.research.current_revision},v=>{v.research_version=1.5},v=>{v.task_history[0].start_version=v.research_version+1}];
for (const change of navChanges) {const v=structuredClone(payload);change(v);if(validTaskHistory(v)!==null)throw Error('bad history navigation accepted')}
selectedTask='00000000-0000-4000-8000-000000000000';
if(validMethod(payload)!==null || validTaskHistory(payload)!==null)throw Error('wrong URL task scope accepted');
console.log('real historical body/nav accepted; '+(bodyChanges.length+navChanges.length+2)+' malformed scope/body/nav checks rejected');
"""
            checked=subprocess.run(['node','-e',program],input=json.dumps(data),capture_output=True,text=True,timeout=15)
            assert checked.returncode==0,checked.stderr
        finally:context.close();browser.close()


@pytest.mark.parametrize('transition',['revision','task'])
def test_fixed_current_task_refresh_becomes_historical_with_server_truth(method_server,transition):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            rid=facts['research_id'];task=facts['task_id'];selected=base+'/api/research/'+rid+'?task_id='+task
            fixed=context.new_page();fixed.goto(base+'/research/'+rid+'?task_id='+task)
            expect(fixed.locator('#view-context')).to_contain_text('固定任务只读')
            assert context.request.get(selected).json()['data']['is_historical'] is False
            editor=context.new_page();editor.goto(base+'/research/'+rid)
            expect(editor.locator('#original-input')).to_be_enabled()
            if transition=='revision':
                editor.locator('#original-input').fill('另一标签保存了新的问题修订')
                editor.locator('#save').click();expect(editor.locator('#status')).to_contain_text('已保存修订 2')
            else:
                editor.locator('#source-query').fill('queue next task');editor.locator('#source-preview').click()
                expect(editor.locator('#source-confirm')).to_be_visible()
                editor.locator('#source-confirm').click();expect(editor.locator('#source-status')).to_contain_text('已排队')
            with fixed.expect_response(selected) as response:fixed.locator('#task-refresh').click()
            assert response.value.status==200 and response.value.json()['data']['is_historical'] is True
            expect(fixed.locator('#method-body')).to_contain_text('离线待核记录')
            expect(fixed.locator('#method-title')).to_have_text('历史方法假说记录')
            expect(fixed.locator('#view-context')).to_contain_text('历史流程')
            expect(fixed.locator('#view-context')).not_to_contain_text('这是当前任务')
            expect(fixed.locator('#status')).to_contain_text('历史流程')
            expect(fixed.locator('#status')).not_to_contain_text('仍是当前任务')
            expect(fixed.locator('#method-result-ref')).to_have_text(facts['result_ref'])
            expect(fixed.locator('#method-time')).to_have_attribute('datetime',facts['received_at'])
            expect(fixed.locator('#original-input')).to_be_disabled()
        finally:context.close();browser.close()



def test_invalid_or_ambiguous_task_url_never_falls_back_to_editable_current_problem(method_server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=method_server['base'];facts=method_server['facts'];login(context,base,facts['owner_email'])
            for query in ('task_id=','task_id=bad','task_id='+facts['task_id']+'&task_id='+facts['task_id']):
                page=context.new_page();requests=[]
                page.on('request',lambda request:requests.append((request.method,request.url)) if '/api/research' in request.url else None)
                page.goto(base+'/research/'+facts['research_id']+'?'+query)
                expect(page.locator('#status')).to_have_text('流程链接无效。')
                expect(page.locator('#problem-form')).to_be_hidden()
                expect(page.locator('#task-history-items a')).to_have_count(0)
                page.locator('#problem-form').dispatch_event('submit')
                page.locator('#task-start').dispatch_event('click')
                page.wait_for_timeout(50)
                assert requests==[]
                page.close()
        finally:context.close();browser.close()



@pytest.mark.parametrize('selector',['','bad','00000000-0000-4000-8000-000000000000'],ids=['empty','malformed','valid-uuid'])
def test_task_selector_without_research_id_is_explicitly_invalid_and_cannot_create(server,selector):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page();requests=[]
            page.on('request',lambda request:requests.append((request.method,request.url)) if '/api/research' in request.url else None)
            page.goto(base+'/research?task_id='+selector)
            expect(page.locator('#status')).not_to_have_text('正在读取研究记录…')
            observation={'selector':selector,'status':page.locator('#status').inner_text(),'form_visible':page.locator('#problem-form').is_visible(),'requests':requests.copy()}
            (server['root']/'missing-research-id-observation.json').write_text(json.dumps(observation,ensure_ascii=False,indent=2))
            expect(page.locator('#status')).to_have_text('流程链接无效。')
            expect(page.locator('#status')).to_have_attribute('data-error','true')
            expect(page.locator('#problem-form')).to_be_hidden()
            expect(page.locator('#method-body')).to_have_text('')
            expect(page.locator('#task-history-items a')).to_have_count(0)
            page.locator('#problem-form').dispatch_event('submit')
            page.locator('#task-start').dispatch_event('click')
            page.wait_for_timeout(50)
            assert requests==[]
            assert context.request.get(base+'/api/auth/me').status==200
        finally:context.close();browser.close()


def test_new_research_without_task_selector_keeps_real_create_and_save(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page();page.goto(base+'/research')
            expect(page.locator('#status')).to_have_text('新问题尚未保存。')
            expect(page.locator('#original-input')).to_be_enabled()
            expect(page.locator('#save')).to_be_enabled()
            text='普通新建入口应继续真实保存问题'
            fill(page,text)
            with page.expect_response(lambda response:response.url==base+'/api/research' and response.request.method=='POST') as saved:
                page.locator('#save').click()
            assert saved.value.status==200
            data=saved.value.json()['data'];rid=data['research']['id']
            assert data['current_problem']['original_input']==text and data['current_problem']['revision']==1
            expect(page.locator('#status')).to_contain_text('已保存修订 1')
            assert page.url==base+'/research/'+rid
            actual=context.request.get(base+'/api/research/'+rid)
            assert actual.status==200 and actual.json()['data']['current_problem']['original_input']==text
        finally:context.close();browser.close()



def _open_formula_editor(page,base,*,left='little',right='little',scope='expression'):
    page.goto(base+'/research')
    expect(page.locator('#problem-form')).to_be_visible()
    fill(page,'用户提供的公式对照实际保存流程')
    page.locator('#entry').select_option('formula')
    page.locator('#formula-enable').check()
    if left!='little':page.locator('#formula-left-template').select_option(left)
    if right!='little':page.locator('#formula-right-template').select_option(right)
    page.locator('#formula-scope').select_option(scope)


def _save_formula_editor(page,base):
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.split('?')[0].endswith(('/api/research','/revisions'))) as saved:
        page.locator('#save').click()
    assert saved.value.status==200,saved.value.text()
    body=saved.value.json()['data']
    expect(page.locator('#formula-editor-status')).to_contain_text('已按权限读取原公式快照')
    return body


@pytest.mark.parametrize('viewport',[{'width':1280,'height':900},{'width':430,'height':932}])
def test_formula_real_ui_save_snapshot_confirm_actual_return_and_reopen(server,viewport):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport=viewport)
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            expect(page.locator('#formula-run')).to_be_disabled()
            page.locator('#formula-left-use-template').click();page.locator('#formula-right-use-template').click()
            page.locator('#formula-left-symbol-1-value').fill('3.00')
            body=_save_formula_editor(page,base);rid=body['research']['id'];meta=body['current_problem']['formula_snapshot']
            assert meta['executable'] and 'formula_draft' not in body['current_problem']
            snapshot=context.request.get(base+'/api/research/'+rid+'/formula-revisions/1')
            assert snapshot.status==200 and snapshot.json()['data']['formula_digest']==meta['formula_digest']
            assert snapshot.json()['data']['formula']['left']['symbols'][1]['value']=='3.00'
            expect(page.locator('#formula-run')).to_be_disabled()
            page.locator('#formula-confirm').check()
            with page.expect_response('**/formula-checks') as checked:page.locator('#formula-run').click()
            assert checked.value.status==200,checked.value.text()
            ack=checked.value.json()['data'];ref=ack['result_ref']
            original=context.request.get(base+'/api/research/'+rid+'/formula-results/'+ref)
            assert original.status==200,original.text()
            result=original.json()['data'];assert result['state']=='available'
            expect(page.locator('#formula-result-ref')).to_have_text(ref)
            expect(page.locator('#formula-result-time')).to_have_attribute('datetime',ack['formula_result_recorded_at'])
            assert page.locator('#formula-results .formula-outcome').count()==4
            assert result['result']['execution_attested'] is False
            if result['provenance']['execution_state']=='unsupported':
                assert result['provenance']['execution_attested'] is False
                expect(page.locator('#formula-status')).to_contain_text('未执行')
                assert set(page.locator('.formula-outcome-status').all_text_contents())=={'不支持 · 关系未判定'}
                assert page.locator('.formula-outcome-status[data-status="passed"]').count()==0
            else:assert result['provenance']['execution_attested'] is (result['provenance']['execution_state']=='ok')
            server['stop'](server['process']);server['start']()
            page.reload()
            expect(page.locator('#formula-result-ref')).to_have_text(ref)
            expect(page.locator('#formula-result-time')).to_have_attribute('datetime',ack['formula_result_recorded_at'])
            assert context.request.get(base+'/api/research/'+rid+'/formula-results/'+ref).json()==original.json()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(server['root']/'formula-real-return.png'),full_page=True)
        finally:context.close();browser.close()


def test_formula_empty_structure_is_real_saved_draft_and_not_executable(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            with page.expect_response(lambda response:response.request.method=='POST' and response.url==base+'/api/research') as saved:page.locator('#save').click()
            assert saved.value.status==200,saved.value.text()
            data=saved.value.json()['data'];assert data['current_problem']['formula_snapshot']['executable'] is False
            expect(page.locator('#formula-editor-status')).to_contain_text('仍缺结构')
            expect(page.locator('#formula-confirm')).to_be_disabled();expect(page.locator('#formula-run')).to_be_disabled()
            requests=[];page.on('request',lambda request:requests.append(request.url) if request.method=='POST' and request.url.endswith('/formula-checks') else None)
            page.locator('#formula-run').dispatch_event('click');page.wait_for_timeout(50)
            assert requests==[]
            with sqlite3.connect(server['path']) as conn:assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==0
        finally:context.close();browser.close()



def _formula_declare_all(page,side):
    for field in page.locator('#formula-'+side+' select[id*="-assumptions-"][id$="-declared"]').all():field.select_option('true')


@pytest.mark.parametrize('variant',[0,1])
@pytest.mark.parametrize('scenario',['little','mm1','thermal-rc','local'])
def test_formula_registered_cases_real_inputs_and_honest_execution_status(server,scenario,variant):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page()
            left='passive_decay' if scenario in ('thermal-rc','local') else scenario
            right='linear_stable' if scenario=='local' else left
            scope='initial_value_problem' if scenario=='thermal-rc' else 'equation_form' if scenario!='little' else 'expression'
            _open_formula_editor(page,base,left=left,right=right,scope=scope)
            if scenario=='thermal-rc':page.locator('#formula-right-domain').select_option('electrical')
            for name in ('left','right'):
                page.locator('#formula-'+name+'-use-template').click();_formula_declare_all(page,name)
            if scenario=='little' and variant:
                for name in ('left','right'):
                    for index,value in enumerate(('20','4','5')):page.locator(f'#formula-{name}-symbol-{index}-value').fill(value)
            if scenario=='mm1' and variant:
                for name in ('left','right'):
                    for index,value in enumerate(('0.25','2','6')):page.locator(f'#formula-{name}-symbol-{index}-value').fill(value)
                    page.locator(f'#formula-{name}-symbol-0-unit').select_option('workday')
                    for index in (1,2):page.locator(f'#formula-{name}-symbol-{index}-unit').select_option('count_per_workday')
                    page.locator(f'#formula-{name}-basis').select_option('workday')
            if scenario=='thermal-rc':
                for name,value in [('left','4' if variant else '8'),('right','7' if variant else '3')]:
                    page.locator('#formula-'+name+'-initial-enable').check()
                    page.locator('#formula-'+name+'-initial-at_time').fill('0.0')
                    page.locator('#formula-'+name+'-initial-value').fill(value)
                    page.locator('#formula-'+name+'-initial-declared').select_option('true')
            if scenario=='local' and variant:
                page.locator('#formula-right-symbol-1-value').fill('0.5')
            page.locator('#formula-samples').fill('0,1,2' if scenario in ('thermal-rc','local') else '0')
            body=_save_formula_editor(page,base);rid=body['research']['id']
            actual=context.request.get(base+'/api/research/'+rid+'/formula-revisions/1').json()['data']['formula']
            assert actual['comparison_scope']==scope
            assert actual['left']['template_id']==left and actual['right']['template_id']==right
            assert actual['left']['source_refs']==[] and actual['right']['source_refs']==[]
            if scenario=='thermal-rc':assert actual['left']['symbols'][0]['unit_id']=='K' and actual['right']['symbols'][0]['unit_id']=='V'
            if scenario=='mm1' and variant:assert actual['left']['time_basis']==actual['right']['time_basis']=='workday'
            page.locator('#formula-confirm').check()
            with page.expect_response('**/formula-checks') as returned:page.locator('#formula-run').click()
            assert returned.value.status==200,returned.value.text()
            meta=returned.value.json()['data'];response=context.request.get(base+'/api/research/'+rid+'/formula-results/'+meta['result_ref'])
            assert response.status==200 and response.json()['data']['state']=='available'
            result=response.json()['data'];expect(page.locator('#formula-result-ref')).to_have_text(meta['result_ref'])
            assert result['result']['execution_attested'] is False
            if result['provenance']['execution_state']=='ok':
                assert result['provenance']['execution_attested'] is True
                canonical=next(v for v in result['result']['outcomes'] if v['check_kind']=='canonical_transform')
                assert canonical['status']=='passed'
                assert canonical['relation']==('algebraic_identity' if scenario=='little' else 'local_approximation' if scenario=='local' else 'conditional_model_equivalence')
                numeric=next(v for v in result['result']['outcomes'] if v['check_kind']=='bounded_numeric')
                assert numeric['relation']=='undetermined'
            else:
                assert result['provenance']['execution_attested'] is False
                assert page.locator('.formula-outcome-status[data-status="passed"]').count()==0
        finally:context.close();browser.close()


def test_formula_lost_actual_post_receipt_reopens_and_recovers_same_key_ref_without_second_task(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();received=[];keys=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            body=_save_formula_editor(page,base);rid=body['research']['id']
            page.on('request',lambda request:keys.append((request.headers.get('idempotency-key'),request.post_data)) if request.method=='POST' and request.url.endswith('/formula-checks') else None)
            def lose(route):
                response=route.fetch();assert response.status==200;received.append(response.json()['data']);route.abort()
            page.route('**/formula-checks',lose,times=1)
            page.locator('#formula-confirm').check();page.locator('#formula-run').click()
            expect(page.locator('#formula-status')).to_contain_text('状态尚未确认')
            assert len(received)==1;original=received[0]
            pending=page.evaluate("Object.fromEntries(Object.entries(sessionStorage).filter(([k])=>k.startsWith('structure-research-pending:formula-check:'))) ")
            assert len(pending)==1
            page.reload();expect(page.locator('#formula-result-ref')).to_have_text(original['result_ref'])
            assert len(keys)==1 and page.evaluate("Object.fromEntries(Object.entries(sessionStorage).filter(([k])=>k.startsWith('structure-research-pending:formula-check:'))) ")==pending
            with page.expect_response('**/formula-checks') as replay:page.locator('#formula-recover').click()
            assert replay.value.status==200 and replay.value.json()['data']['result_ref']==original['result_ref']
            assert replay.value.json()['data']['formula_result_recorded_at']==original['formula_result_recorded_at']
            expect(page.locator('#formula-result-ref')).to_have_text(original['result_ref'])
            assert len(keys)==2 and keys[0]==keys[1]
            assert page.evaluate("Object.keys(sessionStorage).filter(k=>k.startsWith('structure-research-pending:formula-check:')).length")==0
            with sqlite3.connect(server['path']) as conn:
                assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==1
                assert conn.execute("SELECT count(*) FROM research_tasks WHERE policy_revision='local-formula-v1'").fetchone()[0]==1
        finally:context.close();browser.close()


@pytest.mark.parametrize('save_new_revision',[False,True],ids=['draft','saved'])
def test_late_actual_formula_post_ack_cannot_replace_new_formula_or_problem(server,save_new_revision):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            _save_formula_editor(page,base)
            def hold(route):
                response=route.fetch();assert response.status==200;held.append((route,response))
            page.route('**/formula-checks',hold,times=1)
            page.locator('#formula-confirm').check();page.locator('#formula-run').click()
            for _ in range(50):
                if held:break
                page.wait_for_timeout(20)
            assert len(held)==1
            page.locator('#formula-left-symbol-1-value').fill('9')
            page.locator('#original-input').fill('公式检查期间新写的问题草稿')
            if save_new_revision:
                _save_formula_editor(page,base);expect(page.locator('#revision-label')).to_have_text('当前修订 2')
            notice=page.locator('#status').inner_text()
            route,response=held.pop();route.fulfill(response=response)
            expect(page.locator('#formula-left-symbol-1-value')).to_have_value('9')
            expect(page.locator('#original-input')).to_have_value('公式检查期间新写的问题草稿')
            expect(page.locator('#status')).to_have_text(notice)
            expect(page.locator('#formula-results')).to_have_text('')
            page.wait_for_timeout(100)
            expect(page.locator('#formula-recover')).to_be_hidden()
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def test_formula_old_real_post_success_after_logout_cannot_restore_private_results(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            _save_formula_editor(page,base);expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            def hold(route):
                response=route.fetch();assert response.status==200;held.append((route,response))
            page.route('**/formula-checks',hold,times=1)
            page.locator('#formula-confirm').check();page.locator('#formula-run').click()
            for _ in range(50):
                if held:break
                page.wait_for_timeout(20)
            assert held
            assert context.request.post(base+'/api/auth/logout',headers={'Origin':base}).status==200
            page.locator('#research-list-refresh').click();expect(page.locator('#problem-form')).to_be_hidden()
            pending=page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')
            route,response=held.pop();route.fulfill(response=response)
            page.wait_for_timeout(100)
            expect(page.locator('#problem-form')).to_be_hidden();expect(page.locator('#formula-check-section')).to_be_hidden()
            expect(page.locator('#formula-results')).to_have_text('')
            assert page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')==pending
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def _formula_execute_ui(page):
    page.locator('#formula-confirm').check()
    with page.expect_response('**/formula-checks') as returned:page.locator('#formula-run').click()
    assert returned.value.status==200,returned.value.text()
    meta=returned.value.json()['data']
    expect(page.locator('#formula-result-ref')).to_have_text(meta['result_ref'])
    return meta


def test_formula_explicit_refresh_does_not_mix_another_window_revision_into_old_problem(server):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            body=_save_formula_editor(page,base);rid=body['research']['id'];original=page.locator('#original-input').input_value()
            other=context.new_page();other.goto(base+'/research/'+rid)
            expect(other.locator('#formula-editor-status')).to_contain_text('已按权限读取')
            other.locator('#formula-left-symbol-1-value').fill('9');other.locator('#original-input').fill('另一窗口保存的新问题与公式')
            _save_formula_editor(other,base)
            page.locator('#formula-refresh').click()
            expect(page.locator('#formula-status')).to_contain_text('版本')
            expect(page.locator('#formula-left-symbol-1-value')).to_have_value('3')
            expect(page.locator('#original-input')).to_have_value(original)
            expect(page.locator('#revision-label')).to_have_text('当前修订 1')
            expect(page.locator('#formula-run')).to_be_disabled()
            expect(page.locator('#status')).to_contain_text('表单仍基于修订 1')
        finally:context.close();browser.close()


@pytest.mark.parametrize('transition',['revision','new-task'])
def test_formula_real_history_native_tab_original_snapshot_result_time_and_readonly(server,transition):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context(viewport={'width':430,'height':932})
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            body=_save_formula_editor(page,base);rid=body['research']['id'];first=_formula_execute_ui(page)
            original=context.request.get(base+'/api/research/'+rid+'/formula-results/'+first['result_ref']).json()
            if transition=='revision':
                page.locator('#original-input').fill('新修订的原问题不能替换历史原式');page.locator('#formula-left-symbol-1-value').fill('5')
                _save_formula_editor(page,base)
            else:
                page.locator('#formula-refresh').click();expect(page.locator('#formula-editor-status')).to_contain_text('已按权限读取')
                second=_formula_execute_ui(page);assert second['result_ref']!=first['result_ref']
            page.reload();expect(page.locator('#task-history-items a')).not_to_have_count(0)
            link=page.locator('#task-history-items a[href="/research/'+rid+'?task_id='+first['task_id']+'"]')
            link.focus()
            with context.expect_page() as opened:page.keyboard.press('Enter')
            history=opened.value
            expect(history.locator('#view-context')).to_contain_text('历史流程')
            expect(history.locator('#formula-result-ref')).to_have_text(first['result_ref'])
            expect(history.locator('#formula-result-time')).to_have_attribute('datetime',first['formula_result_recorded_at'])
            expect(history.locator('#formula-left-symbol-1-value')).to_have_value('3')
            expect(history.locator('#formula-left-symbol-1-value')).to_be_disabled()
            expect(history.locator('#formula-confirm')).to_be_disabled()
            assert history.evaluate('window.opener===null')
            requests=[];history.on('request',lambda request:requests.append(request.url) if request.method=='POST' and '/api/research' in request.url else None)
            for identifier in ('formula-run','formula-recover','source-preview','source-confirm','task-start','task-cancel'):
                history.locator('#'+identifier).dispatch_event('click')
            history.locator('#problem-form').dispatch_event('submit');history.wait_for_timeout(50)
            assert requests==[]
            server['stop'](server['process']);server['start']();history.reload()
            expect(history.locator('#formula-result-ref')).to_have_text(first['result_ref'])
            expect(history.locator('#formula-result-time')).to_have_attribute('datetime',first['formula_result_recorded_at'])
            assert context.request.get(base+'/api/research/'+rid+'/formula-results/'+first['result_ref']).json()==original
            assert history.evaluate('document.documentElement.scrollWidth<=innerWidth')
            history.screenshot(path=str(server['root']/'formula-history-430.png'),full_page=True)
        finally:context.close();browser.close()


@pytest.mark.parametrize('stage',['formula-checks','source-approvals','source-tasks'])
def test_formula_fixed_or_historical_view_keeps_genuine_pending_intent_without_any_post(server,stage):
    server['stop'](server['process']);server['start'](d1_sources=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();seen=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            if stage!='formula-checks':page.locator('#confirmed').check()
            body=_save_formula_editor(page,base);rid=body['research']['id']
            if stage!='formula-checks':
                first=_formula_execute_ui(page);page.reload();expect(page.locator('#formula-result-ref')).to_have_text(first['result_ref'])
                page.locator('#source-query').fill('queue pending formula');page.locator('#source-preview').click();expect(page.locator('#source-confirm')).to_be_visible()
            def lose(route):
                response=route.fetch()
                try:
                    assert response.status==200,response.text();seen.append(response.json()['data'])
                finally:route.abort()
            page.route('**/'+stage,lose,times=1)
            if stage=='formula-checks':
                page.locator('#formula-confirm').check();page.locator('#formula-run').click();expect(page.locator('#formula-status')).to_contain_text('状态尚未确认')
                first=seen[0]
            else:
                page.locator('#source-confirm').click();expect(page.locator('#source-status')).to_contain_text('fetch')
            assert len(seen)==1
            storage=page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')
            assert any(key.startswith('structure-research-pending:formula-check:' if stage=='formula-checks' else 'structure-research-pending:source:'+stage+':') for key in storage)
            posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' and '/api/research' in request.url else None)
            page.goto(base+'/research/'+rid+'?task_id='+first['task_id'])
            expect(page.locator('#formula-result-ref')).to_have_text(first['result_ref'])
            expect(page.locator('#formula-left-symbol-1-value')).to_be_disabled()
            expect(page.locator('#formula-confirm')).to_be_disabled()
            for identifier in ('formula-run','formula-recover','source-preview','source-confirm','task-start','task-cancel'):
                page.locator('#'+identifier).dispatch_event('click')
            page.locator('#problem-form').dispatch_event('submit');page.wait_for_timeout(100)
            assert posts==[] and page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')==storage
            expect(page.locator('#view-context')).to_contain_text('历史流程' if stage=='source-tasks' else '固定任务只读')
        finally:context.close();browser.close()


@pytest.mark.parametrize('error_status',[401,404])
def test_formula_late_actual_result_access_error_cannot_clear_new_saved_problem(server,error_status):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();foreign=browser.new_context();held=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            body=_save_formula_editor(page,base);rid=body['research']['id'];first=_formula_execute_ui(page)
            login(foreign,base,'formula-other-owner@example.test')
            foreign_cookie='; '.join(item['name']+'='+item['value'] for item in foreign.cookies(base))
            def hold(route):
                headers={**route.request.headers,'cookie':foreign_cookie if error_status==404 else 'owned_negative=1'}
                response=route.fetch(headers=headers);assert response.status==error_status
                held.append((route,response))
            page.route('**/formula-results/'+first['result_ref'],hold,times=1)
            page.locator('#formula-refresh').click()
            for _ in range(50):
                if held:break
                page.wait_for_timeout(20)
            assert held
            page.locator('#formula-left-symbol-1-value').fill('7')
            page.locator('#original-input').fill('迟到的公式访问失败不能清除这份新问题')
            _save_formula_editor(page,base)
            notice=page.locator('#status').inner_text();pending=page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')
            route,response=held.pop();route.fulfill(response=response)
            page.wait_for_timeout(100)
            expect(page.locator('#original-input')).to_have_value('迟到的公式访问失败不能清除这份新问题')
            expect(page.locator('#formula-left-symbol-1-value')).to_have_value('7')
            expect(page.locator('#status')).to_have_text(notice)
            expect(page.locator('#formula-results')).to_have_text('')
            assert context.request.get(base+'/api/auth/me').status==200
            assert page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')==pending
        finally:
            for route,_ in held:route.abort()
            context.close();foreign.close();browser.close()


def test_formula_actual_auth503_preserves_all_editor_fields_and_real_pending(method_server):
    server=method_server
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            _save_formula_editor(page,base)
            def lose(route):
                response=route.fetch();assert response.status==200;route.abort()
            page.route('**/formula-checks',lose,times=1)
            page.locator('#formula-confirm').check();page.locator('#formula-run').click()
            expect(page.locator('#formula-status')).to_contain_text('状态尚未确认')
            page.locator('#formula-left-symbol-1-value').fill('7.00')
            snapshot=page.locator('#problem-form').evaluate("f=>Array.from(f.querySelectorAll('input,textarea,select')).map(e=>[e.id,e.value,e.checked])")
            storage=page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')
            assert any(key.startswith('structure-research-pending:formula-check:') for key in storage)
            server['stop'](server['process']);server['start'](auth_enabled=False)
            page.locator('#research-list-refresh').click()
            expect(page.locator('#status')).to_contain_text('暂时无法核对')
            assert page.locator('#problem-form').evaluate("f=>Array.from(f.querySelectorAll('input,textarea,select')).map(e=>[e.id,e.value,e.checked])")==snapshot
            assert page.evaluate('Object.fromEntries(Object.entries(sessionStorage))')==storage
            expect(page.locator('#formula-results')).to_have_text('');expect(page.locator('#formula-run')).to_be_disabled()
        finally:context.close();browser.close()


def test_formula_real_source_reader_keeps_old_revision_and_stop_policy_but_hides_withdrawn_result(server):
    from web.backend.tests.source_http_fixture import source_server
    server['stop'](server['process']);server['start'](d1_sources=True)
    with sync_playwright() as playwright,source_server() as (port,calls):
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            page.locator('#confirmed').check();body=_save_formula_editor(page,base);rid=body['research']['id']
            page.locator('#source-query').fill('queue source formula');page.locator('#source-preview').click();expect(page.locator('#source-confirm')).to_be_visible()
            with page.expect_response('**/source-tasks') as started:page.locator('#source-confirm').click()
            assert started.value.status==200
            source_task=started.value.json()['data']['task']['id']
            worker=server['run_source_worker'](source_task,port);assert worker.returncode==0,worker.stderr
            assert calls==['/discovery','/article']
            with sqlite3.connect(server['path']) as conn:
                row=conn.execute("SELECT id,payload FROM research_evidence_objects WHERE task_id=? AND kind='excerpts'",(source_task,)).fetchone();excerpt=json.loads(row[1])
                source=json.loads(conn.execute('SELECT payload FROM research_evidence_objects WHERE id=?',(excerpt['snapshot_id'],)).fetchone()[0])
                reference={'id':row[0],'revision':source['source_revision'],'content_digest':source['extracted_digest'],'provenance':'product_excerpt','locator':f"chars:{excerpt['start']}:{excerpt['end']}"}
            full=context.request.get(base+'/api/research/'+rid+'/formula-revisions/1').json()['data']['formula']
            draft={key:full[key] for key in ('input_origin','comparison_scope','left','right','requested_checks','sample_points')}
            for form in (draft['left'],draft['right']):
                if form:form.pop('id');form.pop('revision')
            draft['left']['source_refs']=[reference]
            problem={key:body['current_problem'][key] for key in ('entry','original_input','objective','summary','variables','constraints','unknowns','confirmed')};problem['formula_draft']=draft
            revised=context.request.post(base+'/api/research/'+rid+'/revisions',headers={'Origin':base,'Idempotency-Key':'formula-real-source-revision'},data={'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':{'expected_revision':1,'problem':problem}})
            assert revised.status==200,revised.text()
            page.goto(base+'/research/'+rid);expect(page.locator('#formula-editor-status')).to_contain_text('已按权限读取')
            meta=_formula_execute_ui(page)
            with sqlite3.connect(server['path']) as conn:conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(source_task,))
            page.locator('#formula-refresh').click();expect(page.locator('#formula-result-ref')).to_have_text(meta['result_ref'])
            with sqlite3.connect(server['path']) as conn:conn.execute('DELETE FROM research_evidence_objects WHERE id=?',(excerpt['snapshot_id'],))
            page.locator('#formula-refresh').click()
            expect(page.locator('#formula-editor-status')).to_contain_text('当前不可读取')
            expect(page.locator('#formula-results')).to_have_text('')
            expect(page.locator('#original-input')).to_be_enabled()
            expect(page.locator('#formula-run')).to_be_disabled()
            blocked=context.request.get(base+'/api/research/'+rid+'/formula-results/'+meta['result_ref'])
            assert blocked.status==200 and blocked.json()['data']['state']=='unavailable' and blocked.json()['data']['result'] is None
        finally:context.close();browser.close()



def test_formula_client_canonical_bounds_and_attestation_guards_from_actual_http_record(server):
    """Client-only malformed clones never substitute for executed mathematics."""
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context()
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for name in ('left','right'):page.locator('#formula-'+name+'-use-template').click()
            body=_save_formula_editor(page,base);rid=body['research']['id'];meta=_formula_execute_ui(page)
            snapshot=context.request.get(base+'/api/research/'+rid+'/formula-revisions/1').json()['data']
            result=context.request.get(base+'/api/research/'+rid+'/formula-results/'+meta['result_ref']).json()['data']
            source=(ROOT/'web/frontend/assets/research.js').read_text()
            block=source[source.index('  // Formula drafts are plain editor data'):source.index('  function status(message')]
            definitions='\n'.join(line.strip() for line in source.splitlines() if line.strip().startswith(('const validId =','const recordTime =')))
            payload={'rid':rid,'problem_digest':body['current_problem']['digest'],'snapshot':snapshot,'metadata':meta,'result':result}
            program="const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));const crypto=require('node:crypto').webcrypto;\n"+definitions+"\nconst formulaState={snapshot:{raw:payload.snapshot.formula,digest:payload.snapshot.formula_digest},scope:{rid:payload.rid,revision:1,problemDigest:payload.problem_digest}};\n"+block+r"""
(async()=>{
 await formulaValidateResult(payload.result,payload.metadata,payload.metadata.task_id);
 const pairs=[['3.00','3'],['1000','1E+3'],['0.0000001','1E-7'],['-0.0','0'],['1e-6','0.000001'],['12.300','12.3']];
 for(const [input,expected]of pairs)if(formulaNormalizeDecimal(input)!==expected)throw Error('decimal protocol mismatch');
 const bad=[v=>{v.result.execution_attested=true},v=>{v.metadata.formula_result_recorded_at=null},v=>{v.metadata.result_ref='00000000-0000-4000-8000-000000000000'},v=>{v.provenance.problem_digest='0'.repeat(64)},v=>{v.result.content_input_digest='0'.repeat(64)},v=>{v.result.outcomes.find(x=>x.check_kind==='bounded_numeric').relation='algebraic_identity'},v=>{v.result.formula_displays[0].original_display='changed'},v=>{v.result.source_references.push({id:'foreign'})},v=>{v.provenance.execution_state='ok';v.provenance.execution_attested=true;v.provenance.resource_guard='not_executed'}];
 if(!payload.result.provenance.execution_attested)bad.push(v=>{v.result.outcomes[0].status='passed'});
 for(const change of bad){const value=structuredClone(payload.result);change(value);let rejected=false;try{await formulaValidateResult(value,payload.metadata,payload.metadata.task_id)}catch{rejected=true}if(!rejected)throw Error('malformed proof accepted')}
 const hugeResult=structuredClone(payload.result);hugeResult.result.limitations=['x'.repeat(524289)];let outputLimit=false;
 try{await formulaValidateResult(hugeResult,payload.metadata,payload.metadata.task_id)}catch(error){outputLimit=error.message.includes('512KiB')}if(!outputLimit)throw Error('readable512 bound missing');
 const draft=structuredClone(payload.snapshot.formula);delete draft.executable;for(const side of [draft.left,draft.right]){delete side.id;delete side.revision;}
 validateFormulaDraft(draft);
 for(const side of [draft.left,draft.right]){
  side.expression=null;side.symbols=[];
 }
 validateFormulaDraft(draft);
 for(const side of [draft.left,draft.right]){
  side.original_display='x'.repeat(2048);side.symbols=Array.from({length:12},(_,i)=>({id:('symbol_'+i).padEnd(32,'x'),role:('role_'+i).padEnd(32,'x'),unit_id:'one',quantity:'ratio',value:'0.'+'0'.repeat(62)}));
  side.assumptions=Array.from({length:24},(_,i)=>({id:'condition_'+i,statement:'x'.repeat(400),declared_satisfied:null}));side.boundary_conditions=[];side.initial_conditions=[];
  side.source_refs=Array.from({length:20},(_,i)=>({id:'00000000-0000-4000-8000-'+i.toString(16).padStart(12,'0'),revision:1,content_digest:'a'.repeat(64),provenance:'product_excerpt',locator:'x'.repeat(300)}));
  const tree=depth=>depth?{op:'mul',left:tree(depth-1),right:tree(depth-1)}:{op:'const',value:'0.'+'0'.repeat(62)};
  side.expression={op:'eq',left:tree(5),right:tree(5)};
 }
 if(new TextEncoder().encode(formulaCanonical(draft)).length<=65536)throw Error('oversize test setup is not over64KiB');
 let inputLimit=false;try{validateFormulaDraft(draft)}catch(error){inputLimit=error.message.includes('64KiB')}if(!inputLimit)throw Error('readable64 bound missing');
 console.log('actual HTTP record accepted; decimal protocol, empty draft, malformed proof and64/512 bounds checked; no mathematical execution inferred');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
            checked=subprocess.run(['node','-e',program],input=json.dumps(payload),capture_output=True,text=True,timeout=20)
            assert checked.returncode==0,checked.stderr
            (server['root']/'formula-proof-observation.json').write_text(json.dumps({'result_ref':meta['result_ref'],'recorded_at':meta['formula_result_recorded_at'],'execution_state':result['provenance']['execution_state'],'execution_attested':result['provenance']['execution_attested'],'resource_guard':result['provenance']['resource_guard'],'pure_adapter_execution_attested':result['result']['execution_attested'],'outcomes':[{'check_kind':v['check_kind'],'status':v['status'],'relation':v['relation']} for v in result['result']['outcomes']]},indent=2))
        finally:context.close();browser.close()



@pytest.mark.parametrize('mode',['normal','abort','missing-ref','wrong-digest','wrong-task','wrong-ref','other-real-run'])
def test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement(server,mode):
    """Corrupt only the browser ACK after the actual HTTP operation committed."""
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();actual=[];sent=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for side in ('left','right'):page.locator('#formula-'+side+'-use-template').click()
            saved=_save_formula_editor(page,base);rid=saved['research']['id'];older=None
            if mode=='other-real-run':
                older=_formula_execute_ui(page)
                page.locator('#formula-refresh').click();expect(page.locator('#formula-editor-status')).to_contain_text('已按权限读取')
            page.on('request',lambda request:sent.append((request.headers.get('idempotency-key'),request.post_data)) if request.method=='POST' and request.url.endswith('/formula-checks') else None)
            if mode!='normal':
                def fault_after_commit(route):
                    response=route.fetch();assert response.status==200,response.text();body=response.json();actual.append(body['data'].copy())
                    if mode=='abort':route.abort();return
                    if mode=='missing-ref':body['data'].pop('result_ref')
                    elif mode=='wrong-digest':body['data']['formula_digest']='0'*64
                    elif mode=='wrong-task':body['data']['task_id']='00000000-0000-4000-8000-000000000000'
                    elif mode=='wrong-ref':body['data']['result_ref']='00000000-0000-4000-8000-000000000000'
                    elif mode=='other-real-run':body['data']=older
                    route.fulfill(response=response,json=body)
                page.route('**/formula-checks',fault_after_commit,times=1)
            def completed_ack_post(action):
                captured=[];responses=[];terminal=[]
                def capture(request):
                    if request.method=='POST' and request.url==base+'/api/research/'+rid+'/formula-checks' and not captured:captured.append(request)
                def headers(response):
                    if captured and response.request is captured[0]:responses.append(response)
                def finished(request):
                    if captured and request is captured[0] and not terminal:terminal.append(('requestfinished',request,time.monotonic()))
                def failed(request):
                    if captured and request is captured[0] and not terminal:terminal.append(('requestfailed',request,time.monotonic()))
                listeners=[('request',capture),('response',headers),('requestfinished',finished),('requestfailed',failed)]
                for event,callback in listeners:page.on(event,callback)
                deadline=time.monotonic()+15
                try:
                    action()
                    while not terminal:
                        remaining=deadline-time.monotonic()
                        assert remaining>0,'ACK body did not reach a terminal network event within15s'
                        page.wait_for_timeout(min(20,remaining*1000))
                    assert terminal[0][2]<=deadline,'ACK terminal network event exceeded15s'
                    assert captured and terminal[0][1] is captured[0],'ACK terminal event must identify the original POST'
                    assert terminal[0][0]=='requestfinished','ACK body requestfailed before completion'
                    assert len(responses)==1 and responses[0].request is captured[0],'ACK headers and finish must be the same request'
                    return responses[0]
                finally:
                    for event,callback in listeners:page.remove_listener(event,callback)
            page.locator('#formula-confirm').check()
            if mode=='abort':
                with page.expect_event('requestfailed',predicate=lambda request:request.url.endswith('/formula-checks')):page.locator('#formula-run').click()
            else:
                completed_ack_post(lambda:page.locator('#formula-run').click())
            if mode=='normal':expect(page.locator('#formula-result-ref')).to_have_text(re.compile(r'[0-9a-f-]{36}'))
            else:
                assert len(actual)==1
                expect(page.locator('#formula-status')).not_to_have_text(re.compile(r'^正在'))
            pending=page.evaluate("Object.fromEntries(Object.entries(sessionStorage).filter(([key])=>key.startsWith('structure-research-pending:formula-check:')))")
            with sqlite3.connect(server['path']) as conn:count=conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]
            expected=2 if mode=='other-real-run' else 1
            (server['root']/'ack-observation.json').write_text(json.dumps({'mode':mode,'actual_task_count':count,'post_count':len(sent),'pending_count':len(pending),'recover_visible':page.locator('#formula-recover').is_visible(),'status':page.locator('#formula-status').inner_text()},ensure_ascii=False,indent=2))
            assert count==expected and len(sent)==1
            if mode=='normal':assert len(pending)==0
            else:
                assert len(pending)==1,'Unconfirmed or request-mismatched ACK must keep the original key'
                expect(page.locator('#formula-recover')).to_be_visible()
                expect(page.locator('#formula-status')).to_contain_text('状态尚未确认')
                expect(page.locator('#problem-form')).to_be_visible()
                replay=completed_ack_post(lambda:page.locator('#formula-recover').click())
                assert replay.status==200
                assert replay.json()['data']['result_ref']==actual[0]['result_ref']
                assert replay.json()['data']['formula_result_recorded_at']==actual[0]['formula_result_recorded_at']
                expect(page.locator('#formula-result-ref')).to_have_text(actual[0]['result_ref'])
                assert len(sent)==2 and sent[0]==sent[1]
                assert page.evaluate("Object.keys(sessionStorage).filter(key=>key.startsWith('structure-research-pending:formula-check:')).length")==0
                with sqlite3.connect(server['path']) as conn:assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==expected
        finally:context.close();browser.close()



@pytest.mark.parametrize('mode',['current-logout','restored-session','new-draft','private-scope-changed'])
def test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key(server,mode):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();committed=[];held=[];metadata_statuses=[];auth_reads=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            for side in ('left','right'):page.locator('#formula-'+side+'-use-template').click()
            saved=_save_formula_editor(page,base);rid=saved['research']['id'];original=page.locator('#original-input').input_value()
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            def lose_auth_after_commit(route):
                response=route.fetch();assert response.status==200,response.text();committed.append(response.json()['data'])
                assert context.request.post(base+'/api/auth/logout',headers={'Origin':base}).status==200
                assert context.request.get(base+'/api/auth/me').status==401
                route.fulfill(response=response)
            page.route('**/formula-checks',lose_auth_after_commit,times=1)
            if mode!='current-logout':
                def hold401(route):
                    response=route.fetch();assert response.status==401;metadata_statuses.append(response.status);held.append((route,response))
                page.route('**/api/research/'+rid+'?task_id=*',hold401,times=1)
            page.on('response',lambda response:auth_reads.append(response.status) if response.url==base+'/api/auth/me' else None)
            page.locator('#formula-confirm').check()
            if mode=='current-logout':
                with page.expect_response(lambda response:response.status==401 and '/api/research/' in response.url):page.locator('#formula-run').click()
                expect(page.locator('#formula-status')).not_to_have_text(re.compile(r'^正在'))
            else:
                page.locator('#formula-run').click()
                for _ in range(100):
                    if held:break
                    page.wait_for_timeout(20)
                assert len(held)==1
                if mode in ('restored-session','new-draft'):
                    login(context,base)
                    assert context.request.get(base+'/api/auth/me').status==200
                    if mode=='new-draft':
                        page.locator('#formula-left-symbol-1-value').fill('7')
                        page.locator('#original-input').fill('恢复身份后的新草稿不可被迟到401清除')
                else:
                    page.locator('#research-list-refresh').click();expect(page.locator('#problem-form')).to_be_hidden()
                count_before_release=len(auth_reads)
                route,response=held.pop();route.fulfill(response=response)
                if mode=='restored-session':expect(page.locator('#formula-status')).to_contain_text('状态尚未确认')
                else:page.wait_for_timeout(100)
                if mode in ('new-draft','private-scope-changed'):assert len(auth_reads)==count_before_release,'stale ticket must not add auth reads'
            assert len(committed)==1
            pending=page.evaluate("Object.fromEntries(Object.entries(sessionStorage).filter(([key])=>key.startsWith('structure-research-pending:formula-check:')))")
            (server['root']/'ack-auth-observation.json').write_text(json.dumps({'mode':mode,'pending_count':len(pending),'form_visible':page.locator('#problem-form').is_visible(),'original_input':page.locator('#original-input').input_value(),'status':page.locator('#status').inner_text(),'actual_task_id':committed[0]['task_id'],'metadata_statuses':metadata_statuses,'auth_reads':auth_reads},ensure_ascii=False,indent=2))
            assert len(pending)==1
            if mode in ('current-logout','private-scope-changed'):
                expect(page.locator('#problem-form')).to_be_hidden()
                expect(page.locator('#original-input')).to_have_value('')
                expect(page.locator('#formula-check-section')).to_be_hidden()
                expect(page.locator('#formula-results')).to_have_text('')
                expect(page.locator('#status')).to_contain_text('登录')
                assert context.request.get(base+'/api/auth/me').status==401
            else:
                expect(page.locator('#problem-form')).to_be_visible()
                expect(page.locator('#original-input')).to_have_value('恢复身份后的新草稿不可被迟到401清除' if mode=='new-draft' else original)
                assert context.request.get(base+'/api/auth/me').status==200
            with sqlite3.connect(server['path']) as conn:assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==1
        finally:
            for route,_ in held:route.abort()
            context.close();browser.close()


def _formula_real_sso_cookie(browser,base,email):
    """Obtain a second credential through the mounted app's real SSO exchange."""
    from urllib.parse import parse_qs,urlsplit
    other=browser.new_context()
    try:
        login(other,base,email)
        start=other.request.get(base+'/api/sso/start',max_redirects=0)
        assert start.status==303
        query=parse_qs(urlsplit(start.headers['location']).query)
        issued=other.request.post(base+'/api/sso/issue',headers={'Origin':base},data={
            'audience':'structural-beta','state':query['state'][0],'nonce':query['nonce'][0]})
        assert issued.status==200
        exchanged=other.request.post(base+'/api/sso/exchange',headers={'Origin':base},data={
            'state':query['state'][0],'code':issued.json()['code']})
        assert exchanged.status==200
        assert other.request.get(base+'/api/auth/me').json()['user']['email']==email
        return next(cookie for cookie in other.cookies() if cookie['name']=='structural_beta_session')
    finally:other.close()


@pytest.mark.parametrize('mode',[
    'account-switch','same-owner-wrong-task','same-owner-new-draft','restored-owner',
    'late-root-new-draft','late-root-private-scope','credential-conflict','same-owner-dual',
    'restored-conflict','stale-conflict-draft','stale-conflict-private-scope',
])
def test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft(server,mode):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch();context=browser.new_context();held=[];committed=[];posts=[];reads=[];finished=[];metadata_statuses=[];root_statuses=[]
        try:
            base=server['base'];login(context,base);page=context.new_page();_open_formula_editor(page,base)
            page.locator('#original-input').fill('账户A已保存的私有问题')
            for side in ('left','right'):page.locator('#formula-'+side+'-use-template').click()
            saved=_save_formula_editor(page,base);rid=saved['research']['id'];original=page.locator('#original-input').input_value()
            expect(page.locator('#research-list-status')).to_contain_text('已读取 1')
            dual=mode in ('credential-conflict','same-owner-dual','restored-conflict','stale-conflict-draft','stale-conflict-private-scope')
            sso=_formula_real_sso_cookie(browser,base,'browser-a@example.test' if mode=='same-owner-dual' else 'browser-b@example.test') if dual else None
            assert context.request.get(base+'/api/auth/me').json()['user']['email']=='browser-a@example.test'
            def capture_post(route):
                response=route.fetch();assert response.status==200
                committed.append(response.json()['data']);posts.append(route.request.headers['idempotency-key']);held.append(('ack',route,response))
            page.route('**/formula-checks',capture_post,times=1)
            def capture_meta(route):
                response=route.fetch();held.append(('meta',route,response))
            if mode in ('restored-owner','restored-conflict','stale-conflict-draft','stale-conflict-private-scope'):
                page.route('**/api/research/'+rid+'?task_id=*',capture_meta,times=1)
            def capture_root(route):
                response=route.fetch();assert response.status==404;held.append(('root',route,response))
            if mode.startswith('late-root-'):page.route(base+'/api/research/'+rid,capture_root,times=1)
            page.on('request',lambda request:reads.append(request.url) if request.method=='GET' and request.url in (base+'/api/auth/me',base+'/api/research/'+rid) else None)
            page.on('requestfinished',lambda request:finished.append(request.url))
            page.on('response',lambda response:metadata_statuses.append(response.status) if response.url.startswith(base+'/api/research/'+rid+'?task_id=') else None)
            page.on('response',lambda response:root_statuses.append(response.status) if response.url==base+'/api/research/'+rid else None)
            def wait_held(kind):
                deadline=time.monotonic()+5
                while not any(item[0]==kind for item in held) and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert any(item[0]==kind for item in held),kind+' did not arrive'
                item=next(item for item in held if item[0]==kind);held.remove(item);return item[1:]
            def draft():
                page.locator('#formula-left-symbol-1-value').fill('7')
                page.locator('#original-input').fill('账户A的新草稿应保留')
            page.locator('#formula-confirm').check();page.locator('#formula-run').click();route,response=wait_held('ack')
            if dual:
                context.add_cookies([sso])
                auth=context.request.get(base+'/api/auth/me')
                assert auth.status==(200 if mode=='same-owner-dual' else 409)
                if mode!='same-owner-dual':assert auth.json()['error']=='credential_conflict'
            elif mode not in ('same-owner-wrong-task','same-owner-new-draft'):
                assert context.request.post(base+'/api/auth/logout',headers={'Origin':base}).status==200
                login(context,base,'browser-b@example.test')
                assert context.request.get(base+'/api/auth/me').json()['user']['email']=='browser-b@example.test'
                assert context.request.get(base+'/api/research/'+rid).status==404
            if mode=='same-owner-wrong-task':
                other=context.new_page();other.goto(base+'/research/'+rid)
                expect(other.locator('#formula-editor-status')).to_contain_text('已按权限读取')
                other.locator('#formula-left-symbol-1-value').fill('9')
                other.locator('#original-input').fill('另一窗口已保存的新问题，不得被可信核验装入旧表单')
                newer=_save_formula_editor(other,base);assert newer['current_problem']['revision']==2;other.close()
            if mode=='same-owner-new-draft':draft()
            if mode in ('same-owner-wrong-task','same-owner-new-draft'):
                ack=response.json();ack['data']['task_id']='00000000-0000-4000-8000-000000000000';route.fulfill(response=response,json=ack)
            else:route.fulfill(response=response)
            if mode in ('restored-owner','restored-conflict','stale-conflict-draft','stale-conflict-private-scope'):
                route,response=wait_held('meta')
                assert response.status==(404 if mode=='restored-owner' else 409)
                if mode!='restored-owner':assert response.json()['error']['code']=='AUTHORIZATION_STALE'
                if mode=='restored-owner':
                    assert context.request.post(base+'/api/auth/logout',headers={'Origin':base}).status==200;login(context,base)
                elif mode=='stale-conflict-private-scope':
                    page.locator('#research-list-refresh').click();expect(page.locator('#problem-form')).to_be_hidden()
                else:
                    context.clear_cookies(name='structural_beta_session')
                    assert context.request.get(base+'/api/auth/me').status==200
                    if mode=='stale-conflict-draft':draft()
                read_before=len(reads);route.fulfill(response=response)
            elif mode.startswith('late-root-'):
                route,response=wait_held('root')
                if mode=='late-root-private-scope':
                    page.locator('#research-list-refresh').click();expect(page.locator('#problem-form')).to_be_hidden()
                else:
                    assert context.request.post(base+'/api/auth/logout',headers={'Origin':base}).status==200;login(context,base);draft()
                read_before=len(reads);route.fulfill(response=response)
            deadline=time.monotonic()+5
            while not metadata_statuses and time.monotonic()<deadline:page.wait_for_timeout(20)
            assert metadata_statuses==[200 if mode=='same-owner-dual' else 409 if dual else 404]
            # The trusted gate may reject the page before the untrusted metadata
            # body is consumed. Wait for the real gate's body and resulting DOM.
            if mode in ('account-switch','same-owner-wrong-task','restored-owner'):
                while base+'/api/research/'+rid not in finished and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert base+'/api/research/'+rid in finished,'trusted root body did not finish'
            elif mode.startswith('late-root-'):
                # A draft/private-generation change stops the central read before
                # consuming its body; arrival must not clear or rebase that view.
                while not root_statuses and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert root_statuses==[404]
            elif mode in ('credential-conflict','restored-conflict'):
                while base+'/api/auth/me' not in finished and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert base+'/api/auth/me' in finished,'trusted auth body did not finish'
            elif mode not in ('stale-conflict-private-scope',):
                while not any(url.startswith(base+'/api/research/'+rid+'?task_id=') for url in finished) and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert any(url.startswith(base+'/api/research/'+rid+'?task_id=') for url in finished),'consumed metadata body did not finish'
            if mode in ('account-switch','credential-conflict'):expect(page.locator('#problem-form')).to_be_hidden()
            if mode in ('same-owner-wrong-task','restored-owner','restored-conflict'):expect(page.locator('#formula-status')).to_contain_text('状态尚未确认')
            if mode=='same-owner-dual':expect(page.locator('#formula-result-ref')).to_have_text(committed[0]['result_ref'])
            page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            formula_pending=page.evaluate("Object.entries(sessionStorage).filter(([key])=>key.startsWith('structure-research-pending:formula-check:')).map(([,value])=>JSON.parse(value))")
            assert len(formula_pending)==(0 if mode=='same-owner-dual' else 1)
            if formula_pending:assert formula_pending[0]['key']==posts[0]
            with sqlite3.connect(server['path']) as conn:assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==1
            cleared=mode in ('account-switch','credential-conflict','late-root-private-scope','stale-conflict-private-scope')
            facts={'mode':mode,'private_form_visible':page.locator('#problem-form').is_visible(),'pending':len(formula_pending),'actual_task_count':1,'browser_root_reads':reads.count(base+'/api/research/'+rid),'browser_auth_reads':reads.count(base+'/api/auth/me'),'input_preserved':page.locator('#original-input').input_value()==original,'metadata_statuses':metadata_statuses,'root_statuses':root_statuses}
            (server['root']/'ack-identity-facts.json').write_text(json.dumps(facts,indent=2))
            if cleared:
                expect(page.locator('#problem-form')).to_be_hidden();expect(page.locator('#original-input')).to_have_value('')
                expect(page.locator('#formula-check-section')).to_be_hidden();expect(page.locator('#formula-results')).to_have_text('')
            else:
                expect(page.locator('#problem-form')).to_be_visible()
                expect(page.locator('#original-input')).to_have_value('账户A的新草稿应保留' if mode in ('same-owner-new-draft','late-root-new-draft','stale-conflict-draft') else original)
            if mode in ('same-owner-new-draft','stale-conflict-draft','stale-conflict-private-scope'):
                assert reads.count(base+'/api/research/'+rid)==0
                if mode!='same-owner-new-draft':assert len(reads)==read_before,'stale metadata must not start an identity read'
            elif mode in ('account-switch','same-owner-wrong-task','restored-owner','late-root-new-draft','late-root-private-scope'):
                assert reads.count(base+'/api/research/'+rid)==1
            if mode in ('credential-conflict','restored-conflict'):assert reads.count(base+'/api/auth/me')==1
            if mode=='same-owner-wrong-task':
                expect(page.locator('#revision-label')).to_have_text('当前修订 1')
                expect(page.locator('#formula-left-symbol-1-value')).to_have_value('3')
                current_view=context.request.get(base+'/api/research/'+rid)
                assert current_view.status==200 and current_view.json()['data']['current_problem']['revision']==2
            if mode.startswith('late-root-'):assert len(reads)==read_before,'late trusted root must not trigger another read'
            if mode=='same-owner-dual':assert reads.count(base+'/api/auth/me')==0 and len(formula_pending)==0
        finally:
            for _,route,_ in held:route.abort()
            context.close();browser.close()
