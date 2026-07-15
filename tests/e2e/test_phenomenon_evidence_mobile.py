"""Real Chromium checks for the phenomenon evidence cards at narrow widths."""
from __future__ import annotations

import functools
import json
import threading
import unicodedata
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


pytest.importorskip("playwright")
pytestmark = pytest.mark.e2e

FRONTEND = Path(__file__).resolve().parents[2] / "web" / "frontend"
AXE = FRONTEND.parent / "phase-detector" / "node_modules" / "axe-core" / "axe.min.js"


def _serious_axe_violations(page) -> list[dict]:
    assert AXE.exists(), f"install locked axe-core first: {AXE}"
    if not page.evaluate("typeof window.axe !== 'undefined'"):
        page.add_script_tag(path=str(AXE))
    return page.evaluate(
        """async () => (await axe.run(document, {
          runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa']}
        })).violations.filter(item => ['critical','serious'].includes(item.impact))"""
    )


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/phenomenon/"):
            kb_id = parsed.path.rsplit("/", 1)[-1]
            suffix = f"&{parsed.query}" if parsed.query else ""
            self.path = f"/phenomenon.html?id={kb_id}{suffix}"
        super().do_GET()


@pytest.fixture(scope="module")
def phenomenon_origin():
    handler = functools.partial(_QuietHandler, directory=str(FRONTEND))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _isolate_page_routes(page):
    """Do not let parameterized stream routes survive into the next example."""
    try:
        yield
    finally:
        if not page.is_closed():
            page.unroute_all(behavior="ignoreErrors")


def _evidence(kind: str, label: str, score: float | None = None) -> dict:
    del score
    return {
        "schema_version": "evidence-envelope-v1",
        "evidence_level": "candidate",
        "candidate": {"status": "recorded", "kind": kind, "label": label, "score": None},
        "source": {
            "status": "recorded", "kind": "internal_kb",
            "label": "Structural internal candidate index", "url": None, "source_review": None,
        },
        "result": {
            "status": "recorded", "provenance": "INTERNAL_AI_SCREEN",
            "verdict": "INCONCLUSIVE", "summary": "Internal candidate; not validation.",
        },
        "independence": {
            "status": "recorded", "kind": "internal",
            "summary": "No external reviewer or independent team recorded.",
        },
        "counterexamples": {
            "status": "gap_recorded", "summary": "Boundaries and counterexamples remain untested.",
        },
        "ledger": {
            "status": "not_recorded", "claim_id": None, "version": None,
            "recorded_at": None, "artifact_sha256": None, "url": None,
        },
    }


def _payload(lang: str) -> dict:
    en = lang == "en"
    main_name = "Network cascade candidate" if en else "网络级联候选"
    similar_name = "Threshold response candidate" if en else "阈值响应候选"
    same_name = "Shared-label candidate" if en else "同标签候选"
    v2_name = "V2 cross-domain candidate" if en else "V2 跨域候选"
    return {
        "phenomenon": {
            "id": "p-main", "name": main_name, "domain": "Systems" if en else "系统科学",
            "type_id": "07", "description": "A record used to inspect candidate evidence boundaries." if en else "用于检查候选证据边界的现象记录。",
            "evidence": _evidence("phenomenon_kb_record_candidate", main_name),
        },
        "similar": [{
            "id": "p-sim", "name": similar_name, "domain": "Biology" if en else "生物学",
            "type_id": "04", "description": "Embedding-neighborhood candidate." if en else "嵌入邻域候选。",
            "retrieval_similarity": 0.8123, "evidence": _evidence("embedding_neighbor_candidate", similar_name),
        }],
        "same_structure": [{
            "id": "p-same", "name": same_name, "domain": "Economics" if en else "经济学",
            "type_id": "07", "description": "Candidate sharing an internal type label." if en else "共享内部类型标签的候选。",
            "evidence": _evidence("shared_type_label_candidate", same_name),
        }],
        "v2_pairs": [{
            "other_id": "p-v2", "other_name": v2_name,
            "other_domain": "Ecology" if en else "生态学",
            "retrieval_similarity": 0.7456,
            "candidate_reason": "Internal model rationale; pending source checks." if en else "内部模型理由；尚待来源核对。",
            "evidence": _evidence("v2_model_pair_candidate", v2_name),
        }],
    }


@pytest.mark.parametrize("width", [320, 390])
def test_phenomenon_evidence_cards_have_no_overflow_and_keep_outer_anchor_tab_target(
    page, phenomenon_origin: str, width: int,
) -> None:
    page.set_viewport_size({"width": width, "height": 812})
    page.emulate_media(reduced_motion="reduce")
    api_languages: list[str] = []

    def fulfill_phenomenon(route) -> None:
        lang = parse_qs(urlsplit(route.request.url).query).get("lang", ["zh"])[0]
        api_languages.append(lang)
        route.fulfill(
            status=200, content_type="application/json; charset=utf-8",
            body=json.dumps(_payload(lang), ensure_ascii=False),
        )

    page.route("**/api/phenomenon/**", fulfill_phenomenon)
    page.route(
        "**/api/auth/me**",
        lambda route: route.fulfill(status=401, content_type="application/json", body='{"error":"no session"}'),
    )
    page.route("https://plausible.bytedance.city/**", lambda route: route.abort())
    page.goto(
        f"{phenomenon_origin}/phenomenon.html?id=p-main&lang=zh",
        wait_until="domcontentloaded", timeout=20_000,
    )
    page.locator(".ph-hero__name").wait_for(state="visible")
    assert api_languages == ["zh"]

    page.locator("#site-menu-btn").click()
    page.locator("#site-menu-lang-toggle").click()
    page.keyboard.press("Escape")
    page.locator(".ph-hero__name").filter(has_text="Network cascade candidate").wait_for()
    assert api_languages[-1] == "en"
    assert "网络级联候选" not in page.locator("#ph-content").inner_text()

    assert page.locator(".evidence-envelope").count() == 4
    score_text = page.locator("#ph-content").inner_text()
    assert "Group rank" in score_text
    assert "not comparable across queries; not a probability" in score_text
    assert "%" not in score_text
    assert "V2 4" not in score_text and "V2 5" not in score_text
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page_width = page.locator(".ph-page").evaluate(
        """el => ({
          clientWidth: el.clientWidth,
          scrollWidth: el.scrollWidth,
          offenders: Array.from(el.querySelectorAll('*')).map(node => ({
            tag: node.tagName, cls: typeof node.className === 'string' ? node.className : '',
            clientWidth: node.clientWidth, scrollWidth: node.scrollWidth
          })).filter(row => row.scrollWidth > row.clientWidth + 1).slice(0, 12)
        })"""
    )
    assert page_width["scrollWidth"] <= page_width["clientWidth"] + 1, page_width

    outer_cards = page.locator("a.ph-cross__card, a.ph-v2-pair-card")
    assert outer_cards.count() == 3
    for index in range(outer_cards.count()):
        card = outer_cards.nth(index)
        assert card.locator(".evidence-envelope").count() == 1
        assert card.locator(
            ".evidence-envelope a, .evidence-envelope button, "
            ".evidence-envelope input, .evidence-envelope [tabindex]"
        ).count() == 0
        assert card.evaluate("el => el.scrollWidth <= el.clientWidth + 1")

    focused_cards: set[str] = set()
    for _ in range(40):
        page.keyboard.press("Tab")
        state = page.evaluate(
            """() => ({
              tag: document.activeElement && document.activeElement.tagName,
              cls: document.activeElement && document.activeElement.className,
              href: document.activeElement && document.activeElement.getAttribute('href')
            })"""
        )
        classes = state.get("cls") if isinstance(state.get("cls"), str) else ""
        if "ph-cross__card" in classes or "ph-v2-pair-card" in classes:
            assert state["tag"] == "A"
            focused_cards.add(state["href"])
    assert len(focused_cards) == 3
    assert _serious_axe_violations(page) == []


def _mapping_payload() -> dict:
    return {
        "schema_version": "candidate-mapping-v2",
        "evidence_level": "candidate",
        "generation_status": "generated",
        "structure_name": "Threshold-response candidate",
        "formula": "y = 1 / (1 + e^{-k(x-x_0)})",
        "candidate_rationale": "The records show a sharp response near a measurable threshold; the correspondence remains untested.",
        "parameter_mapping": [{
            "a_term": "load", "a_symbol": "x", "b_term": "candidate stressor",
            "b_symbol": "s", "note": "Compare distance from a threshold.",
        }],
        "validation_suggestions": [{
            "title": "Fit competing curves",
            "description": "Compare a threshold curve with linear and monotone baselines.",
            "scenario": "Use the same preregistered holdout split.",
            "failure_signal": "Reject the candidate if a simpler baseline predicts as well.",
        }],
        "alternative_explanations": ["Aggregation may create the apparent threshold."],
        "failure_conditions": ["Reject the candidate if the response disappears under another sampling window."],
        "why_worth_testing": "A small comparison can reject the candidate before a costly transfer.",
    }


@pytest.mark.parametrize("width", [320, 390])
def test_mapping_stream_never_renders_partial_semantics_and_share_modal_is_accessible(
    page, phenomenon_origin: str, width: int,
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.emulate_media(reduced_motion="reduce")
    mapping = _mapping_payload()

    def fulfill_mapping(route) -> None:
        request = route.request.post_data_json
        question = request.get("text_a")
        query_mode = isinstance(question, str)
        meta = {
            "schema_version": "mapping-stream-meta-v2",
            "a": {
                "id": "p-main", "name": "网络级联候选", "domain": "系统科学",
                "type_id": "07", "description": "主记录", "original_query": None,
            },
            "b": {
                "id": "__query__" if query_mode else "p-sim",
                "name": question[:80] if query_mode else "阈值响应候选",
                "domain": "你的问题" if query_mode else "生物学",
                "type_id": "query" if query_mode else "04",
                "description": "阈值附近响应为何突然变化" if query_mode else "候选记录",
                "original_query": question if query_mode else None,
            },
            "retrieval_similarity": 0.8123,
        }
        events = [
            ("meta", meta),
            ("text", {"content": '<h1 id="semantic-leak">机制已经确认</h1>', "total_length": 42}),
            ("done", {"mapping": mapping, "from_cache": False}),
        ]
        body = "".join(
            f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            for name, data in events
        )
        route.fulfill(status=200, content_type="text/event-stream; charset=utf-8", body=body)

    page.route("**/api/mapping/stream", fulfill_mapping)

    page.route(
        "**/api/phenomenon/**",
        lambda route: route.fulfill(
            status=200, content_type="application/json; charset=utf-8",
            body=json.dumps(_payload("zh"), ensure_ascii=False),
        ),
    )
    page.route(
        "**/api/auth/me**",
        lambda route: route.fulfill(status=401, content_type="application/json", body='{"error":"no session"}'),
    )
    page.route(
        "**/api/search**",
        lambda route: route.fulfill(
            status=200, content_type="application/json; charset=utf-8",
            body=json.dumps({
                "results": [{
                    "id": "p-more", "name": "另一检索候选", "domain": "经济学",
                    "type_id": "09", "description": "来自搜索结果的候选。", "score": 0.667,
                    "debug": "must-not-render",
                }]
            }, ensure_ascii=False),
        ),
    )
    page.route("https://plausible.bytedance.city/**", lambda route: route.abort())
    page.goto(
        f"{phenomenon_origin}/phenomenon.html?id=p-main&pair=p-sim&lang=zh",
        wait_until="domcontentloaded", timeout=20_000,
    )

    page.locator(".mapping-tests").wait_for(state="visible")
    visible = page.locator("#ph-mapping-slot").inner_text()
    assert "机制已经确认" not in visible
    assert page.locator("#semantic-leak").count() == 0
    assert "待验证候选，不是研究结论" in visible
    assert "还可能是什么" in visible
    assert "何时应否定或停止" in visible
    assert "可区分的验证计划" in visible
    assert "检索接近度" not in visible and "%" not in visible
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    preview = page.locator("#share-preview")
    assert preview.evaluate("el => el.getBoundingClientRect().height >= 44")
    preview.click()
    dialog = page.get_by_role("dialog", name="分享图片卡片")
    dialog.wait_for(state="visible")
    assert page.locator("body > :not(.share-modal)[inert]").count() > 0
    assert page.evaluate("document.body.style.overflow") == "hidden"
    page.keyboard.press("Shift+Tab")
    assert dialog.evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    assert dialog.count() == 0
    assert preview.evaluate("el => document.activeElement === el")
    assert _serious_axe_violations(page) == []

    question = "为什么阈值附近会突然变化？"
    query_results = [{
        "id": "p-more", "name": "另一检索候选", "domain": "经济学",
        "type_id": "09", "description": "来自搜索结果的候选。", "score": 0.667,
    }]
    private_link = page.evaluate(
        """({question, results}) => buildPrivatePhenomenonUrl({
          id: 'p-main', query: question, results, lang: 'zh', source: 'search_result'
        })""",
        {"question": question, "results": query_results},
    )
    assert question not in private_link and "from_query=" not in private_link
    page.goto(phenomenon_origin + private_link, wait_until="domcontentloaded", timeout=20_000)
    page.locator(".mapping-tests").wait_for(state="visible")
    heads = page.locator(".mapping-pair__head")
    assert heads.count() == 2
    assert "网络级联候选" in heads.nth(0).inner_text()
    assert unicodedata.normalize("NFKC", question) in heads.nth(1).inner_text()
    assert "用于检索的候选改写" in heads.nth(1).inner_text()
    assert "你的问题" in heads.nth(1).inner_text()
    assert "你的问题" not in heads.nth(0).inner_text()
    assert page.locator(".mapping-pair--query .mapping-pair__head--right").count() == 1
    more = page.locator("#ph-more-answers-slot .ph-cross__card")
    more.wait_for(state="visible")
    more_text = more.inner_text()
    assert "另一检索候选" in more_text
    assert "本组序位" in more_text and "不是概率" in more_text
    assert "67%" not in more_text
    assert "debug" not in more_text and "must-not-render" not in more_text
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert _serious_axe_violations(page) == []


@pytest.mark.parametrize("width", [320, 390])
def test_mapping_failure_is_announced_retryable_and_negative_score_stays_hidden(
    page, phenomenon_origin: str, width: int,
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.emulate_media(reduced_motion="reduce")
    mapping = _mapping_payload()
    attempts = {"automatic_failures": 0, "user_retry_successes": 0}
    page.add_init_script(script="""
      (() => {
        const nativeFetch = window.fetch.bind(window);
        window.__mappingUserRetry = false;
        window.fetch = (input, init = {}) => {
          const url = new URL(typeof input === 'string' ? input : input.url, location.origin);
          if (url.pathname === '/api/mapping/stream' && window.__mappingUserRetry) {
            window.__mappingUserRetry = false;
            const headers = new Headers(init.headers || {});
            headers.set('X-Structural-Test-User-Retry', '1');
            init = {...init, headers};
          }
          return nativeFetch(input, init);
        };
      })();
    """)

    def fulfill_mapping(route) -> None:
        is_user_retry = (
            route.request.headers.get("x-structural-test-user-retry") == "1"
        )
        if not is_user_retry:
            attempts["automatic_failures"] += 1
            events = [("error", {"message": "upstream_timeout"})]
        else:
            attempts["user_retry_successes"] += 1
            events = [
                ("meta", {
                    "schema_version": "mapping-stream-meta-v2",
                    "a": {
                        "id": "p-main", "name": "网络级联候选", "domain": "系统科学",
                        "type_id": "07", "description": "主记录", "original_query": None,
                    },
                    "b": {
                        "id": "p-sim", "name": "阈值响应候选", "domain": "生物学",
                        "type_id": "04", "description": "候选记录", "original_query": None,
                    },
                    "retrieval_similarity": -0.25,
                }),
                ("done", {"mapping": mapping, "from_cache": False}),
            ]
        body = "".join(
            f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            for name, data in events
        )
        route.fulfill(status=200, content_type="text/event-stream; charset=utf-8", body=body)

    page.route("**/api/mapping/stream", fulfill_mapping)
    page.route(
        "**/api/phenomenon/**",
        lambda route: route.fulfill(
            status=200, content_type="application/json; charset=utf-8",
            body=json.dumps(_payload("zh"), ensure_ascii=False),
        ),
    )
    page.route(
        "**/api/auth/me**",
        lambda route: route.fulfill(status=401, content_type="application/json", body='{"error":"no session"}'),
    )
    page.route("https://plausible.bytedance.city/**", lambda route: route.abort())
    page.goto(
        f"{phenomenon_origin}/phenomenon.html?id=p-main&pair=p-sim&lang=zh",
        wait_until="domcontentloaded", timeout=20_000,
    )

    alert = page.get_by_role("alert")
    alert.wait_for(state="visible")
    assert "暂时无法生成可复核的候选映射" in alert.inner_text()
    retry = page.get_by_role("button", name="重试生成")
    assert retry.evaluate("el => el.getBoundingClientRect().height >= 44")
    retry.evaluate("""el => el.addEventListener('click', () => {
      window.__mappingUserRetry = true;
    }, {capture: true, once: true})""")
    retry.focus()
    page.keyboard.press("Enter")
    page.locator(".mapping-tests").wait_for(state="visible")
    assert attempts["automatic_failures"] >= 1
    assert attempts["user_retry_successes"] == 1
    visible = page.locator("#ph-mapping-slot").inner_text()
    assert "检索接近度" not in visible and "-25%" not in visible

    page.evaluate("""() => {
      window.__shareTexts = [];
      const original = CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
        window.__shareTexts.push(String(text));
        return original.call(this, text, ...args);
      };
    }""")
    page.locator("#share-preview").click()
    share_texts = page.evaluate("window.__shareTexts")
    assert not any("检索接近度" in text or "-25%" in text for text in share_texts)
    assert any("候选映射 · 不是概率" in text for text in share_texts)
    page.keyboard.press("Escape")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert _serious_axe_violations(page) == []
