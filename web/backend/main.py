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
from fastapi.responses import FileResponse, JSONResponse

# Ensure structural_isomorphism package is importable.
# Prefer env var, else walk up from this file (web/backend/main.py -> project root).
_project_root = os.getenv("STRUCTURAL_PROJECT_ROOT") or str(
    Path(__file__).resolve().parent.parent.parent
)
sys.path.insert(0, _project_root)

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("structural.web")

# Shared state
app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load the search engine once."""
    logger.info("Starting Structural Web Backend...")
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
    description="跨领域结构同构搜索引擎",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Rate limiter (slowapi) ---
# The Limiter instance lives in services/rate_limit.py so routers can import
# it without a circular dependency on this module.
from services.rate_limit import limiter  # noqa: E402
if limiter is not None:
    try:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    except Exception as e:  # pragma: no cover
        logger.warning(f"rate limit handler wiring failed: {e}")

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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- Shared getter for dependency ---
def get_search_service():
    return app_state.get("search")


# --- API routes ---
from api import search, phenomenon, mapping, daily, examples, suggest, discoveries, analyze, synthesize  # noqa

app.include_router(search.router, prefix="/api")
app.include_router(phenomenon.router, prefix="/api")
app.include_router(mapping.router, prefix="/api")
app.include_router(daily.router, prefix="/api")
app.include_router(examples.router, prefix="/api")
app.include_router(suggest.router, prefix="/api")
app.include_router(discoveries.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(synthesize.router, prefix="/api")


@app.get("/api/health")
async def health():
    svc = app_state.get("search")
    return {
        "status": "ok",
        "kb_size": svc.kb_size if svc else 0,
        "llm_model": os.getenv("LLM_MODEL", "unknown"),
    }


# --- Serve frontend ---
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/search")
async def search_page():
    return FileResponse(FRONTEND_DIR / "search.html")


@app.get("/phenomenon/{pid}")
async def phenomenon_page(pid: str):
    return FileResponse(FRONTEND_DIR / "phenomenon.html")


@app.get("/about")
async def about_page():
    return FileResponse(FRONTEND_DIR / "about.html")


@app.get("/discoveries")
async def discoveries_page():
    return FileResponse(FRONTEND_DIR / "discoveries.html")


@app.get("/analyze")
async def analyze_page():
    return FileResponse(FRONTEND_DIR / "analyze.html")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    # API routes return JSON; only HTML pages get the full 404 template.
    path = request.url.path or ""
    if path.startswith("/api"):
        return JSONResponse({"detail": "not found"}, status_code=404)
    return FileResponse(FRONTEND_DIR / "404.html", status_code=404)
