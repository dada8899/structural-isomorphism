from scripts.check_public_controls import run
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_control_contract() -> None:
    controls, errors = run()
    assert len(controls) >= 100
    assert errors == []


def test_inventory_has_links_and_buttons() -> None:
    controls, _ = run()
    assert any(item["tag"] == "a" for item in controls)
    assert any(item["tag"] == "button" for item in controls)


def test_workbench_requires_fingerprint_and_candidate_confirmation() -> None:
    ask = (ROOT / "web/frontend/assets/js/ask.js").read_text(encoding="utf-8")
    analyze = (ROOT / "web/frontend/assets/js/analyze.js").read_text(encoding="utf-8")
    page = (ROOT / "web/frontend/index.html").read_text(encoding="utf-8")
    assert "openFingerprintReview(q)" in ask
    assert "structural_pending_fingerprint" in ask
    assert "item._selectedCandidateId" in ask
    assert "系统不会替你默认选择 Top 1" in ask
    assert "结构匹配线索" in ask
    assert "反证 / 尚缺证据" in ask
    assert "适用边界" in ask
    assert "检索分" in ask
    assert "相似度 " not in ask
    assert 'id="ask-fingerprint-confirm"' in page
    assert "buildFingerprintDraft" in ask
    assert "structural_fingerprint_draft" in ask
    assert "系统只根据你写下的内容生成草案" in page
    assert "用户原文" in page and "待确认" in page and "未知" in page
    assert 'aria-describedby="ask-fingerprint-help"' in page
    assert "persist=0" in ask
    assert 'data-role="save-report-choice"' in ask
    assert "未勾选时不会在服务器保存报告" in ask
    assert "persistFlag === '1'" in analyze
    assert "persistFlag !== '0'" not in analyze


def test_report_list_is_an_action_workbench() -> None:
    script = (ROOT / "web/frontend/assets/js/my-reports.js").read_text(encoding="utf-8")
    page = (ROOT / "web/frontend/reports.html").read_text(encoding="utf-8")
    for bucket in ("today", "week", "waiting", "completed"):
        assert f"id: '{bucket}'" in script
    assert "outcome !== 'too_early'" in script
    assert "reportBucket(item)" in script
    assert "按今天、本周、等待推进和已完成分组" in page


def test_phase_build_is_network_independent() -> None:
    layout = (ROOT / "web/phase-detector/app/layout.tsx").read_text(encoding="utf-8")
    assert 'from "next/font/local"' in layout
    assert "next/font/google" not in layout


def test_phase_auth_navigation_is_wired_and_fail_closed() -> None:
    top_nav = (ROOT / "web/phase-detector/components/TopNav.tsx").read_text(encoding="utf-8")
    auth_nav = (ROOT / "web/phase-detector/components/AuthNav.tsx").read_text(encoding="utf-8")
    production_env = (ROOT / "web/phase-detector/.env.production").read_text(encoding="utf-8")
    assert 'import AuthNav from "./AuthNav"' in top_nav
    assert '<AuthNav variant="compact" />' in top_nav
    assert '<AuthNav variant="drawer" />' in top_nav
    assert 'process.env.NEXT_PUBLIC_AUTH_ENABLED !== "true"' in auth_nav
    assert 'href="/auth/login"' in auth_nav
    assert "注册 / 登录" in auth_nav
    assert "min-h-11" in auth_nav
    assert "NEXT_PUBLIC_AUTH_ENABLED=true" in production_env


def test_beta_auth_entry_is_explicitly_phase_scoped() -> None:
    chrome = (ROOT / "web/frontend/assets/js/site-chrome.js").read_text(encoding="utf-8")
    backend = (ROOT / "web/backend/main.py").read_text(encoding="utf-8")
    assert "https://phase.bytedance.city/auth/login" in chrome
    assert "Phase 账户 ↗" in chrome
    assert "external: true" in chrome
    assert "target=\"_blank\" rel=\"noopener\"" in chrome
    assert "async def unified_auth_login" in backend


def test_public_positioning_matches_frozen_demo_and_null_backtest() -> None:
    phase_paths = [
        "web/phase-detector/app/page.tsx",
        "web/phase-detector/app/zh/page.tsx",
        "web/phase-detector/app/thank-you/page.tsx",
        "web/phase-detector/components/LandingHero.tsx",
        "web/phase-detector/components/LandingHeroZh.tsx",
        "web/phase-detector/components/HowItWorksSteps.tsx",
        "web/phase-detector/components/TrustSignalsRow.tsx",
        "web/phase-detector/components/ExploreCardsGrid.tsx",
        "web/phase-detector/components/WaitlistForm.tsx",
    ]
    phase = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in phase_paths)
    forbidden_phase_claims = (
        "You judge the alpha",
        "alpha 是否成立",
        "你判断 alpha",
        "before they're priced",
        "市场定价前看见翻转",
        "Recent flips",
        "本周状态变化",
        "每周精选",
        "每周日推送",
        "本周新走到",
        "本周回到",
    )
    assert not any(claim in phase for claim in forbidden_phase_claims)
    assert "frozen 597-ticker demo snapshot" in phase.lower()
    assert "NULL" in phase

    seo = (ROOT / "web/phase-detector/lib/seo.ts").read_text(encoding="utf-8")
    nav = (ROOT / "web/phase-detector/components/TopNav.tsx").read_text(encoding="utf-8")
    pricing = (ROOT / "web/phase-detector/app/pricing/page.tsx").read_text(encoding="utf-8")
    assert '"@type": "Offer"' not in seo
    assert "priceCurrency" not in seo
    assert '{ href: "/companies", label: "公司表" }' in nav
    assert '{ href: "/pricing", label: "定价" }' not in nav
    assert "PricingTable" not in pricing


def test_beta_entry_copy_uses_current_counts_timing_and_claim_boundary() -> None:
    paths = [
        "web/frontend/index.html",
        "web/frontend/learn.html",
        "web/frontend/assets/js/home.js",
        "web/frontend/assets/data/i18n/content.json",
    ]
    copy = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in paths)
    for stale in ("100 家", "100家", "1-2 分钟", "1–2 分钟", "完全相同", "exactly the same"):
        assert stale not in copy
    assert "597 个 demo ticker" in copy
    assert "2–3 分钟" in copy
    assert "机制是否一致仍需验证" in copy


def test_phase_privacy_discloses_account_session_storage() -> None:
    privacy = (ROOT / "web/phase-detector/app/privacy/page.tsx").read_text(encoding="utf-8")
    for disclosure in ("账户与登录", "登录链接的哈希", "phase_session", "HttpOnly", "SameSite=Lax"):
        assert disclosure in privacy
    assert "localStorage（不是 cookie）" not in privacy


def test_phase_logout_and_bulk_favorite_failures_are_not_false_successes() -> None:
    auth = (ROOT / "web/phase-detector/lib/auth-client.ts").read_text(encoding="utf-8")
    nav = (ROOT / "web/phase-detector/components/AuthNav.tsx").read_text(encoding="utf-8")
    favorites = (ROOT / "web/phase-detector/app/me/favorites/page.tsx").read_text(encoding="utf-8")
    me_page = (ROOT / "web/phase-detector/app/me/page.tsx").read_text(encoding="utf-8")
    assert "if (!response.ok)" in auth
    assert "setUser(null)" in auth
    assert "退出失败，请重试" in nav
    assert "你仍处于登录状态" in me_page
    assert "failed.add(t)" in favorites
    assert "已保留在列表中" in favorites
    assert "已同步到邮箱账户，可在其他设备登录后查看" in favorites
    assert "当前未登录，收藏仅保存在本设备；登录后会自动合并" in favorites
