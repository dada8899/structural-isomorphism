import json
import subprocess

from scripts.check_public_claims import (
    DEFAULT_INVENTORY,
    ROOT,
    _historical_paper_quarantine,
    _paths,
    load_inventory,
)


FRONTEND = ROOT / "web" / "frontend"
MANIFEST_PATH = FRONTEND / "assets" / "data" / "papers-manifest.json"
PAPERS_DIR = FRONTEND / "assets" / "data" / "papers"
CATALOG_JS = FRONTEND / "assets" / "js" / "papers-catalog.js"
HISTORICAL_BOUNDARY_OPENING = (
    "> **历史研究记录——不是当前证据。 / "
    "Historical research record — not current evidence.**"
)
HISTORICAL_BOUNDARY_MARKERS = (
    "历史研究记录——不是当前证据。",
    "Historical research record — not current evidence.",
    "未绑定当前证据账本",
    "not bound to the current evidence ledger",
    "不能证明跨领域系统共享机制",
    "do not establish a shared cross-domain mechanism",
)


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _records(manifest: dict | None = None) -> list[dict]:
    value = manifest or _manifest()
    return [paper for group in value["groups"] for paper in group["papers"]]


def _run_catalog_validation(payload: dict) -> dict:
    program = f"""
const fs = require('fs');
const vm = require('vm');
const window = {{}};
const document = {{
  createElement: () => ({{
    set textContent(value) {{ this.value = value; }},
    get innerHTML() {{ return this.value || ''; }},
  }}),
}};
const fetch = () => new Promise(() => {{}});
vm.runInNewContext(
  fs.readFileSync({json.dumps(str(CATALOG_JS))}, 'utf8'),
  {{ window, document, fetch, URL, RegExp, Set, Map, Object, Array, Number, String, Error, Boolean }}
);
try {{
  const result = window.StructuralPapersCatalog.validateManifest({json.dumps(payload)});
  process.stdout.write(JSON.stringify({{ ok: true, counts: result.counts }}));
}} catch (error) {{
  process.stdout.write(JSON.stringify({{ ok: false, error: error.message }}));
}}
"""
    result = subprocess.run(
        ["node", "-e", program], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def _direct_boundary_order_errors(markdown: str) -> list[str]:
    """Return ordering errors for a directly addressable historical Markdown asset."""
    lines = markdown.splitlines()
    first_nonempty = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_nonempty is None:
        return ["historical Markdown is empty"]

    errors: list[str] = []
    if lines[first_nonempty].strip() != HISTORICAL_BOUNDARY_OPENING:
        errors.append("bilingual boundary must be the first non-empty content")

    first_h1 = next(
        (index for index, line in enumerate(lines) if line.startswith("# ")),
        None,
    )
    if first_h1 is None:
        return errors + ["historical Markdown must retain its H1"]
    if first_h1 <= first_nonempty:
        errors.append("bilingual boundary must precede the first H1")
        boundary = ""
    else:
        boundary_lines = lines[first_nonempty:first_h1]
        boundary = "\n".join(boundary_lines)
        if any(line.strip() and not line.lstrip().startswith(">") for line in boundary_lines):
            errors.append("only the bilingual boundary may appear before the first H1")

    missing = [marker for marker in HISTORICAL_BOUNDARY_MARKERS if marker not in boundary]
    if missing:
        errors.append(f"bilingual boundary is incomplete: {missing}")
    if "这份历史材料" not in boundary or "This historical material" not in boundary:
        errors.append("boundary wording must remain date-independent")
    if "这份 2026 年 5 月材料" in boundary or "This May 2026 material" in boundary:
        errors.append("boundary wording must not be bound to a publication month")
    return errors


def test_manifest_is_the_single_20_equals_14_plus_5_plus_1_contract() -> None:
    manifest = _manifest()
    records = _records(manifest)
    meta = manifest["meta"]

    assert meta["schema_version"] == "papers-manifest-v2"
    assert meta["total_items"] == 20
    assert meta["historical_result_records"] == 14
    assert meta["historical_research_drafts"] == 5
    assert meta["historical_tutorials"] == 1
    assert 20 == 14 + 5 + 1 == len(records)

    statuses = [record["status"] for record in records]
    assert statuses.count("historical-record") == 14
    assert statuses.count("historical-draft") == 5
    assert statuses.count("historical-tutorial") == 1


def test_every_manifest_slug_has_one_markdown_and_one_canonical_source() -> None:
    manifest = _manifest()
    records = _records(manifest)
    slugs = {record["slug"] for record in records}
    files = {path.stem for path in PAPERS_DIR.glob("*.md")}

    assert slugs == files
    assert len(slugs) == 20
    assert all(record["source_url"].startswith(
        "https://github.com/dada8899/structural-isomorphism/"
    ) for record in records)
    assert all("external_link" not in record for record in records)


def test_shared_catalog_accepts_real_manifest_and_rejects_slug_or_source_attacks() -> None:
    manifest = _manifest()
    accepted = _run_catalog_validation(manifest)
    assert accepted == {
        "ok": True,
        "counts": {"total": 20, "records": 14, "drafts": 5, "tutorials": 1},
    }

    attacks = []
    bad_slug = json.loads(json.dumps(manifest))
    bad_slug["groups"][0]["papers"][0]["slug"] = "../paper"
    attacks.append(bad_slug)

    duplicate = json.loads(json.dumps(manifest))
    duplicate["groups"][1]["papers"][0]["slug"] = duplicate["groups"][0]["papers"][0]["slug"]
    attacks.append(duplicate)

    bad_source = json.loads(json.dumps(manifest))
    bad_source["groups"][0]["papers"][0]["source_url"] = "javascript:alert(1)"
    attacks.append(bad_source)

    drift = json.loads(json.dumps(manifest))
    drift["meta"]["historical_result_records"] = 13
    attacks.append(drift)

    for attack in attacks:
        assert _run_catalog_validation(attack)["ok"] is False


def test_index_has_one_external_renderer_and_no_legacy_inline_renderer() -> None:
    html = (FRONTEND / "papers.html").read_text(encoding="utf-8")

    assert html.count("/assets/js/papers-catalog.js") == 1
    assert html.count("/assets/js/papers.js") == 1
    assert "const STATUS_LABEL" not in html
    assert "papers-manifest.json?v=20260513" not in html
    assert "4 篇 arXiv 投稿" not in html
    assert "/assets/css/papers.css" in html


def test_detail_uses_local_safe_renderer_and_has_non_bypassable_boundary_shell() -> None:
    html = (FRONTEND / "paper.html").read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/npm/marked" not in html
    assert html.count("/assets/js/papers-catalog.js") == 1
    assert html.count("/assets/js/markdown-safe.js") == 1
    assert html.count("/assets/js/paper.js") == 1
    assert 'id="paper-boundary"' in html
    assert 'id="paper-heading"' in html
    assert 'id="paper-legacy-record"' in html
    assert 'href="/papers"' in html
    assert "soc-earthquake" not in html
    assert "marked.parse" not in html


def test_public_claim_dependency_closure_includes_manifest_renderer_and_all_markdown() -> None:
    paths = set(_paths(load_inventory(DEFAULT_INVENTORY), ROOT))
    expected_markdown = {
        path.relative_to(ROOT).as_posix() for path in PAPERS_DIR.glob("*.md")
    }

    assert "web/frontend/assets/js/papers-catalog.js" in paths
    assert "web/frontend/assets/js/papers.js" in paths
    assert "web/frontend/assets/js/paper.js" in paths
    assert "web/frontend/assets/data/papers-manifest.json" in paths
    assert expected_markdown <= paths


def test_historical_markdown_quarantine_requires_raw_and_runtime_boundaries() -> None:
    paths = _paths(load_inventory(DEFAULT_INVENTORY), ROOT)
    contents = {
        relative: (ROOT / relative).read_text(encoding="utf-8")
        for relative in paths
    }
    expected_markdown = {
        path.relative_to(ROOT).as_posix() for path in PAPERS_DIR.glob("*.md")
    }

    quarantined, errors = _historical_paper_quarantine(contents)
    assert errors == []
    assert quarantined == expected_markdown

    direct_asset_bypass = dict(contents)
    direct_path = sorted(expected_markdown)[0]
    direct_asset_bypass[direct_path] = direct_asset_bypass[direct_path].replace(
        "not bound to the current evidence ledger",
        "kept as an old draft",
        1,
    )
    quarantined, errors = _historical_paper_quarantine(direct_asset_bypass)
    assert quarantined == set()
    assert any("raw self-boundary" in error for error in errors)

    bypass = dict(contents)
    bypass["web/frontend/paper.html"] = bypass["web/frontend/paper.html"].replace(
        'id="paper-legacy-record">', 'id="paper-legacy-record" open>'
    )
    quarantined, errors = _historical_paper_quarantine(bypass)
    assert quarantined == set()
    assert any("closed details" in error for error in errors)


def test_every_direct_markdown_asset_starts_with_the_bilingual_evidence_boundary() -> None:
    for path in sorted(PAPERS_DIR.glob("*.md")):
        markdown = path.read_text(encoding="utf-8")
        assert _direct_boundary_order_errors(markdown) == [], path


def test_direct_markdown_boundary_contract_rejects_h1_before_warning() -> None:
    markdown = sorted(PAPERS_DIR.glob("*.md"))[0].read_text(encoding="utf-8")
    lines = markdown.splitlines()
    h1_index = next(index for index, line in enumerate(lines) if line.startswith("# "))
    h1 = lines.pop(h1_index)
    inverted = "\n".join((h1, "", *lines))

    errors = _direct_boundary_order_errors(inverted)
    assert "bilingual boundary must be the first non-empty content" in errors
    assert "bilingual boundary must precede the first H1" in errors


def test_inventory_does_not_narratively_exclude_dynamic_paper_markdown() -> None:
    inventory = load_inventory(DEFAULT_INVENTORY)
    excluded = " ".join(inventory["scope"]["excluded_contexts"])

    assert "assets/data/papers" not in excluded


def test_cache_version_is_one_release_across_papers_assets() -> None:
    manifest = _manifest()
    version = manifest["meta"]["asset_version"]
    papers_html = (FRONTEND / "papers.html").read_text(encoding="utf-8")
    paper_html = (FRONTEND / "paper.html").read_text(encoding="utf-8")
    catalog = CATALOG_JS.read_text(encoding="utf-8")

    assert version == "20260714n2"
    for asset in ("papers.css", "papers-catalog.js", "papers.js"):
        assert f"{asset}?v={version}" in papers_html
    for asset in ("paper.css", "papers-catalog.js", "markdown-safe.js", "paper.js"):
        assert f"{asset}?v={version}" in paper_html
    assert f"papers-manifest.json?v={version}" in catalog


def test_papers_language_runtime_uses_real_service_contract_and_syncs_aria() -> None:
    index_js = (FRONTEND / "assets" / "js" / "papers.js").read_text(encoding="utf-8")
    detail_js = (FRONTEND / "assets" / "js" / "paper.js").read_text(encoding="utf-8")

    assert "i18n:langchange" not in index_js + detail_js
    assert "window.i18n.onChange" in index_js
    assert "window.i18n.onChange" in detail_js
    assert "alignExplicitUrlLanguage();" in index_js
    assert "alignExplicitUrlLanguage();" in detail_js
    for label in (
        "Historical material composition",
        "Historical material type filters",
        "Historical material boundary",
    ):
        assert label in index_js
    for label in ("Breadcrumb", "Historical material actions", "Loading historical Markdown"):
        assert label in detail_js


def test_detail_focuses_only_measured_horizontal_overflow_with_visible_ring() -> None:
    detail_js = (FRONTEND / "assets" / "js" / "paper.js").read_text(encoding="utf-8")
    detail_css = (FRONTEND / "assets" / "css" / "paper.css").read_text(encoding="utf-8")
    markdown_js = (FRONTEND / "assets" / "js" / "markdown-safe.js").read_text(
        encoding="utf-8"
    )

    assert "details && details.open" in detail_js
    assert "element.scrollWidth > element.clientWidth + 1" in detail_js
    assert "style.overflowX === 'auto' || style.overflowX === 'scroll'" in detail_js
    assert "element.setAttribute('tabindex', '0')" in detail_js
    assert "delete element.dataset.paperScrollable" in detail_js
    assert '[data-paper-scrollable="true"]:focus-visible' in detail_css
    assert "outline: 3px solid" in detail_css
    assert 'tabindex="0"' not in markdown_js


def test_index_evidence_summary_has_mobile_touch_target_contract() -> None:
    papers_css = (FRONTEND / "assets" / "css" / "papers.css").read_text(encoding="utf-8")
    summary_rule = papers_css.split(".paper-result__details summary {", 1)[1].split("}", 1)[0]

    assert "box-sizing: border-box" in summary_rule
    assert "min-height: 44px" in summary_rule
