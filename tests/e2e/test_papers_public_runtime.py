"""Real-browser acceptance matrix for the historical papers surface."""

from __future__ import annotations

import functools
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


pytest.importorskip("playwright")
from playwright.sync_api import Browser, Page, expect  # noqa: E402


pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "web" / "frontend"
MANIFEST = json.loads(
    (FRONTEND / "assets" / "data" / "papers-manifest.json").read_text(encoding="utf-8")
)
RECORDS = [paper for group in MANIFEST["groups"] for paper in group["papers"]]
SLUGS = frozenset(paper["slug"] for paper in RECORDS)
CONTRACT = MANIFEST["meta"]["result_contract"]
AXE = ROOT / "web" / "phase-detector" / "node_modules" / "axe-core" / "axe.min.js"


class _PapersHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return

    def _serve_404(self) -> None:
        body = (Path(self.directory) / "404.html").read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = unquote(urlsplit(self.path).path)
        if path == "/papers":
            self.path = "/papers.html"
        elif path.startswith("/paper/"):
            slug = path.removeprefix("/paper/")
            if slug not in SLUGS:
                self._serve_404()
                return
            self.path = "/paper.html"
        elif path.startswith("/api/"):
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"not found"}')
            return
        super().do_GET()


@pytest.fixture(scope="module")
def papers_origin():
    handler = functools.partial(_PapersHandler, directory=str(FRONTEND))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _new_page(browser: Browser, width: int = 390) -> tuple[Page, object]:
    context = browser.new_context(viewport={"width": width, "height": 844})
    page = context.new_page()
    page.add_init_script("localStorage.clear()")
    page.route("https://**", lambda route: route.abort())
    return page, context


def _serious_axe_violations(page: Page) -> list[dict]:
    assert AXE.is_file(), f"locked axe-core asset is missing: {AXE}"
    page.add_script_tag(path=str(AXE))
    return page.evaluate(
        """async () => (await axe.run(document, {
          runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}
        })).violations.filter(item => ['serious', 'critical'].includes(item.impact))
          .map(item => ({id: item.id, targets: item.nodes.map(node => node.target)}))"""
    )


@pytest.mark.parametrize("width", [375, 390, 430])
def test_index_mobile_keyboard_language_and_axe(
    browser: Browser, papers_origin: str, width: int,
) -> None:
    page, context = _new_page(browser, width)
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        page.goto(
            f"{papers_origin}/papers?lang=en", wait_until="commit", timeout=15_000,
        )
        expect(page.locator(".paper-card")).to_have_count(20, timeout=15_000)
        initial_language = page.evaluate(
            """() => ({
              href: location.href,
              search: location.search,
              htmlLang: document.documentElement.lang,
              runtimeLang: window.i18n && window.i18n.getLang(),
              storedLang: localStorage.getItem('structural.lang'),
              readyState: document.readyState,
            })"""
        )
        assert initial_language["htmlLang"] == "en", json.dumps(initial_language)
        assert initial_language["runtimeLang"] == "en", json.dumps(initial_language)
        page.wait_for_function(
            "window.i18n.t('page.papers.title') !== 'page.papers.title'",
            timeout=15_000,
        )
        expect(page.locator("#papers-heading")).to_have_text(
            "Twenty historical research items"
        )
        expect(page.locator(".papers-group__title").first).to_have_text(
            MANIFEST["groups"][0]["title_en"]
        )
        expect(page.locator(".paper-card__title").first).to_have_text(
            RECORDS[0]["title_en"]
        )
        expect(
            page.locator(".paper-result__decision > div").nth(1).locator("p").first
        ).to_have_text(CONTRACT["boundary_en"])
        expect(page.locator(".paper-result__details summary").first).to_have_text(
            "Inspect evidence fields"
        )
        expect(page.locator("#papers-stats")).to_have_attribute(
            "aria-label", "Historical material composition"
        )
        expect(page.locator("#papers-filter")).to_have_attribute(
            "aria-label", "Historical material type filters"
        )
        expect(page.locator(".papers-footer-note")).to_have_attribute(
            "aria-label", "Historical material boundary"
        )
        assert page.locator("#papers-stats .papers-stat__num").all_inner_texts() == [
            "20", "14", "5", "1",
        ]
        hrefs = page.locator(".paper-card__title").evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('href'))"
        )
        assert len(hrefs) == len(set(hrefs)) == 20
        assert all(href.startswith("/paper/") for href in hrefs)
        assert page.locator(".paper-result__details[open]").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")

        filters = page.locator(".papers-filter__btn")
        filters.first.focus()
        page.keyboard.press("ArrowRight")
        expect(filters.nth(1)).to_be_focused()
        expect(filters.nth(1)).to_have_attribute("aria-pressed", "true")
        assert page.locator(".papers-group:not([hidden]) .paper-card").count() == 1
        page.keyboard.press("End")
        expect(filters.last).to_be_focused()
        assert page.locator(".papers-group:not([hidden]) .paper-card").count() == 1
        page.keyboard.press("Home")
        expect(filters.first).to_be_focused()
        assert page.locator(".papers-group:not([hidden]) .paper-card").count() == 20

        first_details = page.locator(".paper-result__details").first
        first_details.locator("summary").click()
        expect(first_details).to_have_attribute("open", "")

        page.evaluate("window.i18n.setLang('zh')")
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        expect(page.locator("#papers-heading")).to_have_text("20 项历史研究材料")
        expect(page.locator(".papers-group__title").first).to_have_text(
            MANIFEST["groups"][0]["title_zh"]
        )
        expect(page.locator(".paper-card__title").first).to_have_text(
            RECORDS[0]["title_zh"]
        )
        expect(
            page.locator(".paper-result__decision > div").nth(1).locator("p").first
        ).to_have_text(CONTRACT["boundary_zh"])
        expect(first_details.locator("summary")).to_have_text("核对证据字段")
        expect(first_details).to_have_attribute("open", "")
        expect(page.locator("#papers-stats")).to_have_attribute(
            "aria-label", "历史材料构成"
        )
        expect(page.locator("#papers-filter")).to_have_attribute(
            "aria-label", "历史材料类型筛选"
        )
        expect(page.locator(".papers-footer-note")).to_have_attribute(
            "aria-label", "历史材料边界"
        )

        page.evaluate("window.i18n.setLang('en')")
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#papers-heading")).to_have_text(
            "Twenty historical research items"
        )
        expect(filters.first).to_have_text("All 20 items")
        expect(first_details.locator("summary")).to_have_text("Inspect evidence fields")
        expect(first_details).to_have_attribute("open", "")

        filter_heights = filters.evaluate_all(
            "nodes => nodes.map(node => node.getBoundingClientRect().height)"
        )
        summary_heights = page.locator(".paper-result__details summary").evaluate_all(
            "nodes => nodes.map(node => node.getBoundingClientRect().height)"
        )
        assert min(filter_heights) >= 44
        assert min(summary_heights) >= 44
        assert page_errors == []
        assert _serious_axe_violations(page) == []
    finally:
        context.close()


def test_all_twenty_detail_routes_use_manifest_boundary_and_safe_local_renderer(
    browser: Browser, papers_origin: str,
) -> None:
    page, context = _new_page(browser, 390)
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        for record in RECORDS:
            response = page.goto(
                f"{papers_origin}/paper/{record['slug']}?lang=zh",
                wait_until="domcontentloaded",
                timeout=20_000,
            )
            assert response is not None and response.status == 200
            article = page.locator("#paper-article")
            expect(article).to_have_attribute("aria-busy", "false", timeout=15_000)
            expect(page.locator("#paper-heading")).to_have_text(record["title_zh"])
            expect(page.locator("#paper-source")).to_have_attribute("href", record["source_url"])
            expect(page.locator("#paper-download-md")).to_have_attribute(
                "download", f"{record['slug']}.md"
            )
            assert page.locator("#paper-legacy-record").evaluate("node => node.open") is False
            assert page.evaluate(
                """() => document.getElementById('paper-boundary').compareDocumentPosition(
                  document.getElementById('paper-legacy-record')) & Node.DOCUMENT_POSITION_FOLLOWING"""
            )
            forbidden_nodes = article.locator("h1, script, iframe, object, embed, style, img")
            assert forbidden_nodes.count() == 0, forbidden_nodes.evaluate_all(
                "nodes => nodes.map(node => node.tagName)"
            )
            assert article.locator("h2").count() >= 1
            assert len((article.text_content() or "").strip()) > 100
            unsafe_links = article.locator("a[href]").evaluate_all(
                """nodes => nodes.map(node => node.href).filter(href =>
                  !href.startsWith(location.origin + '/') &&
                  !href.startsWith('https://github.com/dada8899/structural-isomorphism/'))"""
            )
            assert unsafe_links == []
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert page_errors == []
    finally:
        context.close()


def test_unknown_slug_is_a_real_http_404(browser: Browser, papers_origin: str) -> None:
    page, context = _new_page(browser)
    try:
        response = page.goto(
            f"{papers_origin}/paper/not-a-real-paper", wait_until="commit", timeout=15_000
        )
        assert response is not None and response.status == 404
        assert page.locator("#paper-boundary").count() == 0
    finally:
        context.close()


def test_malicious_markdown_is_text_only_and_external_runtime_is_optional(
    browser: Browser, papers_origin: str,
) -> None:
    slug = "soc-earthquake-2026-04-15"
    malicious = """# Raw title <img src=x onerror=\"window.__paperPwned=1\">

<script>window.__paperPwned = 2</script>

[unsafe](javascript:window.__paperPwned=3)
[foreign](https://evil.example/steal)
[repository](../v4/validation/soc-earthquake/fetch_earthquakes.py)
[local](/papers)

```html
<iframe srcdoc=\"<script>window.__paperPwned=4</script>\"></iframe>
```

| Field | Value |
|---|---|
| safe | **rendered** |
"""
    page, context = _new_page(browser, 390)
    external_requests: list[str] = []
    page.unroute("https://**")
    page.route(
        "https://**",
        lambda route: (external_requests.append(route.request.url), route.abort()),
    )
    page.route(
        f"**/assets/data/papers/{slug}.md*",
        lambda route: route.fulfill(
            status=200,
            content_type="text/markdown; charset=utf-8",
            body=malicious,
        ),
    )
    try:
        page.goto(f"{papers_origin}/paper/{slug}?lang=en", wait_until="domcontentloaded")
        article = page.locator("#paper-article")
        expect(article).to_have_attribute("aria-busy", "false", timeout=15_000)
        assert page.evaluate("window.__paperPwned") is None
        assert article.locator("script, iframe, img, svg, style, object, embed").count() == 0
        assert article.locator("h1").count() == 0
        assert article.locator("h2").count() == 1
        assert article.locator("a").count() == 2
        assert article.locator("a", has_text="repository").get_attribute("href") == (
            "https://github.com/dada8899/structural-isomorphism/blob/main/"
            "v4/validation/soc-earthquake/fetch_earthquakes.py"
        )
        assert article.locator("a", has_text="local").get_attribute("href") == "/papers"
        assert "window.__paperPwned" in (article.text_content() or "")
        assert page.locator("#paper-legacy-record").evaluate("node => node.open") is False
        assert all("plausible.bytedance.city" in url for url in external_requests)
    finally:
        context.close()


@pytest.mark.parametrize("width", [375, 390, 430])
def test_detail_mobile_has_no_overflow_and_no_serious_axe_violations(
    browser: Browser, papers_origin: str, width: int,
) -> None:
    slug = "unified-pipeline-v0.2-2026-05-13"
    long_token = "structural_isomorphism_" * 24
    long_formula = "+".join(f"x_{{{index}}}" for index in range(1, 45))
    markdown = f"""## Overflow accessibility fixture

Short paragraph.

```text
short
```

```text
{long_token}
```

| Field | Value |
|---|---|
| short | ok |

| Long field | Long value |
|---|---|
| evidence | {long_token} |

$$
{long_formula}=0
$$
"""
    page, context = _new_page(browser, width)
    page.route(
        f"**/assets/data/papers/{slug}.md*",
        lambda route: route.fulfill(
            status=200,
            content_type="text/markdown; charset=utf-8",
            body=markdown,
        ),
    )
    try:
        page.goto(
            f"{papers_origin}/paper/{slug}?lang=en",
            wait_until="domcontentloaded",
        )
        expect(page.locator("#paper-article")).to_have_attribute(
            "aria-busy", "false", timeout=15_000,
        )
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#paper-heading")).to_have_text(RECORDS[0]["title_en"])
        expect(page.locator("#paper-not-established")).to_have_text(
            CONTRACT["boundary_en"]
        )
        expect(page.locator("#paper-legacy-summary")).to_have_text(
            "Inspect the unnormalized historical Markdown record"
        )
        expect(page.locator(".paper-breadcrumb")).to_have_attribute(
            "aria-label", "Breadcrumb"
        )
        expect(page.locator(".paper-primary-actions")).to_have_attribute(
            "aria-label", "Historical material actions"
        )
        overflow = page.evaluate(
            """() => ({
              viewport: innerWidth,
              documentWidth: document.documentElement.scrollWidth,
              offenders: Array.from(document.querySelectorAll('#paper-legacy-record *'))
                .map(node => {
                  const box = node.getBoundingClientRect();
                  return {
                    tag: node.tagName,
                    cls: typeof node.className === 'string' ? node.className : '',
                    left: Number(box.left.toFixed(1)),
                    right: Number(box.right.toFixed(1)),
                    width: Number(box.width.toFixed(1)),
                    clientWidth: node.clientWidth,
                    scrollWidth: node.scrollWidth,
                  };
                }).filter(item => item.left < -1 || item.right > innerWidth + 1)
                .slice(0, 12)
            })"""
        )
        assert overflow["documentWidth"] <= overflow["viewport"] + 1, json.dumps(overflow)
        assert page.locator("#paper-legacy-record").evaluate("node => node.open") is False
        page.locator("#paper-legacy-record > summary").focus()
        page.keyboard.press("Enter")
        assert page.locator("#paper-legacy-record").evaluate("node => node.open") is True
        page.wait_for_function(
            "document.querySelectorAll('#paper-article [data-paper-scrollable=true]').length >= 2"
        )
        overflow = page.evaluate(
            """() => ({
              viewport: innerWidth,
              documentWidth: document.documentElement.scrollWidth,
              offenders: Array.from(document.querySelectorAll('#paper-legacy-record *'))
                .map(node => {
                  const box = node.getBoundingClientRect();
                  return {
                    tag: node.tagName,
                    cls: typeof node.className === 'string' ? node.className : '',
                    left: Number(box.left.toFixed(1)),
                    right: Number(box.right.toFixed(1)),
                    width: Number(box.width.toFixed(1)),
                    clientWidth: node.clientWidth,
                    scrollWidth: node.scrollWidth,
                  };
                }).filter(item => item.left < -1 || item.right > innerWidth + 1)
                .slice(0, 12)
            })"""
        )
        assert overflow["documentWidth"] <= overflow["viewport"] + 1, json.dumps(overflow)

        focusability = page.evaluate(
            """() => {
              const candidates = Array.from(document.querySelectorAll(
                '#paper-article pre, #paper-article table, '
                + '#paper-article .katex-display, #paper-article .katex'
              ));
              return candidates.map(node => {
                const style = getComputedStyle(node);
                const overflows = (style.overflowX === 'auto' || style.overflowX === 'scroll')
                  && node.clientWidth > 0 && node.scrollWidth > node.clientWidth + 1;
                return {
                  tag: node.tagName,
                  cls: typeof node.className === 'string' ? node.className : '',
                  overflows,
                  tabIndex: node.tabIndex,
                  managed: node.dataset.paperScrollable === 'true',
                  label: node.getAttribute('aria-label') || '',
                };
              });
            }"""
        )
        actual_overflow = [item for item in focusability if item["overflows"]]
        static_nodes = [item for item in focusability if not item["overflows"]]
        assert len(actual_overflow) >= 2, json.dumps(focusability)
        assert static_nodes, json.dumps(focusability)
        assert all(
            item["tabIndex"] == 0 and item["managed"] for item in actual_overflow
        ), json.dumps(focusability)
        assert all(
            item["tabIndex"] != 0 and not item["managed"] for item in static_nodes
        ), json.dumps(focusability)

        scrollable = page.locator("#paper-article [data-paper-scrollable=true]").first
        scrollable.focus()
        focus_outline = scrollable.evaluate(
            """node => {
              const style = getComputedStyle(node);
              return {style: style.outlineStyle, width: parseFloat(style.outlineWidth)};
            }"""
        )
        assert focus_outline["style"] != "none"
        assert focus_outline["width"] >= 2

        page.evaluate("window.i18n.setLang('zh')")
        expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        expect(page.locator("#paper-heading")).to_have_text(RECORDS[0]["title_zh"])
        expect(page.locator("#paper-not-established")).to_have_text(
            CONTRACT["boundary_zh"]
        )
        expect(page.locator("#paper-legacy-summary")).to_have_text(
            "查看未经当前证据标准化的历史 Markdown 原文"
        )
        expect(page.locator(".paper-breadcrumb")).to_have_attribute(
            "aria-label", "面包屑"
        )
        expect(page.locator(".paper-primary-actions")).to_have_attribute(
            "aria-label", "历史材料操作"
        )
        expect(page.locator("#paper-legacy-record")).to_have_attribute("open", "")
        expect(
            page.locator('#paper-article [data-paper-managed-label="true"]').first
        ).to_have_attribute("aria-label", re.compile(r"^可横向滚动"))

        page.evaluate("window.i18n.setLang('en')")
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#paper-heading")).to_have_text(RECORDS[0]["title_en"])
        expect(
            page.locator('#paper-article [data-paper-managed-label="true"]').first
        ).to_have_attribute("aria-label", re.compile(r"^Horizontally scrollable"))
        expect(page.locator("#paper-legacy-record")).to_have_attribute("open", "")
        assert _serious_axe_violations(page) == []
    finally:
        context.close()
