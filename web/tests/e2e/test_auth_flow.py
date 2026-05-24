"""W15-B (session #10) magic-link auth e2e — UI shell + real backend.

Booting Next.js in CI is heavy. Following the W13-E `test_cmdk_search.py`
pattern, this test stands up:

  1. A real FastAPI backend (in-process via threading + uvicorn) on a
     dynamic port, with the auth router mounted and storage redirected
     to a tmp dir. JWT_SECRET is fixed so tests are deterministic.

  2. A tiny `http.server` serving a self-contained HTML shell that
     embeds a minimal-but-faithful JS implementation of /auth/login,
     /auth/verify, /me — mirroring the React components' testable
     surface (data-testids, fetch flow, redirect-after-verify).

Coverage:
  • /auth/login renders the form
  • Submit → mock outbox writes the link → dev mode returns it inline
  • /auth/verify?token=… → 200 → redirect to /me
  • /me shows the email + tier
  • Logout button clears state → /me shows "no session"
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _pick_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- Backend harness ----

@pytest.fixture
def backend(tmp_path, monkeypatch):
    """Boot a real FastAPI app with the auth router + a same-origin HTML
    shell on a dynamic port. Co-locating shell + API on one origin avoids
    CORS preflight + cookie SameSite headaches in tests.
    """
    monkeypatch.setenv("JWT_SECRET", "e2e-test-secret-deterministic-key-32+")
    monkeypatch.setenv("AUTH_DEV_MODE", "true")

    # Late import so env vars are read fresh.
    from api import auth as auth_mod  # noqa: E402
    from fastapi import FastAPI  # noqa: E402
    from fastapi.responses import HTMLResponse  # noqa: E402
    import uvicorn  # noqa: E402

    auth_mod._data_dir = lambda: tmp_path

    app = FastAPI()
    app.include_router(auth_mod.router, prefix="/api")

    @app.get("/", response_class=HTMLResponse)
    def _shell_root():
        return _shell_html("")  # same-origin → backend URL empty

    port = _pick_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for startup.
    deadline = time.time() + 5
    while time.time() < deadline and not server.started:
        time.sleep(0.05)
    if not server.started:
        pytest.skip("backend failed to start within 5s")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=2)


# ---- Frontend shell (minimal HTML mirroring the React pages) ----

# We serve this from a separate http.server on a different port so the
# fetch from JS → backend is same-origin via a /api/ proxy on the shell
# side. Simpler: bake the backend URL into the page and use absolute
# fetch with credentials="include".

def _shell_html(backend_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Auth harness</title>
  <style>body{{font:14px system-ui;padding:24px;max-width:480px;margin:auto}}</style>
</head>
<body>
  <div id="root"></div>
  <script>
    const BACKEND = "{backend_url}";
    const root = document.getElementById("root");

    function renderLogin() {{
      root.innerHTML = `
        <h1>登录</h1>
        <form data-testid="auth-login-form">
          <input type="email" data-testid="auth-login-email" required>
          <button type="submit" data-testid="auth-login-submit">发送链接</button>
        </form>
        <div data-testid="auth-login-sent" style="display:none">
          链接已发送
          <a data-testid="auth-login-dev-link"></a>
        </div>
        <div data-testid="auth-login-error" style="display:none"></div>
      `;
      const form = root.querySelector('[data-testid="auth-login-form"]');
      form.addEventListener("submit", async (e) => {{
        e.preventDefault();
        const email = root.querySelector('[data-testid="auth-login-email"]').value;
        console.log("submitting for", email);
        let r;
        try {{
          r = await fetch(BACKEND + "/api/auth/request-link", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ email }}),
          }});
        }} catch (err) {{
          console.log("fetch err", err.message);
          throw err;
        }}
        const j = await r.json();
        if (j.ok) {{
          form.style.display = "none";
          const sent = root.querySelector('[data-testid="auth-login-sent"]');
          sent.style.display = "block";
          if (j.dev_link) {{
            const a = root.querySelector('[data-testid="auth-login-dev-link"]');
            a.href = j.dev_link;
            a.textContent = j.dev_link;
            a.dataset.devToken = j.dev_token;
          }}
        }} else {{
          const err = root.querySelector('[data-testid="auth-login-error"]');
          err.style.display = "block";
          err.textContent = j.error || "failed";
        }}
      }});
    }}

    async function renderVerify(token) {{
      root.innerHTML = `<div data-testid="auth-verify-loading">验证中…</div>`;
      if (!token) {{
        root.innerHTML = `<div data-testid="auth-verify-missing">缺少 token</div>`;
        return;
      }}
      const r = await fetch(BACKEND + "/api/auth/verify", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        credentials: "include",
        body: JSON.stringify({{ token }}),
      }});
      const j = await r.json();
      if (j.ok) {{
        root.innerHTML = `<div data-testid="auth-verify-success">成功，跳转中…</div>`;
        setTimeout(() => {{ location.hash = "#/me"; route(); }}, 200);
      }} else {{
        root.innerHTML = `<div data-testid="auth-verify-error">${{j.error}}</div>`;
      }}
    }}

    async function renderMe() {{
      root.innerHTML = `<div data-testid="me-loading">加载中…</div>`;
      const r = await fetch(BACKEND + "/api/auth/me", {{ credentials: "include" }});
      if (r.status !== 200) {{
        root.innerHTML = `<div data-testid="me-no-session">未登录</div>`;
        return;
      }}
      const j = await r.json();
      root.innerHTML = `
        <h1>个人</h1>
        <div data-testid="me-email">${{j.user.email}}</div>
        <div data-testid="me-tier">${{j.user.tier}}</div>
        <div data-testid="me-created-at">${{j.user.created_at}}</div>
        <button data-testid="me-logout">退出</button>
      `;
      root.querySelector('[data-testid="me-logout"]').addEventListener("click", async () => {{
        await fetch(BACKEND + "/api/auth/logout", {{ method: "POST", credentials: "include" }});
        location.hash = "#/auth/login";
        route();
      }});
    }}

    function route() {{
      const h = location.hash;
      if (h.startsWith("#/auth/verify")) {{
        const q = h.split("?")[1] || "";
        const params = new URLSearchParams(q);
        renderVerify(params.get("token"));
      }} else if (h.startsWith("#/me")) {{
        renderMe();
      }} else {{
        renderLogin();
      }}
    }}

    window.addEventListener("hashchange", route);
    route();
  </script>
</body>
</html>
"""


@pytest.fixture
def shell(backend):
    """Alias for backend — co-located shell + API on one origin."""
    return backend


# ---- Tests ----

def test_login_form_renders(page, shell):
    page.goto(shell)
    page.wait_for_selector('[data-testid="auth-login-form"]')
    assert page.locator('[data-testid="auth-login-email"]').is_visible()
    assert page.locator('[data-testid="auth-login-submit"]').is_visible()


def test_request_link_dev_mode_shows_inline(page, shell):
    page.goto(shell)
    page.wait_for_selector('[data-testid="auth-login-email"]')
    page.locator('[data-testid="auth-login-email"]').fill("e2e@example.com")
    page.locator('[data-testid="auth-login-submit"]').click()
    page.wait_for_selector('[data-testid="auth-login-sent"]')
    link = page.locator('[data-testid="auth-login-dev-link"]')
    href = link.get_attribute("href")
    assert href and "/auth/verify?token=" in href


def test_verify_redirects_to_me(page, shell):
    page.goto(shell)
    page.wait_for_selector('[data-testid="auth-login-email"]')
    page.locator('[data-testid="auth-login-email"]').fill("e2eflow@example.com")
    page.locator('[data-testid="auth-login-submit"]').click()
    page.wait_for_selector('[data-testid="auth-login-dev-link"]', state="attached")
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"auth-login-dev-link\"]').dataset.devToken"
    )
    token = page.locator('[data-testid="auth-login-dev-link"]').get_attribute("data-dev-token")
    assert token

    # Navigate to the verify route with the token.
    page.evaluate(f"location.hash = '#/auth/verify?token={token}'")
    page.wait_for_selector('[data-testid="auth-verify-success"]', timeout=3000)
    # The success state should auto-redirect to /me.
    page.wait_for_selector('[data-testid="me-email"]', timeout=3000)
    assert page.locator('[data-testid="me-email"]').text_content() == "e2eflow@example.com"
    assert page.locator('[data-testid="me-tier"]').text_content() == "free"


def test_logout_clears_state(page, shell):
    page.goto(shell)
    page.wait_for_selector('[data-testid="auth-login-email"]')
    page.locator('[data-testid="auth-login-email"]').fill("logout@example.com")
    page.locator('[data-testid="auth-login-submit"]').click()
    page.wait_for_selector('[data-testid="auth-login-dev-link"]', state="attached")
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"auth-login-dev-link\"]').dataset.devToken"
    )
    token = page.locator('[data-testid="auth-login-dev-link"]').get_attribute("data-dev-token")

    page.evaluate(f"location.hash = '#/auth/verify?token={token}'")
    page.wait_for_selector('[data-testid="me-email"]', timeout=3000)

    page.locator('[data-testid="me-logout"]').click()
    page.wait_for_selector('[data-testid="auth-login-form"]')
    # Re-visit /me — should now show no session.
    page.evaluate("location.hash = '#/me'")
    page.wait_for_selector('[data-testid="me-no-session"]')


def test_verify_missing_token_shows_error(page, shell):
    page.goto(shell)
    page.evaluate("location.hash = '#/auth/verify'")
    page.wait_for_selector('[data-testid="auth-verify-missing"]')
