"""Real Chromium contract for the evidence-first discovery queue."""
from __future__ import annotations

import functools
import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


pytest.importorskip("playwright")
pytestmark = pytest.mark.e2e
FRONTEND = Path(__file__).resolve().parents[2] / "web" / "frontend"
AXE = Path(__file__).resolve().parents[2] / "web" / "phase-detector" / "node_modules" / "axe-core" / "axe.min.js"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


@pytest.fixture(scope="module")
def discovery_origin():
    handler = functools.partial(_QuietHandler, directory=str(FRONTEND))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _evidence(label: str) -> dict:
    return {
        "schema_version": "evidence-envelope-v1", "evidence_level": "candidate",
        "candidate": {"status": "recorded", "kind": "discovery_candidate", "label": label, "score": None},
        "source": {"status": "not_recorded", "kind": "not_recorded", "label": None, "url": None, "source_review": None},
        "result": {"status": "not_recorded", "provenance": "NOT_TESTED", "verdict": "NOT_TESTED", "summary": None},
        "independence": {"status": "not_recorded", "kind": "not_recorded", "summary": None},
        "counterexamples": {"status": "gap_recorded", "summary": "Common shock remains an alternative."},
        "ledger": {"status": "not_recorded", "claim_id": None, "version": None, "recorded_at": None, "artifact_sha256": None, "url": None},
    }


def _candidate(rank: int, tier: str) -> dict:
    cid = f"discovery-{rank:016x}"
    return {
        "schema_version": "discovery-candidate-v2", "discovery_id": cid,
        "candidate_family_id": "pair-browser", "family_variant_count": 1,
        "rank": rank, "tier": tier, "pipeline": "V2" if tier == "priority_review" else None,
        "pair": {
            "a": {"id": "a-1", "name": {"zh": "系统甲", "en": "System A"}, "domain": {"zh": "领域甲", "en": "Domain A"}},
            "b": {"id": f"b-{rank}", "name": {"zh": "系统乙", "en": "System B"}, "domain": {"zh": "领域乙", "en": "Domain B"}},
        },
        "candidate_summary": {"zh": "比较系统甲与系统乙；当前仅为候选。", "en": "Compare System A and System B; this remains a candidate."},
        "candidate_equations": ["dx/dt = f(x)"], "candidate_variable_mapping": {"状态": "state"},
        "evidence_language": "zh_only",
        "provenance": {"status": "not_started", "recorded_source_count": 0, "independent_review_complete": False, "systematic_search_recorded": False},
        "readiness": {"status": "blocked", "ready_for_preregistration": False, "blockers": [
            "source_review", "dataset_record", "primary_metric", "preregistered_stop_rule",
        ]},
        "validation_plan": {
            "status": "draft_requires_user_completion",
            "hypothesis": {"zh": "检验候选映射。", "en": "Test the candidate mapping."},
            "data_needed": {"zh": "补齐来源与样本。", "en": "Add sources and samples."},
            "baseline": {"zh": "比较无迁移基线。", "en": "Compare a no-transfer baseline."},
            "primary_metric": {"zh": "待定义", "en": "To be defined"},
            "failure_condition": {"zh": "基线相同则拒绝。", "en": "Reject if the baseline is equal."},
            "validation_gaps": [
                {"gap_id": "source_support_not_reviewed", "label": {"zh": "来源尚未独立复核。", "en": "Sources are not independently reviewed."}},
                {"gap_id": "candidate_equation_not_expert_reviewed", "label": {"zh": "候选方程尚未经过专家复核。", "en": "The equation is not expert-reviewed."}},
                {"gap_id": "variable_mapping_not_expert_reviewed", "label": {"zh": "变量对应尚未经过专家复核。", "en": "The mapping is not expert-reviewed."}},
                {"gap_id": "competing_explanations_not_tested", "label": {"zh": "其他解释尚未检验。", "en": "Alternatives are not tested."}},
                {"gap_id": "dataset_and_sampling_not_recorded", "label": {"zh": "数据和抽样尚未记录。", "en": "Data and sampling are not recorded."}},
                {"gap_id": "baseline_and_stop_rule_not_preregistered", "label": {"zh": "研究方案尚未公开锁定。", "en": "The study plan is not publicly locked."}},
            ],
            "preregistered": False,
        },
        "analyze_url": "/analyze?a_id=a-1&id=b-1", "evidence": _evidence("candidate"),
    }


def _payload(priority_count: int, pool_count: int) -> dict:
    priority = [_candidate(rank, "priority_review") for rank in range(1, priority_count + 1)]
    pool = [_candidate(rank, "candidate_pool") for rank in range(101, 101 + pool_count)]
    return {
        "count": len(priority), "discoveries": priority,
        "tier2_count": len(pool), "tier2": pool,
        "stats": {
            "total_candidates": len(priority) + len(pool),
            "priority_review": len(priority), "candidate_pool": len(pool),
            "candidate_families": len(priority) + len(pool),
            "source_backed": 0, "ready_for_preregistration": 0,
        },
    }


def _route_product_dependencies(page, payload: dict, *, delay: float = 0) -> None:
    def fulfill_discoveries(route) -> None:
        if delay:
            time.sleep(delay)
        route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(payload, ensure_ascii=False),
        )

    page.route("**/api/discoveries", fulfill_discoveries)
    page.route(
        "**/api/auth/me**",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"no session"}'
        ),
    )


def _route_daily_dependencies(page) -> None:
    candidates = [_candidate(rank, "priority_review") for rank in range(1, 4)]
    page.route(
        "**/api/daily**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"date": "2026-07-13", "lang": "zh", "discoveries": candidates},
                ensure_ascii=False,
            ),
        ),
    )
    page.route(
        "**/api/suggest**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"suggestions":[]}'
        ),
    )
    page.route(
        "**/api/auth/me**",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"no session"}'
        ),
    )


@pytest.mark.parametrize("width", [320, 390])
def test_daily_candidate_cards_are_scoreless_accessible_and_deep_linked(
    page, discovery_origin: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    _route_daily_dependencies(page)
    page.goto(f"{discovery_origin}/learn.html", wait_until="domcontentloaded", timeout=20_000)
    page.locator("#daily-grid .disc-card").first.wait_for()

    cards = page.locator("#daily-grid .disc-card")
    assert cards.count() == 3
    assert page.locator("#daily-grid .disc-card__score").count() == 0
    assert all("/discoveries?candidate=" in (card.get_attribute("href") or "") for card in cards.all())
    assert all("待验证候选联系" in (card.get_attribute("aria-label") or "") for card in cards.all())
    assert "不能证明两边机制相同" in page.locator("#daily-grid").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    first = cards.first
    first.focus()
    assert first.evaluate("el => el.matches(':focus-visible')")
    box = first.bounding_box()
    assert box is not None and box["height"] >= 44

    page.evaluate("window.i18n.setLang('en')")
    page.locator("#daily-grid .disc-card", has_text="Candidate for validation").first.wait_for()
    assert "does not establish a shared mechanism" in page.locator("#daily-grid").inner_text()


@pytest.mark.parametrize("width", [320, 390])
def test_discovery_queue_renders_plan_without_hype_or_overflow(page, discovery_origin: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    priority = _candidate(1, "priority_review")
    pool = _candidate(2, "candidate_pool")
    payload = {
        "count": 1, "discoveries": [priority], "tier2_count": 1, "tier2": [pool],
        "stats": {"total_candidates": 2, "priority_review": 1, "candidate_pool": 1, "candidate_families": 2, "source_backed": 0, "ready_for_preregistration": 0},
    }
    _route_product_dependencies(page, payload)
    page.goto(f"{discovery_origin}/discoveries.html", wait_until="domcontentloaded", timeout=20_000)
    page.locator(".disc-item").wait_for()
    assert page.locator(".disc-item__score").count() == 0
    assert "建议投稿" not in page.locator(".disc-page").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    expand = page.locator(".disc-item__expand").first
    expand.focus()
    page.keyboard.press("Enter")
    assert expand.get_attribute("aria-expanded") == "true"
    page.locator(".disc-plan").wait_for(state="visible")
    assert "尚不能公开锁定研究方案" in page.locator(".disc-readiness").inner_text()
    with page.expect_download() as download_info:
        page.locator(".disc-plan-download").first.click()
    download = download_info.value
    assert download.suggested_filename == "structural-validation-discovery-0000000000000001.md"
    content = Path(download.path()).read_text(encoding="utf-8")
    assert "Evidence level: candidate" in content and "Preregistered: no" in content
    assert "dx/dt = f\\(x\\)" in content
    assert "状态 → state" in content
    assert "NOT_TESTED" in content and "已记录来源条目: 0" in content

    page.evaluate("window.i18n.setLang('en')")
    page.locator(".disc-plan__status", has_text="Not publicly locked").wait_for()
    assert "this remains a candidate" in page.locator(".disc-item__verdict").inner_text()
    page.locator('[data-tier="t2"]').click()
    page.locator(".disc-t2-item").wait_for()
    assert page.locator(".disc-t2-item__sim").count() == 0
    assert page.locator(".disc-t2-item .disc-plan-download").count() == 1
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    for control in page.locator("button:visible, a:visible").all():
        box = control.bounding_box()
        assert box is not None and box["height"] >= 43.5, (
            control.get_attribute("class"), box
        )


@pytest.mark.parametrize(
    "tier,target_index,expected_tab",
    [("priority_review", 20, "a"), ("candidate_pool", 20, "t2")],
)
def test_stable_deep_link_waits_for_data_and_follows_candidate_across_queues(
    page, discovery_origin: str, tier: str, target_index: int, expected_tab: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    payload = _payload(25, 25)
    rows = payload["discoveries"] if tier == "priority_review" else payload["tier2"]
    target_id = rows[target_index]["discovery_id"]
    page.add_init_script("""
      window.addEventListener('DOMContentLoaded', () => setTimeout(() => {
        if (window.i18n && window.i18n.setLang) window.i18n.setLang('en');
      }, 0));
    """)
    _route_product_dependencies(page, payload, delay=0.15)
    page.goto(
        f"{discovery_origin}/discoveries.html?candidate={target_id}",
        wait_until="domcontentloaded", timeout=20_000,
    )

    target = page.locator(f"#candidate-{target_id}")
    target.wait_for(state="visible")
    assert page.locator(".disc-link-notice").count() == 0
    assert "active" in (page.locator(f'[data-tier="{expected_tab}"]').get_attribute("class") or "")
    if tier == "priority_review":
        assert target.locator(".disc-item__expand").get_attribute("aria-expanded") == "true"
        page.wait_for_function("document.activeElement?.classList.contains('disc-item__expand')")
    else:
        page.wait_for_function("document.activeElement?.matches('.disc-t2-evidence > summary')")


def test_unknown_candidate_link_is_reported_only_after_catalog_load(page, discovery_origin: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _route_product_dependencies(page, _payload(2, 2), delay=0.1)
    page.goto(
        f"{discovery_origin}/discoveries.html?candidate=discovery-ffffffffffffffff",
        wait_until="domcontentloaded", timeout=20_000,
    )
    notice = page.locator(".disc-link-notice")
    assert notice.count() == 1
    assert "不可用" in notice.inner_text() or "unavailable" in notice.inner_text()


def test_pagination_announces_progress_restores_expansion_and_focuses_new_page(
    page, discovery_origin: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _route_product_dependencies(page, _payload(25, 25))
    page.goto(f"{discovery_origin}/discoveries.html", wait_until="domcontentloaded", timeout=20_000)
    page.locator(".disc-item").first.wait_for()

    assert page.locator(".disc-item").count() == 12
    assert "12 / 25" in page.locator(".disc-pagination-status").inner_text()
    first_expand = page.locator(".disc-item__expand").first
    first_expand.click()
    page.locator('[data-load-more="priority"]').click()
    page.locator('.disc-item[data-list-index="23"]').wait_for()
    page.wait_for_function("document.activeElement?.closest('[data-list-index=\"12\"]') !== null")
    assert page.locator(".disc-item").count() == 24
    assert "24 / 25" in page.locator(".disc-pagination-status").inner_text()

    page.locator('[data-tier="t2"]').click()
    page.locator(".disc-t2-item").first.wait_for()
    page.locator('[data-tier="a"]').click()
    assert page.locator(".disc-item__expand").first.get_attribute("aria-expanded") == "true"

    page.locator('[data-tier="t2"]').click()
    page.locator('[data-load-more="candidate-pool"]').click()
    page.locator('.disc-t2-item[data-list-index="23"]').wait_for()
    page.wait_for_function("document.activeElement?.closest('[data-list-index=\"12\"]') !== null")
    assert "24 / 25" in page.locator(".disc-pagination-status").inner_text()


def test_mobile_history_drawer_is_inert_when_closed_and_traps_focus_when_open(
    page, discovery_origin: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.add_init_script(
        """localStorage.setItem('cookie_consent_v1', JSON.stringify({
          version: 1,
          essential: true,
          analytics: false,
          marketing: false,
          source: 'e2e',
          timestamp: new Date(0).toISOString()
        }))"""
    )
    _route_product_dependencies(page, _payload(1, 1))
    page.goto(f"{discovery_origin}/discoveries.html", wait_until="domcontentloaded", timeout=20_000)
    page.locator(".disc-item").first.wait_for()
    sidebar = page.locator("#history-sidebar")
    trigger = page.locator("#history-sidebar-trigger")
    assert sidebar.get_attribute("aria-hidden") == "true"
    assert sidebar.get_attribute("inert") == ""
    trigger.click()
    assert sidebar.get_attribute("aria-hidden") == "false"
    assert trigger.get_attribute("aria-expanded") == "true"
    page.wait_for_function("document.querySelector('#history-sidebar').contains(document.activeElement)")
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.querySelector('#history-sidebar').contains(document.activeElement)")
    page.keyboard.press("Escape")
    assert sidebar.get_attribute("aria-hidden") == "true"
    assert trigger.get_attribute("aria-expanded") == "false"
    page.wait_for_function("document.activeElement === document.querySelector('#history-sidebar-trigger')")


def test_downloaded_plan_escapes_html_markdown_links_and_heading_injection(
    page, discovery_origin: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    candidate = _candidate(1, "priority_review")
    candidate["pair"]["a"]["name"]["zh"] = "<script>alert(1)</script> [click](javascript:alert(1))"
    candidate["validation_plan"]["hypothesis"]["zh"] = "safe\n## injected ![x](javascript:alert(2))"
    candidate["candidate_equations"] = ["x=y\n## equation injection [x](javascript:alert(3))"]
    candidate["candidate_variable_mapping"] = {"<left>": "right\n# injected"}
    payload = _payload(0, 1)
    payload.update(count=1, discoveries=[candidate], tier2_count=0, tier2=[])
    payload["stats"].update(total_candidates=1, priority_review=1, candidate_pool=0, candidate_families=1)
    _route_product_dependencies(page, payload)
    page.goto(f"{discovery_origin}/discoveries.html", wait_until="domcontentloaded", timeout=20_000)
    page.locator(".disc-item").first.wait_for()
    page.locator(".disc-item__expand").click()
    with page.expect_download() as download_info:
        page.locator(".disc-plan-download").click()
    content = Path(download_info.value.path()).read_text(encoding="utf-8")
    assert "<script>" not in content
    assert "](javascript:" not in content
    assert "![x](" not in content
    assert "\n## injected" not in content
    assert "&lt;script&gt;" in content
    assert "javascript:alert\\(3\\)" in content
    assert "&lt;left&gt; → right" in content


def test_load_failure_replaces_all_skeletons_and_rerenders_in_english(page, discovery_origin: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.route(
        "**/api/discoveries",
        lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"unavailable"}'),
    )
    page.route("**/api/auth/me**", lambda route: route.fulfill(status=401, body='{"error":"no session"}'))
    page.goto(f"{discovery_origin}/discoveries.html", wait_until="domcontentloaded", timeout=20_000)
    retry = page.locator("#disc-retry")
    retry.wait_for()
    assert page.locator('[class*="disc-skeleton"]').count() == 0
    assert retry.bounding_box()["height"] >= 43.5
    page.evaluate("window.i18n.setLang('en')")
    page.locator("#disc-retry", has_text="Retry").wait_for()
    assert "temporarily unavailable" in page.locator("#disc-hero-stats").inner_text()


def test_share_modal_has_name_traps_focus_cleans_up_and_restores_opener(page, discovery_origin: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _route_product_dependencies(page, _payload(1, 1))
    page.goto(f"{discovery_origin}/discoveries.html", wait_until="domcontentloaded", timeout=20_000)
    page.locator(".disc-item__expand").click()
    opener = page.locator(".disc-item .share-actions__btn", has_text="生成图片卡片")
    opener.click()
    dialog = page.get_by_role("dialog", name="分享图片卡片")
    dialog.wait_for()
    close = dialog.get_by_role("button", name="关闭图片卡片预览")
    assert page.evaluate("document.activeElement === document.querySelector('.share-modal__close')")
    assert page.locator("main[inert]").count() == 1
    assert page.evaluate("document.body.style.overflow === 'hidden'")
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.querySelector('.share-modal__panel').contains(document.activeElement)")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement === document.querySelector('.share-modal__close')")
    page.keyboard.press("Escape")
    assert dialog.count() == 0
    assert page.evaluate("document.activeElement?.textContent.includes('生成图片卡片')")
    assert page.locator("main[inert]").count() == 0
    assert page.evaluate("document.body.style.overflow === ''")

    opener.click()
    close = page.get_by_role("button", name="关闭图片卡片预览")
    close.click()
    assert page.locator(".share-modal").count() == 0
    focused_before = page.evaluate("document.activeElement?.className")
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement?.className") == focused_before


def test_discovery_four_queue_states_have_no_serious_axe_violations(page, discovery_origin: str) -> None:
    assert AXE.exists(), f"install locked axe-core first: {AXE}"
    page.set_viewport_size({"width": 390, "height": 844})
    page.emulate_media(reduced_motion="reduce")
    _route_product_dependencies(page, _payload(2, 2))
    page.goto(f"{discovery_origin}/discoveries.html", wait_until="domcontentloaded", timeout=20_000)
    page.locator(".disc-item").first.wait_for()
    page.add_script_tag(path=str(AXE))

    def assert_clean() -> None:
        page.wait_for_timeout(550)
        violations = page.evaluate("""async () => (await axe.run(document, {
          runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa']}
        })).violations.filter(v => ['critical','serious'].includes(v.impact))""")
        assert violations == []

    assert_clean()
    page.locator(".disc-item__expand").first.click()
    assert_clean()
    page.locator('[data-tier="t2"]').click()
    page.locator(".disc-t2-item").first.wait_for()
    assert_clean()
    page.locator(".disc-t2-evidence > summary").first.click()
    assert_clean()
