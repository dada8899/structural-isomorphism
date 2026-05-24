"""W12-B (session #10, 2026-05-15) — SEO surface e2e tests.

Verifies the SEO scaffolding added in W12-B:

  - per-page <title> + <meta name="description">
  - <meta property="og:image"> + asset returns 200 + 1200x630
  - JSON-LD parses as valid JSON, has @context schema.org
  - sitemap.xml has ≥100 URLs covering every routable page
  - robots.txt is parseable (Allow / Disallow / Sitemap directives)
  - newsletter RSS returns RSS 2.0 with ≥1 <item>

Local devserver: `next dev -p <random>` in web/phase-detector/. Pattern
mirrors `test_newsletter_archive.py`. The devserver fixture is module-
scoped so all SEO assertions reuse one boot.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_seo.py -v
"""
from __future__ import annotations

import io
import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PHASE_DETECTOR = REPO_ROOT / "web" / "phase-detector"
OG_DIR = PHASE_DETECTOR / "public" / "og"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http_ok(url: str, timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(1.0)
    return False


def _fetch(url: str, timeout: float = 20.0) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "phase-seo-test/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(), dict(r.headers.items())


@pytest.fixture(scope="module")
def next_devserver():
    """Spin up `next dev` for SEO assertions."""
    if not (PHASE_DETECTOR / "package.json").exists():
        pytest.skip(f"phase-detector workspace not found at {PHASE_DETECTOR}")
    next_bin = PHASE_DETECTOR / "node_modules" / ".bin" / "next"
    if not next_bin.exists():
        pytest.skip(f"next binary missing at {next_bin} — run pnpm install first")

    port = _free_port()
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
    log_dir = REPO_ROOT / "web" / "tests" / "e2e" / "results"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "seo_devserver.log"
    log_fh = log_path.open("wb")
    proc = subprocess.Popen(
        [str(next_bin), "dev", "-p", str(port)],
        cwd=str(PHASE_DETECTOR),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        if not _wait_http_ok(f"{base}/", timeout=180.0):
            log_fh.flush()
            tail = log_path.read_text(errors="replace")[-2000:]
            pytest.fail(f"next dev didn't come up on {port}; tail:\n{tail}")
        yield {"base": base}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()


# ---- OG card assets (static, no devserver needed) ---------------------


def test_og_cards_generated():
    """At least 10 OG cards exist under public/og/."""
    assert OG_DIR.is_dir(), f"OG dir missing: {OG_DIR}"
    pngs = sorted(OG_DIR.glob("*.png"))
    assert len(pngs) >= 10, f"expected ≥10 OG cards, got {len(pngs)}: {pngs}"


def test_og_cards_are_1200x630():
    """Every OG card is exactly 1200x630 (Twitter + OG canonical)."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    pngs = sorted(OG_DIR.glob("*.png"))
    for p in pngs:
        with Image.open(p) as img:
            assert img.size == (1200, 630), f"{p.name} is {img.size}, expected 1200x630"


# ---- Static files (robots.txt, sitemap.ts source) ---------------------


def test_static_robots_txt_present():
    """public/robots.txt fallback exists and references sitemap."""
    p = PHASE_DETECTOR / "public" / "robots.txt"
    assert p.exists(), "public/robots.txt missing"
    body = p.read_text(encoding="utf-8")
    assert "User-agent: *" in body
    assert "Sitemap:" in body
    assert "/api/" in body  # at minimum API is disallowed


def test_google_verification_placeholder_present():
    """Placeholder file explains how to add the real Search Console verification."""
    p = PHASE_DETECTOR / "public" / "google-verification-PLACEHOLDER.html"
    assert p.exists(), "verification placeholder missing"
    txt = p.read_text(encoding="utf-8")
    assert "google-site-verification" in txt
    assert "Search Console" in txt


# ---- Live SEO assertions via devserver --------------------------------


PAGES_TO_CHECK = [
    "/",
    "/about",
    "/methodology",
    "/companies",
    "/compare",
    "/universality",
    "/pricing",
    "/backtest",
    "/newsletter",
    "/newsletter/001",
]


def _extract_tag(html: str, tag: str, attrs: dict[str, str]) -> str | None:
    """Pull the content from a single matching <meta>/<link> tag.

    Naive but sufficient for SSR'd HTML — we just regex out matching open tags.
    """
    parts = [re.escape(f'{k}="{v}"') for k, v in attrs.items()]
    pat = re.compile(
        rf"<{tag}\s+[^>]*?(?:{'|'.join(parts)})[^>]*?/?>",
        re.IGNORECASE,
    )
    m = pat.search(html)
    if not m:
        return None
    tag_html = m.group(0)
    m2 = re.search(r'content=["\']([^"\']*)["\']', tag_html, re.IGNORECASE)
    if m2:
        return m2.group(1)
    m3 = re.search(r'href=["\']([^"\']*)["\']', tag_html, re.IGNORECASE)
    return m3.group(1) if m3 else None


@pytest.mark.parametrize("path", PAGES_TO_CHECK)
def test_pages_have_title_and_description(next_devserver, path):
    """Each routable page emits <title> + meta description in SSR HTML."""
    status, body, _ = _fetch(next_devserver["base"] + path, timeout=30.0)
    assert status == 200, f"{path} returned {status}"
    html = body.decode("utf-8", errors="replace")
    title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    assert title_m and len(title_m.group(1).strip()) > 5, f"{path}: missing/empty <title>"
    desc = _extract_tag(html, "meta", {"name": "description"})
    assert desc and len(desc.strip()) > 20, (
        f"{path}: missing/short meta description: {desc!r}"
    )


@pytest.mark.parametrize("path", PAGES_TO_CHECK)
def test_pages_have_og_image_and_canonical(next_devserver, path):
    """Each page has og:image + canonical link."""
    _, body, _ = _fetch(next_devserver["base"] + path, timeout=30.0)
    html = body.decode("utf-8", errors="replace")
    og_image = _extract_tag(html, "meta", {"property": "og:image"})
    assert og_image and og_image.endswith(".png"), (
        f"{path}: og:image missing or wrong format: {og_image!r}"
    )
    canonical = _extract_tag(html, "link", {"rel": "canonical"})
    assert canonical and canonical.startswith("https://phase.bytedance.city"), (
        f"{path}: canonical missing or wrong host: {canonical!r}"
    )


def test_og_image_assets_served(next_devserver):
    """All referenced OG images return 200 from the devserver."""
    base = next_devserver["base"]
    for png in sorted(OG_DIR.glob("*.png")):
        url = f"{base}/og/{png.name}"
        status, body, headers = _fetch(url, timeout=15.0)
        assert status == 200, f"{url} → {status}"
        assert len(body) > 1000, f"{url} body too small ({len(body)} bytes)"
        # Sanity check content-type.
        ctype = headers.get("Content-Type", "")
        assert "image/png" in ctype.lower() or "octet-stream" in ctype.lower(), (
            f"{url} unexpected content-type {ctype}"
        )


def test_json_ld_parses_on_landing(next_devserver):
    """Landing page emits JSON-LD scripts; each parses as valid JSON with @context."""
    _, body, _ = _fetch(next_devserver["base"] + "/", timeout=30.0)
    html = body.decode("utf-8", errors="replace")
    matches = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    assert len(matches) >= 2, f"expected ≥2 JSON-LD scripts on /, got {len(matches)}"
    for raw in matches:
        # Un-escape the `<` we emit in serialize().
        decoded = raw.encode("utf-8").decode("unicode_escape")
        try:
            obj = json.loads(decoded)
        except json.JSONDecodeError:
            obj = json.loads(raw)
        assert isinstance(obj, dict) or isinstance(obj, list)
        if isinstance(obj, dict):
            assert obj.get("@context", "").startswith("https://schema.org"), (
                f"JSON-LD missing @context: {list(obj.keys())[:5]}"
            )


def test_sitemap_has_dynamic_entries(next_devserver):
    """sitemap.xml has ≥100 URLs and includes static + per-ticker + per-class."""
    _, body, _ = _fetch(next_devserver["base"] + "/sitemap.xml", timeout=30.0)
    text = body.decode("utf-8", errors="replace")
    # Cheap URL count via regex (no namespace gymnastics needed).
    urls = re.findall(r"<loc>([^<]+)</loc>", text)
    assert len(urls) >= 100, f"sitemap has only {len(urls)} URLs, expected ≥100"
    # Spot checks across the categories we added.
    assert any(u.endswith("/companies") for u in urls), "missing /companies"
    assert any(u.endswith("/universality") for u in urls), "missing /universality"
    assert any("/company/" in u for u in urls), "missing per-ticker pages"
    assert any("/universality/" in u and not u.endswith("/universality") for u in urls), (
        "missing per-class pages"
    )
    assert any("/newsletter/001" in u for u in urls), "missing newsletter issue"
    # XML must be well-formed.
    ET.fromstring(text)


def test_robots_txt_endpoint(next_devserver):
    """Next-served /robots.txt is parseable and lists the sitemap."""
    _, body, _ = _fetch(next_devserver["base"] + "/robots.txt", timeout=30.0)
    text = body.decode("utf-8", errors="replace")
    assert "User-agent" in text or "User-Agent" in text
    assert "Sitemap" in text or "sitemap" in text
    assert "/api/" in text  # at minimum API blocked


def test_newsletter_rss_valid(next_devserver):
    """RSS feed is valid RSS 2.0 with ≥1 <item> referencing a newsletter URL."""
    _, body, headers = _fetch(next_devserver["base"] + "/newsletter/rss.xml", timeout=30.0)
    text = body.decode("utf-8", errors="replace")
    assert "<rss" in text and 'version="2.0"' in text, "not RSS 2.0"
    root = ET.fromstring(text)
    channel = root.find("channel")
    assert channel is not None, "missing <channel>"
    items = channel.findall("item")
    assert len(items) >= 1, f"expected ≥1 <item>, got {len(items)}"
    first = items[0]
    link = first.findtext("link") or ""
    assert "/newsletter/" in link, f"first item link unexpected: {link!r}"
