"""Static release contracts for the Phase subproduct boundary."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_root_layout_identifies_phase_and_returns_to_canonical_main_product():
    layout = source("app/layout.tsx")
    boundary = source("components/ProductBoundary.tsx")
    assert "<ProductBoundary />" in layout
    assert "Structural Labs · Phase" in layout
    assert "冻结研究子产品" in layout
    assert 'href={MAIN_PRODUCT_URL}' in boundary
    assert 'const MAIN_PRODUCT_URL = "https://beta.structural.bytedance.city"' in boundary
    assert "返回 Structural 主产品 / Back to main product" in boundary
    assert "597 个 demo ticker" in boundary
    assert "published NULL backtest" in boundary
    assert "no predictive capability" in boundary
    assert "方法与来源 / Methods &amp; sources" in boundary
    assert "min-h-11" in boundary
    assert "phase-main-product-return-mobile" in boundary
    assert "xl:hidden" in boundary and "xl:flex" in boundary


def test_desktop_and_mobile_navigation_expose_same_main_product_exit():
    nav = source("components/TopNav.tsx")
    assert 'href: "https://beta.structural.bytedance.city"' in nav
    assert 'label: "返回 Structural 主产品 ↗"' in nav
    assert nav.count("{LINKS.map") == 2  # desktop + mobile drawer
    assert "min-h-[44px]" in nav and "min-h-11" in nav
    assert "focus-visible:outline" in nav
    assert 'e.key === "Escape"' in nav
    assert "toggleRef.current?.focus()" in nav
    assert "drawerRef.current?.querySelector" in nav
    assert 'aria-controls="mobile-nav-drawer"' in nav
    assert 'aria-expanded={open}' in nav
    assert 'window.matchMedia("(min-width: 1280px)")' in nav
    assert 'e.key !== "Tab"' in nav and "e.shiftKey" in nav
    assert 'element.setAttribute("inert", "")' in nav
    assert 'document.body.style.overflow = "hidden"' in nav
    assert "max-h-[calc(100dvh-57px)]" in nav


def test_english_and_chinese_home_make_identical_research_limits():
    english = source("components/LandingHero.tsx")
    chinese = source("components/LandingHeroZh.tsx")
    for page in (english, chinese):
        assert "Structural Labs · Phase" in page
        assert "597" in page
        assert "NULL" in page
        assert "min-h-11" in page
    assert "frozen hypothesis with its provenance" in english
    assert "no predictive capability" in english
    assert "冻结研究子产品" in chinese
    assert "不提供预测能力" in chinese
    assert "Published NULL; no predictive capability" in chinese


def test_named_pages_inherit_boundary_and_keep_clear_local_context():
    pages = {
        "app/about/page.tsx": ("Structural Labs · Phase", "返回 Structural 主产品"),
        "app/methodology/page.tsx": ("冻结研究子产品", "不提供预测能力"),
        "app/universality/page.tsx": ("Structural Labs · Phase", "Back to main product"),
        "app/companies/page.tsx": ("Structural Labs · Phase", "Back to main product"),
        "app/auth/login/page.tsx": ("子产品账户", "Back to main product"),
        "app/me/page.tsx": ("子产品账户", "Back to main product"),
    }
    for relative, markers in pages.items():
        text = source(relative)
        assert all(marker in text for marker in markers), relative
        assert "https://beta.structural.bytedance.city" in text or relative == "app/methodology/page.tsx"


def test_frozen_demo_null_and_no_prediction_contract_stays_consistent():
    combined = "\n".join(source(path) for path in (
        "components/ProductBoundary.tsx",
        "components/LandingHero.tsx",
        "components/LandingHeroZh.tsx",
        "components/TrustSignalsRow.tsx",
        "app/companies/page.tsx",
        "app/methodology/page.tsx",
        "app/about/page.tsx",
    ))
    assert "597" in combined
    assert "demo" in combined
    assert "NULL" in combined
    assert "provenance" in combined and "来源" in combined
    assert "no predictive capability" in combined and "不提供预测能力" in combined
    assert "每周更新一次" not in combined
    assert "下一步可能往哪走" not in combined
    assert "See live data" not in source("components/HeroCtaText.tsx")
    assert "Browse frozen snapshots" in source("components/HeroCtaText.tsx")


def test_metadata_and_manifest_use_subproduct_name():
    manifest = source("public/manifest.webmanifest")
    layout = source("app/layout.tsx")
    companies = source("app/companies/layout.tsx")
    universality = source("app/universality/layout.tsx")
    assert '"name": "Structural Labs · Phase"' in manifest
    assert "Structural Labs · Phase" in layout
    assert "597 个 demo ticker" in companies and "不提供预测能力" in companies
    assert "Structural Labs · Phase" in universality and "不提供预测能力" in universality


def test_public_backtest_p_value_has_one_artifact_derived_display_contract():
    result = json.loads(source("public/backtest/result.json"))
    assert result["p_value"] == result["ttest_welch"]["p"]
    assert f'{result["p_value"]:.10f}' == "0.5690715676"
    constant = source("lib/public-backtest.ts")
    assert 'import result from "@/public/backtest/result.json"' in constant
    assert "result.p_value" in constant and ".toFixed(10)" in constant
    for relative in (
        "components/TrustSignalsRow.tsx",
        "components/FaqAccordion.tsx",
        "components/EwsLeaderboardPanel.tsx",
        "app/companies/page.tsx",
        "app/backtest/page.tsx",
    ):
        assert "PUBLIC_BACKTEST_P_LABEL" in source(relative), relative
    public_source = "\n".join(
        path.read_text(encoding="utf-8")
        for base in ("app", "components", "lib")
        for path in (ROOT / base).rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )
    assert "p=0.681" not in public_source
    assert "p = 0.681" not in public_source
    assert "p≈0.68" not in public_source


def test_no_legacy_product_brand_remains_on_public_surfaces():
    offenders = []
    for base in ("app", "components", "lib", "public"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".json", ".webmanifest"}:
                continue
            if path.name == "search-index.json":
                continue
            if "Phase Detector" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_small_screen_privacy_and_return_controls_are_safe():
    privacy = source("app/privacy/page.tsx")
    assert "[overflow-wrap:anywhere]" in privacy
    assert "[&_code]:break-all" in privacy
    for relative in (
        "app/layout.tsx",
        "app/about/page.tsx",
        "app/methodology/page.tsx",
        "app/universality/page.tsx",
        "app/companies/page.tsx",
        "app/me/page.tsx",
        "app/auth/login/page.tsx",
    ):
        text = source(relative)
        if "返回 Structural 主产品" in text:
            assert "min-h-11" in text, relative
