"""X2 W1 (2026-05-24) — startup fail-fast on missing hybrid retrieval deps.

X2 root cause: `jieba` and `rank_bm25` were imported lazily inside
`services/search_service.py` with `except Exception: fallback`, masking a
real prod gap (neither was listed in `web/backend/requirements.txt`). The
2026-05-15 dogfood report q2 "团队相变恢复 → 形状记忆合金 相变恢复
score=1.0" was a direct consequence: jieba absent → both query and doc
tokenised to {相,变,恢,复} → BM25 字面 4-char hack.

This file ships the single startup assertion test required by X2 W1 spec:
verifies `jieba` is importable AND tokenization no longer degrades to
single-char split. The structural check on main.py's fail-fast block is
folded into the same test so a future stale deploy crashes loudly.

(Additional fine-grained tokenization assertions are intentionally NOT
added here — search_service tokenization is already covered by
test_search_service_v2v3.py and the dogfood corpus.)
"""
from __future__ import annotations

import sys
from pathlib import Path


_BACKEND = Path(__file__).resolve().parent.parent
_ROOT = _BACKEND.parent.parent
for p in (_BACKEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def test_jieba_installed_and_tokenization_works():
    """jieba + rank_bm25 declared in requirements.txt; tokenization no longer
    falls back to single-char (the dogfood q2 字面 hack root cause)."""
    ***REMOVED*** 1) Both deps importable (regression guard on requirements.txt drift)
    import jieba  ***REMOVED*** noqa: F401
    from rank_bm25 import BM25Okapi  ***REMOVED*** noqa: F401

    ***REMOVED*** 2) Service-level jieba handle is non-None
    from services.search_service import _tokenize, _JIEBA
    assert _JIEBA is not None, (
        "X2 W1: _JIEBA is None — hybrid BM25 will degrade to char-level. "
        "Check requirements.txt + venv install."
    )

    ***REMOVED*** 3) "相变恢复" must produce multi-char tokens, NOT 4 single chars
    toks = _tokenize("相变恢复")
    assert "相变" in toks or "恢复" in toks, (
        f"jieba broken: expected ['相变', '恢复'] presence, got {toks}"
    )
    assert sum(1 for t in toks if len(t) > 1) >= 1, (
        f"Tokenization degraded to single chars: {toks}"
    )

    ***REMOVED*** 4) main.py contains the fail-fast assert (structural check)
    main_src = (_BACKEND / "main.py").read_text(encoding="utf-8")
    assert "import jieba" in main_src and "import rank_bm25" in main_src, (
        "main.py is missing the jieba/rank_bm25 startup assert (X2 W1)"
    )
    assert "Hybrid retrieval requires" in main_src, (
        "main.py is missing the explicit fail-fast RuntimeError message"
    )
