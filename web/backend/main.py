"""
Structural Web Backend — FastAPI 入口
"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

# Ensure structural_isomorphism package is importable.
# Prefer env var, else walk up from this file (web/backend/main.py -> project root).
_project_root = os.getenv("STRUCTURAL_PROJECT_ROOT") or str(
    Path(__file__).resolve().parent.parent.parent
)
sys.path.insert(0, _project_root)

load_dotenv(Path(__file__).parent / ".env")

# W14-D: structlog + correlation IDs. configure_logging() installs a
# JSON-line handler on the root logger (stdout) + a rotating file handler
# at web/backend/logs/server.jsonl, then routes uvicorn/fastapi/slowapi
# through the same pipeline. Must run *before* any logger.info() call so
# we don't accidentally bake in the old text format.
from logging_config import configure_logging, get_logger  # noqa: E402

configure_logging(level=os.getenv("STRUCTURAL_LOG_LEVEL", "INFO"))
logger = get_logger("structural.web")

# Shared state
app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load the search engine once."""
    logger.info("Starting Structural Web Backend...")

    # Initialise structured JSON event logger + (optional) Sentry.
    try:
        from services.observability import setup_logging
        setup_logging()
    except Exception as e:  # pragma: no cover — never fail startup over logging
        logger.warning(f"observability setup failed: {e}")

    from services.search_service import SearchService

    data_dir = os.getenv("STRUCTURAL_DATA_DIR")
    kb_file = os.getenv("STRUCTURAL_KB_FILE", "kb-expanded.jsonl")
    model_path = os.getenv("STRUCTURAL_MODEL_PATH")
    precomputed = os.getenv("STRUCTURAL_PRECOMPUTED_EMBEDDINGS")

    logger.info(f"Loading search service: data_dir={data_dir}, kb_file={kb_file}, precomputed={precomputed}")
    search_service = SearchService(
        data_dir=data_dir,
        kb_file=kb_file,
        model_path=model_path,
        precomputed_embeddings=precomputed,
    )
    app_state["search"] = search_service
    logger.info(f"Search service ready. KB size: {search_service.kb_size}")

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Structural",
    description=(
        "跨领域结构同构搜索引擎 — Structural Isomorphism API.\n\n"
        "Public surface for the Structural cross-domain knowledge engine. "
        "Endpoints are grouped by capability (Ask / Phase / Phenomenon / "
        "Pricing / Newsletter / Admin). Rate limits are tier-based; supply "
        "an `X-API-Key` header to promote a request beyond the anonymous "
        "free-tier bucket."
    ),
    version="0.2.0",
    lifespan=lifespan,
    contact={
        "name": "Structural Team",
        "url": "https://structural.bytedance.city",
    },
    license_info={
        "name": "Proprietary",
    },
    openapi_tags=[
        {"name": "ask", "description": "Perplexity-like Q&A over the KB"},
        {"name": "search", "description": "Vector search for phenomena"},
        {"name": "phenomenon", "description": "Per-phenomenon lookups + similar items"},
        {"name": "mapping", "description": "LLM-generated structural mappings"},
        {"name": "analyze", "description": "Deep cross-domain transfer reports"},
        {"name": "synthesize", "description": "Synthesized answer over search results"},
        {"name": "daily", "description": "Today's curated discoveries"},
        {"name": "discoveries", "description": "A-grade structural discoveries"},
        {"name": "examples", "description": "Handpicked example pairs"},
        {"name": "suggest", "description": "Search suggestion phrases"},
        {"name": "history", "description": "Per-device anonymous query history"},
        {"name": "newsletter", "description": "Email newsletter signup"},
        {"name": "favorites", "description": "Per-user bookmarked company tickers"},
        {"name": "checkout-mock", "description": "Stripe checkout mock (pre-PMF)"},
        {"name": "system", "description": "Health, version, and operational probes"},
        {"name": "admin", "description": "Admin-only endpoints (require admin tier)"},
    ],
)

# --- OpenAPI security scheme: APIKeyHeader (X-API-Key) ---
# Optional everywhere; admin-required for /api/admin/*. We inject via a
# custom openapi() so the same spec is served at /openapi.json AND can be
# exported to docs/api/openapi.json without re-implementing the logic.
def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=getattr(app, "openapi_tags", None),
        contact=getattr(app, "contact", None),
        license_info=getattr(app, "license_info", None),
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["APIKeyHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": (
            "Optional API key. Anonymous requests fall back to the free tier "
            "(60 req/min). Provide an X-API-Key header to access higher tiers."
        ),
    }
    # Force admin-prefix paths to require the key.
    for path, methods in schema.get("paths", {}).items():
        if path.startswith("/api/admin"):
            for op in methods.values():
                if isinstance(op, dict):
                    op["security"] = [{"APIKeyHeader": []}]
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi


# --- RFC 7807 problem-detail error handlers ---
# Must be installed before routers so they catch validation errors raised
# during dependency resolution.
from errors import install_problem_handlers  # noqa: E402
install_problem_handlers(app)

# --- Tier-aware rate limiter (W11-C) ---
# Replaces the previous flat slowapi setup. The new module installs the
# middleware + custom RFC 7807 429 handler in one call. The legacy
# `services/rate_limit.py` is kept (existing routers still import `limit`
# and `tier_limit_decorator` from it) but defers to the same shared
# Limiter via the middleware contextvar.
from middleware import install_rate_limit  # noqa: E402
install_rate_limit(app)

# --- CORS ---
# Origins are restricted to our production hosts; wildcard + credentials is
# a browser-invalid combo anyway, so we drop allow_credentials.
_allowed_origins = [
    "https://beta.structural.bytedance.city",
    "https://structural.bytedance.city",
]
_extra = os.getenv("STRUCTURAL_EXTRA_ORIGINS", "").strip()
if _extra:
    _allowed_origins.extend([o.strip() for o in _extra.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    # W14-C: DELETE added for /api/privacy/delete (GDPR right-to-erasure).
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# W14-D: Correlation-ID middleware. Mounted last so it runs *first* for
# inbound requests (Starlette middleware stack is LIFO). Reads X-Request-ID
# from caller or generates UUID4; binds onto ContextVar so every log line
# in the request scope carries it. Echoes back as X-Request-ID on response.
from middleware.correlation import install_correlation_middleware  # noqa: E402

install_correlation_middleware(app)


# --- Shared getter for dependency ---
def get_search_service():
    return app_state.get("search")


# --- API routes ---
from api import search, phenomenon, mapping, daily, examples, suggest, discoveries, analyze, synthesize, ask, history, newsletter, checkout_mock, error_log, favorites  # noqa
from api.privacy import export as privacy_export, delete as privacy_delete  # noqa

app.include_router(search.router, prefix="/api")
app.include_router(phenomenon.router, prefix="/api")
app.include_router(mapping.router, prefix="/api")
app.include_router(daily.router, prefix="/api")
app.include_router(examples.router, prefix="/api")
app.include_router(suggest.router, prefix="/api")
app.include_router(discoveries.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(synthesize.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(newsletter.router, prefix="/api")
# W10-B (session #10): Stripe Pro mock + /api/usage probe. Real Stripe deferred
# until PMF signal — see web/backend/api/checkout_mock.py for migration plan.
app.include_router(checkout_mock.router, prefix="/api")
# W12-E (session #10): client error reporter (page + global error boundaries
# auto-POST here). 10/min/session rate limit + 10MB rotated jsonl.
app.include_router(error_log.router, prefix="/api")
# W14-D: admin log tail endpoint — admin tier only.
from api.admin import logs as admin_logs  # noqa: E402

app.include_router(admin_logs.router, prefix="/api")
# W14-C: GDPR data export + delete endpoints.
app.include_router(privacy_export.router, prefix="/api")
app.include_router(privacy_delete.router, prefix="/api")
# W15-C (session #10): user favorites / bookmarks (per-user star button).
app.include_router(favorites.router, prefix="/api")


@app.get(
    "/api/health",
    tags=["system"],
    summary="Liveness probe",
    description=(
        "Lightweight health check. Pass `?deep=1` for a deep probe that "
        "also exercises external dependencies (DB / LLM upstream)."
    ),
    responses={
        200: {
            "description": "Service is up",
            "content": {
                "application/json": {
                    "example": {"status": "ok", "kb_size": 12345, "llm_model": "deepseek-chat"}
                }
            },
        }
    },
)
async def health(deep: int = 0):
    svc = app_state.get("search")
    body = {
        "status": "ok",
        "kb_size": svc.kb_size if svc else 0,
        "llm_model": os.getenv("LLM_MODEL", "unknown"),
    }
    if deep:
        # Deep-mode: probe optional subsystems and surface their state.
        # We never fail the health endpoint outright — degraded subsystems
        # show up as `checks.<name> = "fail"` so an operator can see the
        # full picture in one shot.
        checks = {}
        # search service load state
        checks["search_service"] = "ok" if svc else "fail"
        # history DB file accessible
        try:
            from pathlib import Path as _P
            hp = _P(__file__).parent / "data" / "history.db"
            checks["history_db"] = "ok" if hp.parent.exists() else "missing_dir"
        except Exception:
            checks["history_db"] = "fail"
        # LLM upstream env present
        checks["llm_env"] = "ok" if os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY") else "missing"
        body["checks"] = checks
        body["status"] = "ok" if all(v in ("ok", "missing") for v in checks.values()) else "degraded"
    return body


@app.get(
    "/api/version",
    tags=["system"],
    summary="Build & version metadata",
    description=(
        "Returns the current build's semantic version, git SHA (if available "
        "via the `STRUCTURAL_GIT_SHA` env), build date, runtime python "
        "version, and the deploy environment (dev / staging / prod)."
    ),
)
async def version():
    import sys as _sys
    import subprocess as _sp
    git_sha = os.getenv("STRUCTURAL_GIT_SHA", "")
    if not git_sha:
        # Best-effort: short SHA from git, capped at 12 chars.
        try:
            git_sha = _sp.check_output(
                ["git", "rev-parse", "--short=12", "HEAD"],
                cwd=str(Path(__file__).resolve().parent.parent.parent),
                stderr=_sp.DEVNULL,
                timeout=2,
            ).decode().strip()
        except Exception:
            git_sha = "unknown"
    return {
        "semver": app.version,
        "git_sha": git_sha,
        "build_date": os.getenv("STRUCTURAL_BUILD_DATE", "unknown"),
        "python_version": _sys.version.split()[0],
        "env": os.getenv("STRUCTURAL_ENV", "dev"),
    }


# --- API-key probe ---
@app.get(
    "/api/whoami",
    tags=["system"],
    summary="Reflect resolved tier for the current request",
    description=(
        "Useful for debugging X-API-Key auth. Returns the tier that "
        "rate-limiting will use and whether a valid key was supplied."
    ),
)
async def whoami(request: Request):
    from middleware.rate_limit import CURRENT_TIER as _T
    has_key = bool(request.headers.get("X-API-Key") or request.headers.get("x-api-key"))
    return {"tier": _T.get(), "api_key_supplied": has_key}


# --- Admin endpoint (requires admin tier) ---
@app.get(
    "/api/admin/keys",
    tags=["admin"],
    summary="List loaded API keys (admin only)",
    description="Reflects the current in-memory API key store. Requires tier=admin.",
    responses={
        200: {"description": "Key list"},
        401: {"description": "Missing or invalid X-API-Key"},
        403: {"description": "API key is valid but not admin tier"},
    },
)
async def admin_list_keys(request: Request):
    from middleware.rate_limit import CURRENT_TIER as _T
    from errors import Forbidden, Unauthenticated
    from auth.api_key import list_seed_keys

    tier = _T.get()
    if tier == "free":
        # No key supplied OR free-tier key — both end up as "free".
        if not (request.headers.get("X-API-Key") or request.headers.get("x-api-key")):
            raise Unauthenticated(detail="X-API-Key header required for /api/admin/*")
        raise Forbidden(detail="Admin tier required")
    if tier != "admin":
        raise Forbidden(detail="Admin tier required")
    keys = list_seed_keys()
    # Never return the raw `key` field — only metadata.
    return {
        "count": len(keys),
        "keys": [
            {
                "key_prefix": k.key[:10] + "..." if len(k.key) > 10 else k.key,
                "tier": k.tier,
                "owner_email": k.owner_email,
                "created_at": k.created_at,
                "revoked": k.revoked,
            }
            for k in keys
        ],
    }


# --- Serve frontend ---
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

# Phase Detector static files
PHASE_DIR = FRONTEND_DIR / "phase"
if PHASE_DIR.exists():
    app.mount("/phase/samples", StaticFiles(directory=PHASE_DIR / "samples"), name="phase_samples")
    if (PHASE_DIR / "data").exists():
        app.mount("/phase/data", StaticFiles(directory=PHASE_DIR / "data"), name="phase_data")


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/search")
async def search_page():
    return FileResponse(FRONTEND_DIR / "search.html")


@app.get("/phenomenon/{pid}")
async def phenomenon_page(pid: str):
    return FileResponse(FRONTEND_DIR / "phenomenon.html")


# Query-param deep-link form: /phenomenon?id=xxx (used by share-card and
# external embeds). JS-side resolvePhenomenonId() reads ?id= as fallback.
@app.get("/phenomenon")
async def phenomenon_page_query():
    return FileResponse(FRONTEND_DIR / "phenomenon.html")


# .html-suffixed forms — kept alive for legacy bookmarks and embedded
# CTAs that still hardcode /phenomenon.html or /analyze.html.
@app.get("/phenomenon.html")
async def phenomenon_html_alias():
    return FileResponse(FRONTEND_DIR / "phenomenon.html")


@app.get("/about")
async def about_page():
    return FileResponse(FRONTEND_DIR / "about.html")


@app.get("/discoveries")
async def discoveries_page():
    return FileResponse(FRONTEND_DIR / "discoveries.html")


@app.get("/phase", include_in_schema=False)
async def phase_root():
    f = FRONTEND_DIR / "phase" / "landing.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.get("/phase/company", include_in_schema=False)
async def phase_company():
    f = FRONTEND_DIR / "phase" / "company.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.get("/phase/screener", include_in_schema=False)
async def phase_screener():
    f = FRONTEND_DIR / "phase" / "screener.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.get("/phase/api/companies", include_in_schema=False)
async def phase_api_companies():
    import json as _json
    data_file = FRONTEND_DIR / "phase" / "data" / "companies_struct.jsonl"
    if not data_file.exists():
        logger.info("phases.fetch", ticker_count=0, source="missing_file")
        return JSONResponse({"count": 0, "companies": []})
    companies = []
    with open(data_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = _json.loads(line)
                if d.get("_error"):
                    continue
                companies.append(d)
            except Exception:
                continue
    # W14-D: ticker_count surfaces the response cardinality so we can
    # spot ingest regressions (e.g. file truncated to 0 rows) from a
    # log dashboard without sampling actual responses.
    logger.info("phases.fetch", ticker_count=len(companies))
    return JSONResponse({"count": len(companies), "companies": companies})


@app.get("/phase/redteam", include_in_schema=False)
async def phase_redteam():
    f = FRONTEND_DIR / "phase" / "redteam.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.post("/phase/api/redteam", include_in_schema=False)
async def phase_api_redteam(request: Request):
    """
    Run structural red team analysis on a user-supplied thesis.
    Returns 3 structurally vulnerable assumptions + historical precedents.
    """
    import json as _json
    import os as _os
    import urllib.request as _req
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    thesis = (body.get("thesis") or "").strip()
    ticker = (body.get("ticker") or "").strip()
    side = (body.get("side") or "").strip()

    if len(thesis) < 50:
        return JSONResponse({"error": "thesis too short (min 50 chars)"}, status_code=400)
    if len(thesis) > 5000:
        return JSONResponse({"error": "thesis too long (max 5000 chars)"}, status_code=400)

    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "LLM backend not configured"}, status_code=503)

    sys_prompt = """你是一个结构化红队分析师。用户给你一份投资 thesis，你用物理学/生物学/生态学/流行病学的结构视角找出 3 个最脆弱的假设——每个都配一个历史上同样结构失败过的真实公司案例。

**你的任务**：
1. 读 thesis，识别核心论点
2. 找出 3 个在结构动力学上最脆弱的假设
3. 每个脆弱点给一个结构解释 + 1-2 个历史先例

**严格输出 JSON（只输出 JSON，不要有任何其他文字）**：

```json
{
  "thesis_summary": "一句话总结 thesis 的核心假设（中文）",
  "vulnerabilities": [
    {
      "title": "脆弱点标题（一句话概括）",
      "assumption": "原 thesis 里的这个假设（直接引用）",
      "structural_flaw": "结构动力学上的漏洞：为什么这个假设在数学上站不住。用浅显中文说清楚，可以借物理/生物类比。",
      "precedent": "1-2 个历史案例：公司名 + 年份 + 同样假设怎么崩的（一段 50-100 字）",
      "trigger": "你应该监控什么指标/信号才能看到这个假设开始失效（具体可观测）"
    }
  ],
  "summary": "整体判断：这份 thesis 整体结构上是 robust 还是 fragile，一段 60-100 字（中文）"
}
```

规则：
- 必须 3 个 vulnerability，不多不少
- 中文叙述，只有必要的技术词或方程才用英文
- 历史先例必须具体（年份 + 数字 + 死法），不能是模糊的"很多公司"
- 不要道德说教，保持 analytical 语气
- 避免陈词滥调（"反身性"、"灰犀牛"这种词）
"""

    user_msg = f"""Thesis 分析任务：

公司: {ticker or "(未指定)"}
立场: {side or "(未指定)"}

Thesis 内容：
---
{thesis}
---

按系统指令输出 JSON。"""

    req_body = {
        "model": "anthropic/claude-sonnet-4.5",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 3000,
    }
    try:
        req = _req.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=_json.dumps(req_body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://beta.structural.bytedance.city",
                "X-Title": "phase-detector-redteam",
            },
        )
        with _req.urlopen(req, timeout=120) as resp:
            llm_data = _json.loads(resp.read())
        content = llm_data["choices"][0]["message"]["content"].strip()
        # Strip markdown fences
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        parsed = _json.loads(content)
        return JSONResponse(parsed)
    except Exception as e:
        return JSONResponse({"error": f"LLM call failed: {str(e)[:200]}"}, status_code=500)


@app.post("/phase/api/deep-report", include_in_schema=False)
async def phase_api_deep_report(request: Request):
    """Generate a deep structural report for a given company on demand."""
    import json as _json
    import os as _os
    import urllib.request as _req
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    ticker = (body.get("ticker") or "").strip()
    struct = body.get("struct") or {}
    if not ticker or not struct:
        return JSONResponse({"error": "ticker and struct required"}, status_code=400)

    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "LLM backend not configured"}, status_code=503)

    sys_prompt = """你是一个结构化金融分析师。用户给你一家公司的结构动力学元数据（dynamics_family、phase_state、feedback_topology、canonical_equation、critical_points 等），你要生成一份完整的中文深度报告，约 1500 字。

要求：
- 全程中文，必要的英文术语保留
- 公式用 KaTeX 行间格式 $$...$$ 或行内 $...$
- 借物理/生物/生态学的类比解释（如 Verhulst 逻辑斯蒂、SIR 流行病、Allee 效应、Hopf 分岔等），但要把数学翻译成人话
- 结构清晰：核心观点 → 为什么是这个动力学家族 → 三个理由 → 一份监控清单 → 风险/反方
- 用小标题、列表、表格、blockquote 让节奏分明
- 不要陈词滥调，不要"市场普遍认为"这种废话
- 标题用 ## 和 ###，不用 #

直接输出 Markdown，不要包在代码块里，不要前置说明。"""

    user_msg = f"""为这家公司生成结构化深度报告：

公司: {struct.get('name', '?')} ({ticker})
行业: {struct.get('industry', '?')}
市值: {struct.get('market_cap_usd', 0)/1e9:.0f}B USD
国家: {struct.get('country', '?')}

结构动力学：
- dynamics_family: {struct.get('dynamics_family', '?')}
- phase_state: {struct.get('phase_state', '?')}
- feedback_topology: {struct.get('feedback_topology', '?')}
- boundary_behavior: {struct.get('boundary_behavior', '?')}
- canonical_equation: {struct.get('canonical_equation', '?')}
- timescale_log10_s: {struct.get('timescale_log10_s', '?')}
- confidence: {struct.get('confidence', '?')}

为什么是这个家族：
{struct.get('why_this_family', '(无)')}

临界点：
{chr(10).join('- ' + str(cp) for cp in (struct.get('critical_points') or []))}

备注：
{struct.get('note', '(无)')}

按系统指令生成 1500 字左右的 Markdown 深度报告。"""

    req_body = {
        "model": "anthropic/claude-sonnet-4.5",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.4,
        "max_tokens": 4000,
    }
    try:
        req = _req.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=_json.dumps(req_body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://beta.structural.bytedance.city",
                "X-Title": "phase-detector-deep-report",
            },
        )
        with _req.urlopen(req, timeout=180) as resp:
            llm_data = _json.loads(resp.read())
        report = llm_data["choices"][0]["message"]["content"].strip()
        # Strip leading code fences if present
        if report.startswith("```"):
            lines = report.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            report = "\n".join(lines).strip()
        return JSONResponse({"ticker": ticker, "report": report})
    except Exception as e:
        return JSONResponse({"error": f"LLM call failed: {str(e)[:200]}"}, status_code=500)


@app.post("/phase/api/waitlist", include_in_schema=False)
async def phase_api_waitlist(request: Request):
    """Append email to waitlist file."""
    import json as _json
    import time as _time
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email or len(email) > 200:
        return JSONResponse({"error": "invalid email"}, status_code=400)
    waitlist_file = FRONTEND_DIR / "phase" / "data" / "waitlist.jsonl"
    waitlist_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "email": email,
        "ts": int(_time.time()),
        "iso": _time.strftime("%Y-%m-%d %H:%M:%S"),
        "ip": request.client.host if request.client else "?",
    }
    with open(waitlist_file, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    return JSONResponse({"ok": True})


@app.post("/phase/api/analogy", include_in_schema=False)
async def phase_api_analogy(request: Request):
    """Generate 3 historical structural analogies for a company."""
    import json as _json
    import os as _os
    import urllib.request as _req
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    ticker = (body.get("ticker") or "").strip()
    struct = body.get("struct") or {}
    if not ticker or not struct:
        return JSONResponse({"error": "ticker and struct required"}, status_code=400)

    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "LLM backend not configured"}, status_code=503)

    sys_prompt = """你是一个金融结构分析师。用户给你一家公司的当前结构动力学数据，你要在历史/其他行业的公司里找出 3 个「结构上最像」的历史时刻。

**严格规则**：
- 类比必须是真实存在的公司 + 真实的历史时期（有年份）
- 每个类比要具体到「XXXX 年的公司 X」，不是泛指「某某时期」
- 「那之后发生了什么」要给真实的数据（收入增速、股价、用户数等）
- 不要预测用户这家公司的未来，只展示历史公司的真实轨迹
- 避免老生常谈的例子（不要三个全是苹果/诺基亚/柯达）

**严格输出 JSON（不要任何其他文字）**：

```json
{
  "current_summary": "一句话总结用户这家公司当前的结构状态（中文，≤40 字）",
  "analogies": [
    {
      "company": "公司名（英文或中文）",
      "ticker": "当时的股票代码（可选）",
      "period": "2015-2018（具体年份区间）",
      "structural_similarity": "结构相似在哪（2-3 句中文）。引用同样的 dynamics_family 或 phase_state",
      "quantitative_parallel": "关键定量对照（1-2 个数字对照）",
      "what_happened": {
        "1y": "1 年后（具体数据 + 事件）",
        "3y": "3 年后（具体数据 + 事件）",
        "5y": "5 年后（具体数据 + 事件，如果走完了）"
      },
      "lesson_for_current": "对用户这家公司的启示：如果走这条路会发生什么（1-2 句）"
    }
  ],
  "summary": "3 个类比的整体主题一句话（中文，≤50 字）"
}
```

**要求**：
- 必须 3 个 analogy，不多不少
- 三个类比要代表不同的可能路径（乐观、悲观、中性）
- 中文叙述，保持 analytical 语气
- 定量数据要真实可查
"""

    user_msg = f"""公司: {struct.get('name', '?')} ({ticker})
行业: {struct.get('industry', '?')}
市值: {struct.get('market_cap_usd', 0)/1e9:.0f}B USD
国家: {struct.get('country', '?')}

结构动力学：
- dynamics_family: {struct.get('dynamics_family', '?')}
- phase_state: {struct.get('phase_state', '?')}
- feedback_topology: {struct.get('feedback_topology', '?')}
- boundary_behavior: {struct.get('boundary_behavior', '?')}
- canonical_equation: {struct.get('canonical_equation', '?')}
- confidence: {struct.get('confidence', '?')}

为什么是这个家族：
{struct.get('why_this_family', '(无)')}

临界点：
{chr(10).join('- ' + str(cp) for cp in (struct.get('critical_points') or []))}

备注：
{struct.get('note', '(无)')}

请找 3 个在这个结构动力学上最相似的真实历史公司 + 时期，按系统指令输出 JSON。"""

    # Kimi K2 是主力（便宜 + 对美股历史知识够用），Sonnet 是 fallback
    # MiniMax M2 最快（~130 t/s），Grok-4-fast 次之，Kimi 和 Sonnet 作 fallback
    models = ["minimax/minimax-m2", "x-ai/grok-4-fast", "moonshotai/kimi-k2-0905", "anthropic/claude-sonnet-4.5"]
    last_err = None
    for model in models:
        req_body = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.4,
            "max_tokens": 3500,
        }
        try:
            req = _req.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=_json.dumps(req_body).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://beta.structural.bytedance.city",
                    "X-Title": "phase-detector-analogy",
                },
            )
            with _req.urlopen(req, timeout=180) as resp:
                llm_data = _json.loads(resp.read())
            content = llm_data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            parsed = _json.loads(content)
            parsed["_model"] = model
            return JSONResponse(parsed)
        except Exception as e:
            last_err = f"{model}: {str(e)[:150]}"
            continue
    return JSONResponse({"error": f"All LLMs failed. Last: {last_err}"}, status_code=500)


@app.get("/phase/analogy", include_in_schema=False)
async def phase_analogy_page():
    f = FRONTEND_DIR / "phase" / "analogy.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.post("/phase/api/analogy-detail", include_in_schema=False)
async def phase_api_analogy_detail(request: Request):
    """Deep analysis (~1500-2000 zh) on ONE specific historical analogy."""
    import json as _json
    import os as _os
    import urllib.request as _req
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    ticker = (body.get("ticker") or "").strip()
    struct = body.get("struct") or {}
    target = body.get("target") or {}
    if not ticker or not struct or not target:
        return JSONResponse({"error": "ticker/struct/target required"}, status_code=400)

    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "LLM backend not configured"}, status_code=503)

    sys_prompt = """你是一个给普通投资经理（不是学术研究员）写分析的金融作者。

用户给你两家公司：
- 「当前公司」：用户正在研究的公司（有结构动力学数据）
- 「历史类比」：粗筛出的一个最接近的历史公司时期

**核心原则 —— 要让一个没读过物理学的 PM 看懂**：
1. 先讲故事，后讲原理。每段先用人话说清楚发生了什么，再引入需要的技术点
2. 每个英文术语第一次出现时必须有中文注释：Verhulst logistic（饱和增长模型）、Fold bifurcation（鞍结突跳）、capex（资本开支）
3. 每个公式必须有紧跟其后的一句大白话翻译，不要假设读者会解释方程
4. 用"每过一年增长多少"代替"一阶导数"；用"接近上限后新增越来越慢"代替"边际递减"
5. 引用数字要给上下文——不是"ARPU $41"，而是"ARPU $41，相当于现在 Netflix 标准档价格的 3.4 倍"
6. 不要用"反身性、灰犀牛、范式转移"这些词

**结构（严格按顺序写，用 Markdown 标题）**：

## 一、两家公司在结构上为什么像

用大白话解释两家公司面对的是同一种数学结构（比如"都在一条 S 型增长曲线的拐点上"）。
然后给出经典方程 + 翻译：

$$\\frac{dN}{dt} = r \\cdot N \\cdot (1 - N/K)$$

*这个方程的意思是：现在的用户数叫 N，天花板叫 K，增长速度在 N 离 K 越近时越慢。*

然后列出两家公司的参数对照表：

| 参数 | 当前公司 | 历史类比 | 含义 |
|------|---------|---------|------|
| K（天花板）| 4.5 亿订户 | 1.05 亿有线家庭 | 理论最大用户池 |
| N/K（饱和度）| 62% | 87% | 离天花板多远 |
| r（每年增速）| 6% | 3% | 当前增长节奏 |

结尾说一句：这两家公司**为什么**在数学上处于同一阶段。

## 二、历史公司当时到底发生了什么

400-500 字的故事，要像在讲新闻。要求：
- 具体 CEO 名字、具体并购金额、具体战略代号
- 至少一个"小插曲"（比如内部争议、关键人离职、外部冲击）
- 分 2-3 个阶段，每阶段带年份
- 避免"管理层做出战略调整"这种空话，要说"XX CEO 在 X 年 X 月做了什么，付出 Y 代价，换来 Z 结果"

## 三、当时的几个"如果当时选别的路"

至少 2 个反事实：
- "如果当时 CEO 选择 X 而不是 Y，后来会像 XX 公司那样..."（要对比真实公司的结局）
- 每个反事实要有一句"为什么最终没走这条路"的解释

## 四、这些信号，当时的投资者能看出来吗？

列 4-6 条具体信号（不要"市场情绪转变"这种虚的）。每条格式：
- **信号名**：具体是什么（举例"订户净新增从季度 80 万降到 20 万"）
- **阈值**：超过多少值得警惕
- **哪里能看到**：财报第几页？earnings call 里听什么？

## 五、那对当前公司意味着什么

最重要的一段。给 PM 可以拿去用的东西：

**如果走类比这条路**：
- 3 年 / 5 年的量化预测（订户、收入、毛利率、估值区间）
- 用"从 X 变到 Y"的具体数字，不是"可能下降"

**想避开这条路需要做什么**：
- 具体要看管理层做哪几件事才算"没走这条路"
- 给 2-3 个可观测的"转折信号"（下季度如果 XX 指标出现 YY，说明选了不同路径）

**这次不一样的地方**：
- 技术/时代/地域哪些不同
- 这些差异会让结局**偏向**哪边

---

**写作风格提醒**：
- 中文为主，必要术语用英文 + 中文解释
- 数字要具体到年份 / 百分比 / 金额
- 用表格、列表、blockquote 让节奏分明
- 每个公式后必须跟一句"大白话的意思是..."
- 开头一句话概括本文结论（不是"历史的教训是..."这种废话，要具体）
- 结尾一句话给行动建议

直接输出 Markdown。
"""

    user_msg = f"""【当前公司】{struct.get('name', '?')} ({ticker})
行业: {struct.get('industry', '?')}
市值: {struct.get('market_cap_usd', 0)/1e9:.0f}B USD
dynamics_family: {struct.get('dynamics_family', '?')}
phase_state: {struct.get('phase_state', '?')}
feedback_topology: {struct.get('feedback_topology', '?')}
canonical_equation: {struct.get('canonical_equation', '?')}
why_this_family: {struct.get('why_this_family', '?')}
critical_points: {', '.join(struct.get('critical_points') or [])}
note: {struct.get('note', '?')}

【历史类比】
公司: {target.get('company', '?')}
时期: {target.get('period', '?')}
之前的粗略描述: {target.get('structural_similarity', '?')}
之前的定量对照: {target.get('quantitative_parallel', '?')}
之前的简要轨迹: 1y={target.get('what_happened', {}).get('1y', '?')} | 3y={target.get('what_happened', {}).get('3y', '?')} | 5y={target.get('what_happened', {}).get('5y', '?')}
之前给出的启示: {target.get('lesson_for_current', '?')}

---

以"历史类比"为主角，按系统指令写一份 1500-2000 字的深度分析。把粗略描述展开到"真的了解了这家公司在那个时期发生的一切"的深度。"""

    # Sonnet 4.5 为主（深度分析质量最好），Kimi K2 作 fallback
    models = ["anthropic/claude-sonnet-4.5", "moonshotai/kimi-k2-0905"]
    last_err = None
    for model in models:
        req_body = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.35,
            "max_tokens": 8000,
        }
        try:
            req = _req.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=_json.dumps(req_body).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://beta.structural.bytedance.city",
                    "X-Title": "phase-detector-analogy-detail",
                },
            )
            with _req.urlopen(req, timeout=240) as resp:
                llm_data = _json.loads(resp.read())
            report = llm_data["choices"][0]["message"]["content"].strip()
            if report.startswith("```"):
                lines = report.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                report = "\n".join(lines).strip()
            return JSONResponse({
                "ticker": ticker,
                "target_company": target.get("company"),
                "target_period": target.get("period"),
                "report": report,
                "_model": model,
            })
        except Exception as e:
            last_err = f"{model}: {str(e)[:200]}"
            continue
    return JSONResponse({"error": f"All LLMs failed. Last: {last_err}"}, status_code=500)


@app.get("/phase/analogy/detail", include_in_schema=False)
async def phase_analogy_detail_page():
    f = FRONTEND_DIR / "phase" / "analogy_detail.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.post("/phase/api/analogy-detail/stream", include_in_schema=False)
async def phase_api_analogy_detail_stream(request: Request):
    """Streaming deep analysis — forwards OpenRouter SSE to the browser."""
    import json as _json
    import os as _os
    import urllib.request as _req

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    ticker = (body.get("ticker") or "").strip()
    struct = body.get("struct") or {}
    target = body.get("target") or {}
    if not ticker or not struct or not target:
        return JSONResponse({"error": "ticker/struct/target required"}, status_code=400)

    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "LLM backend not configured"}, status_code=503)

    sys_prompt = """你是一个给普通投资经理（不是学术研究员）写分析的金融作者。

用户给你两家公司：
- 「当前公司」：用户正在研究的公司（有结构动力学数据）
- 「历史类比」：粗筛出的一个最接近的历史公司时期

**核心原则 —— 要让一个没读过物理学的 PM 看懂**：
1. 先讲故事，后讲原理。每段先用人话说清楚发生了什么，再引入需要的技术点
2. 每个英文术语第一次出现时必须有中文注释：Verhulst logistic（饱和增长模型）、Fold bifurcation（鞍结突跳）、capex（资本开支）
3. 每个公式必须有紧跟其后的一句大白话翻译，不要假设读者会解释方程
4. 用"每过一年增长多少"代替"一阶导数"；用"接近上限后新增越来越慢"代替"边际递减"
5. 引用数字要给上下文——不是"ARPU $41"，而是"ARPU $41，相当于现在 Netflix 标准档价格的 3.4 倍"
6. 不要用"反身性、灰犀牛、范式转移"这些词

**结构（严格按顺序写，用 Markdown 标题）**：

## 一、两家公司在结构上为什么像

用大白话解释两家公司面对的是同一种数学结构（比如"都在一条 S 型增长曲线的拐点上"）。
然后给出经典方程 + 翻译：

$$\\frac{dN}{dt} = r \\cdot N \\cdot (1 - N/K)$$

*这个方程的意思是：现在的用户数叫 N，天花板叫 K，增长速度在 N 离 K 越近时越慢。*

然后列出两家公司的参数对照表：

| 参数 | 当前公司 | 历史类比 | 含义 |
|------|---------|---------|------|
| K（天花板）| 4.5 亿订户 | 1.05 亿有线家庭 | 理论最大用户池 |
| N/K（饱和度）| 62% | 87% | 离天花板多远 |
| r（每年增速）| 6% | 3% | 当前增长节奏 |

结尾说一句：这两家公司**为什么**在数学上处于同一阶段。

## 二、历史公司当时到底发生了什么

400-500 字的故事，要像在讲新闻。要求：
- 具体 CEO 名字、具体并购金额、具体战略代号
- 至少一个"小插曲"（比如内部争议、关键人离职、外部冲击）
- 分 2-3 个阶段，每阶段带年份
- 避免"管理层做出战略调整"这种空话，要说"XX CEO 在 X 年 X 月做了什么，付出 Y 代价，换来 Z 结果"

## 三、当时的几个"如果当时选别的路"

至少 2 个反事实：
- "如果当时 CEO 选择 X 而不是 Y，后来会像 XX 公司那样..."（要对比真实公司的结局）
- 每个反事实要有一句"为什么最终没走这条路"的解释

## 四、这些信号，当时的投资者能看出来吗？

列 4-6 条具体信号（不要"市场情绪转变"这种虚的）。每条格式：
- **信号名**：具体是什么（举例"订户净新增从季度 80 万降到 20 万"）
- **阈值**：超过多少值得警惕
- **哪里能看到**：财报第几页？earnings call 里听什么？

## 五、那对当前公司意味着什么

最重要的一段。给 PM 可以拿去用的东西：

**如果走类比这条路**：
- 3 年 / 5 年的量化预测（订户、收入、毛利率、估值区间）
- 用"从 X 变到 Y"的具体数字，不是"可能下降"

**想避开这条路需要做什么**：
- 具体要看管理层做哪几件事才算"没走这条路"
- 给 2-3 个可观测的"转折信号"（下季度如果 XX 指标出现 YY，说明选了不同路径）

**这次不一样的地方**：
- 技术/时代/地域哪些不同
- 这些差异会让结局**偏向**哪边

---

**写作风格提醒**：
- 中文为主，必要术语用英文 + 中文解释
- 数字要具体到年份 / 百分比 / 金额
- 用表格、列表、blockquote 让节奏分明
- 每个公式后必须跟一句"大白话的意思是..."
- 开头一句话概括本文结论（不是"历史的教训是..."这种废话，要具体）
- 结尾一句话给行动建议

直接输出 Markdown。
"""

    user_msg = f"""【当前公司】{struct.get('name', '?')} ({ticker})
行业: {struct.get('industry', '?')}
市值: {struct.get('market_cap_usd', 0)/1e9:.0f}B USD
dynamics_family: {struct.get('dynamics_family', '?')}
phase_state: {struct.get('phase_state', '?')}
feedback_topology: {struct.get('feedback_topology', '?')}
canonical_equation: {struct.get('canonical_equation', '?')}
why_this_family: {struct.get('why_this_family', '?')}
critical_points: {', '.join(struct.get('critical_points') or [])}
note: {struct.get('note', '?')}

【历史类比】
公司: {target.get('company', '?')}
时期: {target.get('period', '?')}
之前的粗略描述: {target.get('structural_similarity', '?')}
之前的定量对照: {target.get('quantitative_parallel', '?')}
之前的简要轨迹: 1y={target.get('what_happened', {}).get('1y', '?')} | 3y={target.get('what_happened', {}).get('3y', '?')} | 5y={target.get('what_happened', {}).get('5y', '?')}
之前给出的启示: {target.get('lesson_for_current', '?')}

---

以"历史类比"为主角，按系统指令写一份 1500-2000 字的深度分析。"""

    model = body.get("model") or "anthropic/claude-sonnet-4.5"

    req_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.35,
        "max_tokens": 8000,
        "stream": True,
    }

    import httpx as _httpx
    import asyncio as _asyncio

    async def event_stream():
        yield f"event: meta\ndata: {_json.dumps({'model': model, 'ticker': ticker})}\n\n"
        keepalive_task = None
        q = _asyncio.Queue()
        stop_event = _asyncio.Event()

        async def producer():
            try:
                timeout = _httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0)
                async with _httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        "https://openrouter.ai/api/v1/chat/completions",
                        json=req_body,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://beta.structural.bytedance.city",
                            "X-Title": "phase-detector-async-stream",
                            "Accept": "text/event-stream",
                        },
                    ) as resp:
                        if resp.status_code >= 400:
                            err_body = await resp.aread()
                            await q.put(("error", f"upstream {resp.status_code}: {err_body[:300].decode(errors='replace')}"))
                            return
                        async for raw in resp.aiter_lines():
                            await q.put(("line", raw))
            except _httpx.ReadTimeout:
                await q.put(("error", "upstream 无响应 180 秒（LLM 停止生成）"))
            except Exception as _e:
                await q.put(("error", f"{type(_e).__name__}: {str(_e)[:200]}"))
            finally:
                await q.put(("end", None))
                stop_event.set()

        async def keepalive():
            try:
                while not stop_event.is_set():
                    await _asyncio.sleep(10)
                    if not stop_event.is_set():
                        await q.put(("keepalive", None))
            except _asyncio.CancelledError:
                pass

        prod_task = _asyncio.create_task(producer())
        keepalive_task = _asyncio.create_task(keepalive())

        try:
            while True:
                kind, payload = await q.get()
                if kind == "end":
                    break
                elif kind == "keepalive":
                    yield ": keepalive\n\n"
                elif kind == "error":
                    yield f"event: error\ndata: {_json.dumps({'error': payload})}\n\n"
                elif kind == "line":
                    if payload:
                        yield payload + "\n"
                    else:
                        yield "\n"
        finally:
            keepalive_task.cancel()
            try:
                await _asyncio.wait_for(prod_task, timeout=2.0)
            except Exception:
                pass

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/phase/api/analogy/stream", include_in_schema=False)
async def phase_api_analogy_stream(request: Request):
    """Streaming list view — 3 analogies as JSON, but streamed char-by-char."""
    import json as _json
    import os as _os
    import urllib.request as _req
    from datetime import datetime as _dt

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    ticker = (body.get("ticker") or "").strip()
    struct = body.get("struct") or {}
    if not ticker or not struct:
        return JSONResponse({"error": "ticker/struct required"}, status_code=400)

    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "LLM backend not configured"}, status_code=503)

    today = _dt.now().strftime("%Y-%m-%d")

    sys_prompt = """你是一个金融结构分析师。用户给你一家公司的当前结构动力学数据，你要在历史/其他行业的公司里找出 3 个「结构上最像」的历史时刻。

**严格规则**：
- 类比必须是真实存在的公司 + 真实的历史时期（有年份）
- 每个类比要具体到「XXXX 年的公司 X」，不是泛指「某某时期」
- 「那之后发生了什么」要给真实的数据（收入增速、股价、用户数等）
- 不要预测用户这家公司的未来，只展示历史公司的真实轨迹
- 避免老生常谈的例子（不要三个全是苹果/诺基亚/柯达）
- 用户在 system prompt 中会告知「今天日期」——你分析当前公司状态时要用那个日期对应的最新业务情况

**严格输出 JSON（不要任何其他文字）**：

```json
{
  "current_summary": "一句话总结用户这家公司当前的结构状态（中文，≤40 字）",
  "analogies": [
    {
      "company": "公司名",
      "ticker": "当时的股票代码（可选）",
      "period": "2015-2018（具体年份区间）",
      "structural_similarity": "结构相似在哪（2-3 句中文）",
      "quantitative_parallel": "关键定量对照（1-2 个数字对照）",
      "what_happened": {
        "1y": "1 年后（具体数据 + 事件）",
        "3y": "3 年后（具体数据 + 事件）",
        "5y": "5 年后（具体数据 + 事件）"
      },
      "lesson_for_current": "对用户这家公司的启示（1-2 句）"
    }
  ],
  "summary": "3 个类比的整体主题一句话（中文，≤50 字）"
}
```
"""

    user_msg = f"""【今天是】{today}（请用这个日期对应的最新公司状态分析）

公司: {struct.get('name', '?')} ({ticker})
行业: {struct.get('industry', '?')}
市值: {struct.get('market_cap_usd', 0)/1e9:.0f}B USD
国家: {struct.get('country', '?')}

结构动力学：
- dynamics_family: {struct.get('dynamics_family', '?')}
- phase_state: {struct.get('phase_state', '?')}
- feedback_topology: {struct.get('feedback_topology', '?')}
- boundary_behavior: {struct.get('boundary_behavior', '?')}
- canonical_equation: {struct.get('canonical_equation', '?')}
- confidence: {struct.get('confidence', '?')}

为什么是这个家族：{struct.get('why_this_family', '(无)')}
临界点：{chr(10).join('- ' + str(cp) for cp in (struct.get('critical_points') or []))}
备注：{struct.get('note', '(无)')}

按系统指令输出 JSON。"""

    model = body.get("model") or "x-ai/grok-4-fast"

    req_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.4,
        "max_tokens": 3500,
        "stream": True,
    }

    import httpx as _httpx
    import asyncio as _asyncio

    async def event_stream():
        yield f"event: meta\ndata: {_json.dumps({'model': model, 'ticker': ticker})}\n\n"
        keepalive_task = None
        q = _asyncio.Queue()
        stop_event = _asyncio.Event()

        async def producer():
            try:
                timeout = _httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0)
                async with _httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        "https://openrouter.ai/api/v1/chat/completions",
                        json=req_body,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://beta.structural.bytedance.city",
                            "X-Title": "phase-detector-async-stream",
                            "Accept": "text/event-stream",
                        },
                    ) as resp:
                        if resp.status_code >= 400:
                            err_body = await resp.aread()
                            await q.put(("error", f"upstream {resp.status_code}: {err_body[:300].decode(errors='replace')}"))
                            return
                        async for raw in resp.aiter_lines():
                            await q.put(("line", raw))
            except _httpx.ReadTimeout:
                await q.put(("error", "upstream 无响应 180 秒（LLM 停止生成）"))
            except Exception as _e:
                await q.put(("error", f"{type(_e).__name__}: {str(_e)[:200]}"))
            finally:
                await q.put(("end", None))
                stop_event.set()

        async def keepalive():
            try:
                while not stop_event.is_set():
                    await _asyncio.sleep(10)
                    if not stop_event.is_set():
                        await q.put(("keepalive", None))
            except _asyncio.CancelledError:
                pass

        prod_task = _asyncio.create_task(producer())
        keepalive_task = _asyncio.create_task(keepalive())

        try:
            while True:
                kind, payload = await q.get()
                if kind == "end":
                    break
                elif kind == "keepalive":
                    yield ": keepalive\n\n"
                elif kind == "error":
                    yield f"event: error\ndata: {_json.dumps({'error': payload})}\n\n"
                elif kind == "line":
                    if payload:
                        yield payload + "\n"
                    else:
                        yield "\n"
        finally:
            keepalive_task.cancel()
            try:
                await _asyncio.wait_for(prod_task, timeout=2.0)
            except Exception:
                pass

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/phase/timeline", include_in_schema=False)
async def phase_timeline_page():
    f = FRONTEND_DIR / "phase" / "timeline.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.get("/phase/api/timeline/list", include_in_schema=False)
async def phase_api_timeline_list():
    """List all companies that have a timeline."""
    import json as _json
    data_file = FRONTEND_DIR / "phase" / "data" / "timeline_snapshots.jsonl"
    if not data_file.exists():
        return JSONResponse({"count": 0, "tickers": []})
    items = []
    with open(data_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = _json.loads(line)
                items.append({
                    "ticker": d.get("ticker"),
                    "name": d.get("name"),
                    "industry": d.get("industry"),
                    "n_snapshots": len(d.get("snapshots", [])),
                })
            except Exception:
                continue
    return JSONResponse({"count": len(items), "tickers": items})


@app.get("/phase/api/timeline/{ticker:path}", include_in_schema=False)
async def phase_api_timeline(ticker: str):
    """Return the timeline snapshots for one company."""
    import json as _json
    data_file = FRONTEND_DIR / "phase" / "data" / "timeline_snapshots.jsonl"
    if not data_file.exists():
        return JSONResponse({"error": "no timeline data"}, status_code=404)
    with open(data_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = _json.loads(line)
            except Exception:
                continue
            if d.get("ticker") == ticker:
                return JSONResponse(d)
    return JSONResponse({"error": f"no timeline for {ticker}"}, status_code=404)


@app.get("/phase/about", include_in_schema=False)
async def phase_about_page():
    f = FRONTEND_DIR / "phase" / "about.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.post("/phase/api/memo/stream", include_in_schema=False)
async def phase_api_memo_stream(request: Request):
    """流式生成投资 memo 模板 — Sonnet 4.5，6 板块结构化 Markdown。"""
    import json as _json
    import os as _os
    import asyncio as _asyncio
    import httpx as _httpx
    from datetime import datetime as _dt

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    ticker = (body.get("ticker") or "").strip()
    struct = body.get("struct") or {}
    side = (body.get("side") or "long").strip()  # long / short / watch
    if not ticker or not struct:
        return JSONResponse({"error": "ticker and struct required"}, status_code=400)

    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return JSONResponse({"error": "LLM backend not configured"}, status_code=503)

    today = _dt.now().strftime("%Y-%m-%d")

    side_desc = {
        "long": "多头（你正在论证为什么值得买入或持有）",
        "short": "空头（你正在论证为什么值得做空或离场）",
        "watch": "观察（中性立场，想全面理解这家公司的结构）",
    }.get(side, "多头")

    sys_prompt = """你是一个专业的投资 memo 写手，擅长用结构动力学的视角给买方分析师、独立研究员、财经博主写一份可以直接拿去工作的 memo 模板。

你的输出会被用户直接粘到 Notion / Substack / 邮件 / PM memo 里，所以**必须是可以立即使用的成品**，不是草稿。

**严格按以下 6 个板块写 Markdown，每个板块用 `##` 标题，顺序不能换**：

## TLDR
一句话总结。格式：「{公司名}结构上处于 {phase_state}（{dynamics_family} 动力学），{立场}的关键论点是 {一句话}。未来 6 个月最值得盯的是 {一个指标}。」
要求：≤80 字，信息密度高，可以单独摘出来用。

## 一、结构画像

用一段话（150-200 字）说清楚这家公司的结构动力学画像：
- 当前的 `dynamics_family` 是什么，什么经典物理/生物方程对应
- 当前的 `phase_state` 是什么意思
- 关键的 `canonical_equation` 写出来（合法 LaTeX，用 `$$...$$`），并用一句大白话翻译
- 为什么市场对这家公司的结构性评估可能存在偏差

## 二、三个历史类比

找 3 个真实存在过的公司 + 时期，它们在当时的结构动力学和这家公司现在最接近。每个类比写一段（80-120 字）：
- 公司名 + 时期（具体年份，如"1998-2001 的 Cisco"）
- 结构为什么相像（1-2 句）
- 那之后 3-5 年发生了什么（给真实数据）
- 对当前公司的启示（一句话）

## 三、核心观点 + 支撑

根据用户的立场（多/空/观察），给出 3 条立论，每条包含：
- 观点（一句话，黑体）
- 结构动力学上的机制（2-3 句，引用已有的 canonical_equation 或 critical_points）
- 支撑证据（引用具体数字，如果不确定就给区间）
- 潜在反驳（一句话，承认这个观点什么时候会被推翻）

## 四、五个核心风险

按严重程度排序。每条格式：
- **风险名**（一句话概括）
- **结构机制**：这个风险在什么数学结构下发生（1-2 句）
- **触发条件**：什么可观测信号会让这个风险物化
- **如果发生**：对公司的具体冲击（估值、增速、相位切换）

## 五、十个监控指标

每条是**具体可查的指标 + 阈值 + 信号含义**：
| # | 指标 | 阈值 | 在哪看到 | 含义 |
|---|------|------|---------|------|
| 1 | DAU 季度环比 | 连续 2 季 < 1% | 10-Q 用户指标部分 | 饱和信号确认 |
| 2 | ... | ... | ... | ... |

必须用表格。10 条都要具体，不要"市场情绪" / "行业环境"这类虚的。

## 六、六个月后的可证伪假设

给 3 条**可以在 6 个月后用数据验证的**具体预测。每条格式：
- **假设**：可验证的陈述（比如"NFLX 2026-Q2 全球订户将 < 2.85 亿"）
- **为什么这么预测**：结构动力学推理（2-3 句）
- **验证方法**：6 个月后看什么数据就能判断对错

这三条必须是**真的可以打脸的**——不能模糊到"未来可能放缓"这种无法证伪的话。

---

**硬性要求**：
1. 所有公式必须是合法 KaTeX（`\alpha` 不要 `α`；`\frac{}{}`  不要 `/`；不要中文括号注释）
2. 所有数字必须有年份和单位（不要"最近" / "显著"）
3. 引用公司名必须完整（"Netflix Inc." 不是"奈飞"）
4. 不要结尾告别语"希望对你有帮助"等
5. 直接开始写 Markdown，不要前置"以下是..."或"好的，"
6. 全中文，必要术语保留英文原词 + 中文注释
7. **字数 1500-2500**（不要太短，也不要超 3000）
"""

    user_msg = f"""【今天是】{today}

【公司】{struct.get('name', '?')} ({ticker})
行业: {struct.get('industry', '?')}
市值: {struct.get('market_cap_usd', 0)/1e9:.0f}B USD
国家: {struct.get('country', '?')}

【结构动力学】
- dynamics_family: {struct.get('dynamics_family', '?')}
- phase_state: {struct.get('phase_state', '?')}
- feedback_topology: {struct.get('feedback_topology', '?')}
- boundary_behavior: {struct.get('boundary_behavior', '?')}
- canonical_equation: {struct.get('canonical_equation', '?')}
- confidence: {struct.get('confidence', '?')}

【为什么是这个家族】
{struct.get('why_this_family', '(无)')}

【关键临界点】
{chr(10).join('- ' + str(cp) for cp in (struct.get('critical_points') or []))}

【备注】
{struct.get('note', '(无)')}

【用户立场】{side_desc}

---

按系统指令生成一份 1500-2500 字的 Markdown memo，严格 6 个板块的顺序，用户会直接粘到工作文档里。
"""

    model = "anthropic/claude-sonnet-4.5"
    req_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
        "stream": True,
    }

    async def event_stream():
        yield f"event: meta\ndata: {_json.dumps({'model': model, 'ticker': ticker, 'side': side, 'today': today})}\n\n"

        q = _asyncio.Queue()
        stop_event = _asyncio.Event()

        async def producer():
            try:
                timeout = _httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0)
                async with _httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        "https://openrouter.ai/api/v1/chat/completions",
                        json=req_body,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://beta.structural.bytedance.city",
                            "X-Title": "phase-detector-memo",
                            "Accept": "text/event-stream",
                        },
                    ) as resp:
                        if resp.status_code >= 400:
                            err_body = await resp.aread()
                            await q.put(("error", f"upstream {resp.status_code}: {err_body[:300].decode(errors='replace')}"))
                            return
                        async for raw in resp.aiter_lines():
                            await q.put(("line", raw))
            except _httpx.ReadTimeout:
                await q.put(("error", "upstream 无响应 180 秒"))
            except Exception as _e:
                await q.put(("error", f"{type(_e).__name__}: {str(_e)[:200]}"))
            finally:
                await q.put(("end", None))
                stop_event.set()

        async def keepalive():
            try:
                while not stop_event.is_set():
                    await _asyncio.sleep(10)
                    if not stop_event.is_set():
                        await q.put(("keepalive", None))
            except _asyncio.CancelledError:
                pass

        prod_task = _asyncio.create_task(producer())
        keepalive_task = _asyncio.create_task(keepalive())

        try:
            while True:
                kind, payload = await q.get()
                if kind == "end":
                    break
                elif kind == "keepalive":
                    yield ": keepalive\n\n"
                elif kind == "error":
                    yield f"event: error\ndata: {_json.dumps({'error': payload})}\n\n"
                elif kind == "line":
                    if payload:
                        yield payload + "\n"
                    else:
                        yield "\n"
        finally:
            keepalive_task.cancel()
            try:
                await _asyncio.wait_for(prod_task, timeout=2.0)
            except Exception:
                pass

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/phase/memo", include_in_schema=False)
async def phase_memo_page():
    f = FRONTEND_DIR / "phase" / "memo.html"
    return FileResponse(f) if f.exists() else FileResponse(FRONTEND_DIR / "404.html", status_code=404)


@app.get("/classes")
async def classes_page():
    return FileResponse(FRONTEND_DIR / "classes.html")


@app.get("/paper/{slug}")
async def paper_page(slug: str):
    # Whitelist: serve the same HTML renderer, which picks up the slug from URL
    return FileResponse(FRONTEND_DIR / "paper.html")


@app.get("/analyze")
async def analyze_page():
    return FileResponse(FRONTEND_DIR / "analyze.html")


# Legacy alias: ask.js (W3-B deep-analysis CTA) still emits /analyze.html?text_a=
# Keep serving it to avoid breaking already-rendered thread items with hardcoded links.
@app.get("/analyze.html")
async def analyze_html_alias():
    return FileResponse(FRONTEND_DIR / "analyze.html")


@app.get("/papers")
async def papers_page():
    return FileResponse(FRONTEND_DIR / "papers.html")


@app.get("/methods")
async def methods_page():
    return FileResponse(FRONTEND_DIR / "methods.html")


@app.get("/taxonomy-v2")
async def taxonomy_v2_page():
    return FileResponse(FRONTEND_DIR / "taxonomy-v2.html")


@app.get("/start-here")
async def start_here_page():
    return FileResponse(FRONTEND_DIR / "start-here.html")


@app.get("/learn")
async def learn_page():
    return FileResponse(FRONTEND_DIR / "learn.html")


# --- SEO: robots.txt + sitemap.xml (W3-D, 2026-05-14) ---
@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return FileResponse(FRONTEND_DIR / "robots.txt", media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    return FileResponse(FRONTEND_DIR / "sitemap.xml", media_type="application/xml")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    # API routes return JSON; only HTML pages get the full 404 template.
    path = request.url.path or ""
    if path.startswith("/api"):
        return JSONResponse({"detail": "not found"}, status_code=404)
    return FileResponse(FRONTEND_DIR / "404.html", status_code=404)
