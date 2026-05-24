"""
SearchService — 封装 StructuralSearch，支持自定义知识库路径。

v2 upgrades (2026-04-13):
- Hybrid BM25 + embedding retrieval (rank_bm25 + jieba tokenization)
- Optional StructTuple dynamics_family boost from V3 kb-expanded-struct.jsonl
- Domain collapse guard (MMR-lite): diversify top-5 when one domain dominates
"""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from structural_isomorphism.model import load_model, encode_texts

logger = logging.getLogger("structural.search_service")


***REMOVED*** --- Hybrid retrieval config -------------------------------------------------

***REMOVED*** Rule-based trigger phrases -> dynamics_family. Matched against the raw query.
***REMOVED*** When any trigger fires, phenomena from the corresponding family receive a
***REMOVED*** +BOOST_DYNAMICS bonus on their normalized fused score.
DYNAMICS_TRIGGERS: List[tuple] = [
    (("延迟", "滞后", "迟滞", "时滞", "delay", "lag"),
     ("DDE_delayed_feedback",)),
    (("阈值", "临界", "突变", "tipping", "threshold", "critical"),
     ("Phase_transition_1st", "Phase_transition_2nd", "Fold_bifurcation",
      "Hopf_bifurcation", "Saddle_node")),
    (("反馈", "循环", "自我强化", "失控", "feedback", "runaway", "positive loop"),
     ("positive_loop", "negative_loop")),
    (("崩盘", "级联", "雪崩", "瀑布", "cascade", "collapse", "avalanche"),
     ("Network_cascade", "Avalanche_dynamics")),
    (("共识", "演化", "博弈", "平衡", "consensus", "equilibrium"),
     ("Game_theoretic_equilibrium", "Evolutionary_dynamics")),
    (("传播", "扩散", "流言", "谣言", "diffusion", "spread"),
     ("Network_cascade", "Reaction_diffusion")),
    (("相变", "转变", "phase transition"),
     ("Phase_transition_1st", "Phase_transition_2nd")),
    (("振荡", "周期", "振动", "oscillation", "cycle"),
     ("Limit_cycle", "Hopf_bifurcation")),
]


***REMOVED*** Lightweight English stopwords (to dampen uninformative BM25 scores)
_EN_STOP = {"the", "a", "an", "of", "in", "on", "to", "for", "and", "or",
            "is", "are", "was", "were", "be", "been", "by", "with", "as",
            "at", "from", "this", "that", "it", "its", "into", "not"}
***REMOVED*** Chinese question words / fillers
_ZH_STOP = {"为什么", "怎么", "如何", "什么", "吗", "呢", "的", "了", "是",
            "有", "会", "在", "和", "与", "或", "以及", "为", "对", "给",
            "那么", "反而", "更", "一个", "一些", "一种"}


***REMOVED*** X2 W1 (2026-05-24) \u2014 eager jieba import. Previously imported lazily inside
***REMOVED*** _tokenize() with a bare `except Exception` fallback to char-level, which
***REMOVED*** silently masked a real prod gap (jieba not in requirements.txt). main.py
***REMOVED*** lifespan asserts jieba is importable; here we expose the module-level
***REMOVED*** `_JIEBA` handle so unit tests can introspect availability via
***REMOVED*** `search_service._JIEBA is not None`.
try:
    import jieba as _JIEBA
except ImportError:  ***REMOVED*** pragma: no cover \u2014 main.py lifespan asserts this
    _JIEBA = None


def _tokenize(text: str) -> List[str]:
    """Tokenize mixed CJK + English text for BM25.

    Uses jieba search-mode segmentation when available (the expected prod
    path \u2014 see main.py lifespan assert). Falls back to single-char split
    only in unit-test contexts where jieba was intentionally absent. The
    fallback path is preserved so individual service-level tests do not
    require the full requirements.txt to be installed.
    """
    if not text:
        return []
    if _JIEBA is not None:
        raw = list(_JIEBA.cut_for_search(text))
    else:
        raw = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text)
    toks: List[str] = []
    for t in raw:
        t = t.strip().lower()
        if not t or t in _EN_STOP or t in _ZH_STOP:
            continue
        if len(t) == 1 and not re.match(r"[\u4e00-\u9fff]", t):
            ***REMOVED*** drop single ASCII char / punctuation
            continue
        toks.append(t)
    return toks


***REMOVED*** X2 W3 (2026-05-24) — language detection for translate-before-embed.
***REMOVED*** Root cause: KB embedding model is `text2vec-base-chinese`, KB is 100%
***REMOVED*** Chinese. EN queries like "power-law distribution" had 0 BM25 字面 hits
***REMOVED*** AND embedding-similarity bias toward translated noise (LLM AB test:
***REMOVED*** DeepSeek mapped "self-organized criticality" to "分权改革俘获风险").
***REMOVED*** We detect EN-dominant queries up-front so the orchestrator can issue a
***REMOVED*** translation call before encoding.
try:
    from langdetect import detect_langs as _detect_langs  ***REMOVED*** type: ignore
    from langdetect import DetectorFactory as _DetectorFactory  ***REMOVED*** type: ignore
    ***REMOVED*** langdetect is non-deterministic by default; seed for reproducibility.
    _DetectorFactory.seed = 0
    _LANGDETECT_OK = True
except ImportError:  ***REMOVED*** pragma: no cover — falls back to ASCII heuristic
    _LANGDETECT_OK = False


def _detect_lang(query: str) -> str:
    """Return 'zh' | 'en' | 'mixed' for the query string.

    Priority order:
      1. ASCII-letter ratio > 0.7 AND no CJK chars → 'en'
      2. CJK present AND ASCII-letter ratio > 0.3 → 'mixed' (bilingual)
      3. CJK present, low ASCII → 'zh'
      4. No CJK, low ASCII (digits/punct only) → 'zh' (default to KB lang)

    The langdetect library is consulted as a tiebreaker for the ASCII-only
    cases (e.g. "phase transition" vs "1234"). The heuristic comes first
    because it's deterministic; langdetect is non-deterministic on short
    strings even with a seeded RNG.
    """
    if not query or not query.strip():
        return "zh"
    text = query.strip()
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total_meaningful = cjk + ascii_letters
    if total_meaningful == 0:
        return "zh"  ***REMOVED*** digits/punctuation only — default to KB lang
    ascii_ratio = ascii_letters / total_meaningful
    if cjk > 0 and ascii_ratio > 0.3:
        return "mixed"
    if cjk > 0:
        return "zh"
    if ascii_ratio > 0.7:
        return "en"
    return "zh"


def _infer_dynamics_families(query: str) -> List[str]:
    """Return the set of dynamics_family tags implied by the query."""
    q = query.lower()
    hits: List[str] = []
    for triggers, families in DYNAMICS_TRIGGERS:
        if any(t.lower() in q for t in triggers):
            hits.extend(families)
    ***REMOVED*** de-dup preserving order
    seen = set()
    out = []
    for f in hits:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _minmax(arr: np.ndarray) -> np.ndarray:
    """Min-max normalize to [0, 1]. Constant arrays map to 0."""
    if arr.size == 0:
        return arr
    lo = float(arr.min())
    hi = float(arr.max())
    if hi - lo < 1e-9:
        return np.zeros_like(arr, dtype=np.float32)
    return ((arr - lo) / (hi - lo)).astype(np.float32)


class SearchService:
    """
    封装跨领域结构同构搜索。
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        kb_file: str = "kb-expanded.jsonl",
        model_path: Optional[str] = None,
        precomputed_embeddings: Optional[str] = None,
        struct_file: Optional[str] = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else None
        self.kb_file = kb_file
        self.model = load_model(model_path=model_path)

        ***REMOVED*** Load KB
        self.kb: List[Dict] = []
        self.kb_by_id: Dict[str, Dict] = {}
        self.idx_by_id: Dict[str, int] = {}
        self._load_kb()

        ***REMOVED*** Per-instance query encode cache (replaced on reload)
        self._encode_query_cached = lru_cache(maxsize=1024)(self._encode_query_uncached)

        ***REMOVED*** Load precomputed or encode fresh embeddings
        self._embeddings = None
        if precomputed_embeddings:
            pre_path = Path(precomputed_embeddings)
            if pre_path.exists() and self.kb:
                try:
                    self._embeddings = np.load(pre_path)
                    if self._embeddings.shape[0] != len(self.kb):
                        logger.warning(
                            f"Precomputed embeddings size mismatch: "
                            f"{self._embeddings.shape[0]} vs kb {len(self.kb)}. Re-encoding."
                        )
                        self._embeddings = None
                    else:
                        logger.info(
                            f"Loaded precomputed embeddings from {pre_path} "
                            f"(shape: {self._embeddings.shape})"
                        )
                except Exception as e:
                    logger.error(f"Failed to load precomputed embeddings: {e}")
                    self._embeddings = None

        if self._embeddings is None and self.kb:
            logger.info(f"Encoding {len(self.kb)} phenomena...")
            descriptions = [item["description"] for item in self.kb]
            self._embeddings = encode_texts(self.model, descriptions, show_progress=True)
            logger.info(f"Embeddings shape: {self._embeddings.shape}")

        ***REMOVED*** Build BM25 index over name + description (name doubled for weighting)
        self._bm25 = None
        self._bm25_corpus_len = 0
        try:
            from rank_bm25 import BM25Okapi
            corpus_tokens = []
            for item in self.kb:
                text = f"{item.get('name','')} {item.get('name','')} {item.get('description','')}"
                corpus_tokens.append(_tokenize(text))
            if corpus_tokens:
                self._bm25 = BM25Okapi(corpus_tokens)
                self._bm25_corpus_len = len(corpus_tokens)
                logger.info(f"BM25 index built ({self._bm25_corpus_len} docs)")
        except Exception as e:
            logger.warning(f"BM25 init failed, falling back to embedding-only: {e}")
            self._bm25 = None

        ***REMOVED*** Load StructTuple index (phenomenon_id -> struct record)
        self._struct_by_id: Dict[str, Dict] = {}
        struct_path = None
        if struct_file:
            struct_path = Path(struct_file)
        elif self.data_dir:
            ***REMOVED*** default: v3/results/kb-expanded-struct.jsonl relative to project root
            candidate = self.data_dir.parent / "v3" / "results" / "kb-expanded-struct.jsonl"
            if candidate.exists():
                struct_path = candidate
        if struct_path and struct_path.exists():
            try:
                with open(struct_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            pid = rec.get("phenomenon_id")
                            if pid:
                                self._struct_by_id[pid] = rec
                        except json.JSONDecodeError:
                            continue
                logger.info(f"Loaded {len(self._struct_by_id)} StructTuple records from {struct_path}")
            except Exception as e:
                logger.warning(f"Failed to load StructTuple file: {e}")

    def _load_kb(self):
        if not self.data_dir:
            logger.warning("No data_dir configured")
            return
        kb_path = self.data_dir / self.kb_file
        if not kb_path.exists():
            logger.error(f"KB file not found: {kb_path}")
            return
        with open(kb_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                try:
                    item = json.loads(line)
                    idx = len(self.kb)
                    self.kb.append(item)
                    if "id" in item:
                        self.kb_by_id[item["id"]] = item
                        self.idx_by_id[item["id"]] = idx
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed line: {e}")
        logger.info(f"Loaded {len(self.kb)} phenomena from {kb_path}")

    ***REMOVED*** --- Query embedding cache -------------------------------------------------
    def _encode_query_uncached(self, query: str) -> np.ndarray:
        emb = encode_texts(self.model, query)
        return np.asarray(emb, dtype=np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        return self._encode_query_cached(query)

    def cache_stats(self) -> Dict[str, float]:
        """Query-embedding LRU cache stats — hits / misses / hit_rate.

        Session ***REMOVED***17 P2 — the encode cache had no observability. Surfaced
        via /api/health?deep=1 so operators can see whether the 1024-entry
        cache is actually paying off (hit_rate trending up = good).
        """
        info = self._encode_query_cached.cache_info()
        total = info.hits + info.misses
        return {
            "hits": info.hits,
            "misses": info.misses,
            "hit_rate": round(info.hits / total, 4) if total else 0.0,
            "size": info.currsize,
            "maxsize": info.maxsize or 0,
        }

    @property
    def kb_size(self) -> int:
        return len(self.kb)

    @property
    def domain_count(self) -> int:
        return len({item.get("domain", "") for item in self.kb if item.get("domain")})

    @property
    def type_count(self) -> int:
        return len({item.get("type_id", "") for item in self.kb if item.get("type_id")})

    ***REMOVED*** --- Unified similarity (Session ***REMOVED***17 V3) ---------------------------------

    @staticmethod
    def _cosine(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Plain cosine similarity, guaranteed in [-1, 1].

        The precomputed KB embedding files are NOT all L2-normalized
        (kb_v2_embeddings.npy has norms ~14-22). encode_query() *is*
        normalized (model.encode_texts default normalize=True). A raw
        np.dot of those two therefore returns illegal values (9.5 / 4.76
        observed in prod meta.similarity). We always divide by the actual
        norms here so the result is a true cosine regardless of whether
        the stored embeddings happen to be normalized.
        """
        a = np.asarray(vec_a, dtype=np.float64).flatten()
        b = np.asarray(vec_b, dtype=np.float64).flatten()
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na < 1e-12 or nb < 1e-12:
            return 0.0
        cos = float(np.dot(a, b) / (na * nb))
        ***REMOVED*** Clamp tiny FP overshoot so the value is provably in [-1, 1].
        return max(-1.0, min(1.0, cos))

    def relevance_score(self, query: str, phenomenon_id: str) -> float:
        """Unified [0, 1] relevance between a free-text query and a KB item.

        Session ***REMOVED***17 V3.2 — search and analyze used different similarity
        scales (search: min-max-normalized fused BM25+emb; analyze: raw
        np.dot). A result search ranked at 0.80 could be rejected by the
        analyze scope gate. This method is the SINGLE口径 both endpoints
        now share for the scope decision.

        Mapping: cosine ∈ [-1, 1] → relevance = (cosine + 1) / 2 ∈ [0, 1].
        This is a monotonic, bounded transform — a genuine cross-domain
        match (cosine ~0.3-0.6) lands at 0.65-0.80; pure noise (cosine ~0)
        lands at ~0.50; an antonym (cosine <0) lands below 0.50.

        Returns 0.0 if the phenomenon id is unknown / embeddings absent.
        """
        if self._embeddings is None:
            return 0.0
        idx = self.idx_by_id.get(phenomenon_id)
        if idx is None:
            return 0.0
        q_emb = self.encode_query(query)
        cos = self._cosine(q_emb, self._embeddings[idx])
        return round((cos + 1.0) / 2.0, 4)

    ***REMOVED*** --- Hybrid retrieval core -----------------------------------------------

    ***REMOVED*** Weight knobs. BM25 carries lexical match; embeddings carry semantic
    ***REMOVED*** structure. For short keyword queries BM25 dominates naturally; for long
    ***REMOVED*** NL queries embeddings keep control. 0.45/0.55 is the balanced default.
    BM25_WEIGHT = 0.45
    EMB_WEIGHT = 0.55
    BOOST_DYNAMICS = 0.10  ***REMOVED*** added to fused score for matching dynamics_family
    DOMAIN_CAP_IN_TOP5 = 2  ***REMOVED*** diversity guard threshold

    def _fused_scores(self, query: str) -> np.ndarray:
        """Return a (N,) array of fused scores aligned with self.kb."""
        n = len(self.kb)
        if n == 0 or self._embeddings is None:
            return np.zeros(0, dtype=np.float32)

        ***REMOVED*** --- Embedding similarity ---
        q_emb = self.encode_query(query)
        emb_sims = np.dot(self._embeddings, q_emb.T).flatten().astype(np.float32)
        emb_norm = _minmax(emb_sims)

        ***REMOVED*** --- BM25 ---
        if self._bm25 is not None:
            q_tokens = _tokenize(query)
            if q_tokens:
                bm25_raw = np.asarray(self._bm25.get_scores(q_tokens), dtype=np.float32)
                bm25_norm = _minmax(bm25_raw)
            else:
                bm25_norm = np.zeros(n, dtype=np.float32)
        else:
            bm25_norm = np.zeros(n, dtype=np.float32)

        fused = self.BM25_WEIGHT * bm25_norm + self.EMB_WEIGHT * emb_norm

        ***REMOVED*** --- StructTuple dynamics_family boost ---
        families = _infer_dynamics_families(query)
        if families and self._struct_by_id:
            fam_set = set(families)
            for idx, item in enumerate(self.kb):
                pid = item.get("id")
                if not pid:
                    continue
                rec = self._struct_by_id.get(pid)
                if not rec:
                    continue
                df = rec.get("dynamics_family")
                ft = rec.get("feedback_topology")
                if (df and df in fam_set) or (ft and ft in fam_set):
                    fused[idx] += self.BOOST_DYNAMICS

        return fused

    def _domain_guard(self, ranked_idx: List[int], top_k: int) -> List[int]:
        """Cap per-domain hits in the top_k window (MMR-lite).

        Walk through ranked_idx and keep the first top_k indices, but allow at
        most DOMAIN_CAP_IN_TOP5 results from any single domain within the top 5.
        Surplus indices are pushed to the tail in original order.
        """
        if top_k <= 1 or not ranked_idx:
            return ranked_idx[:top_k]
        head: List[int] = []
        tail: List[int] = []
        domain_count: Dict[str, int] = {}
        cap_window = min(5, top_k)
        for idx in ranked_idx:
            item = self.kb[idx]
            dom = item.get("domain", "") or "_unknown"
            used = domain_count.get(dom, 0)
            ***REMOVED*** Only enforce cap while filling the first cap_window slots.
            if len(head) < cap_window and used >= self.DOMAIN_CAP_IN_TOP5:
                tail.append(idx)
                continue
            head.append(idx)
            domain_count[dom] = used + 1
            if len(head) >= top_k:
                break
        if len(head) < top_k:
            for idx in tail:
                if idx not in head:
                    head.append(idx)
                if len(head) >= top_k:
                    break
        return head[:top_k]

    ***REMOVED*** --- Cross-domain detection (Session ***REMOVED***17 V2) -----------------------------

    ***REMOVED*** When the surface domain owns more than this fraction of a result's
    ***REMOVED*** candidate pool, that domain is treated as "the obvious one" and its
    ***REMOVED*** members are flagged same_domain so the frontend can de-emphasise them.
    CROSS_DOMAIN_POOL_FRACTION = 0.30

    def _infer_surface_domain(self, fused: np.ndarray) -> Optional[str]:
        """Best-effort guess of the query's own surface domain.

        We do NOT have the query's domain label — the user typed free text.
        Heuristic: the surface domain is the domain that dominates the very
        top of the lexical+semantic ranking. We take the top-8 fused hits
        and return the modal domain *if* it owns >= 3 of those 8 slots
        (a clear lexical-overlap cluster, e.g. a 留存 query pulling many
        组织管理 phenomena). Otherwise we return None — the query has no
        single obvious home domain, so nothing should be flagged same-domain.
        """
        if fused.size == 0:
            return None
        top = np.argsort(fused)[::-1][:8].tolist()
        counts: Dict[str, int] = {}
        for idx in top:
            dom = self.kb[int(idx)].get("domain", "") or ""
            if dom:
                counts[dom] = counts.get(dom, 0) + 1
        if not counts:
            return None
        modal_dom, modal_n = max(counts.items(), key=lambda kv: kv[1])
        return modal_dom if modal_n >= 3 else None

    def search(
        self,
        query: str,
        top_k: int = 12,
        min_score: float = 0.05,
    ) -> List[Dict]:
        """Search for structurally similar phenomena via hybrid BM25+embedding.

        Session ***REMOVED***17 V2 — each result additionally carries:
          * relevance     — unified [0,1] cosine口径 (same as analyze scope gate)
          * cross_domain  — bool, True if the result's domain differs from the
                            query's inferred surface domain
          * surface_domain— the inferred surface domain (echoed on every result;
                            None when no single domain dominates the pool)
        """
        if self._embeddings is None or not query.strip():
            return []

        fused = self._fused_scores(query)
        if fused.size == 0:
            return []

        surface_domain = self._infer_surface_domain(fused)
        ***REMOVED*** Query embedding is already in the lru cache (encoded inside
        ***REMOVED*** _fused_scores), so this re-fetch is free — used for per-result
        ***REMOVED*** unified relevance.
        q_emb = self.encode_query(query)

        ***REMOVED*** Take a larger candidate pool, then diversity-rank down to top_k.
        pool_size = min(len(self.kb), max(top_k * 4, 40))
        top_pool = np.argsort(fused)[::-1][:pool_size].tolist()
        ranked = self._domain_guard(top_pool, top_k)

        results = []
        for idx in ranked:
            score = float(fused[idx])
            if score < min_score:
                continue
            item = self.kb[int(idx)]
            dom = item.get("domain", "")
            ***REMOVED*** Return fused score directly in [0, 1.1]. Frontend is
            ***REMOVED*** responsible for mapping this to a visual tier (strong/medium/weak)
            ***REMOVED*** or a capped percentage (min(score, 1.0) * 100).
            display_score = round(min(score, 1.0), 4)
            ***REMOVED*** V3 — unified relevance口径 (same transform as relevance_score()),
            ***REMOVED*** so a value search shows here can be re-derived by the analyze
            ***REMOVED*** scope gate without disagreement.
            cos = self._cosine(q_emb, self._embeddings[int(idx)])
            relevance = round((cos + 1.0) / 2.0, 4)
            ***REMOVED*** V2 — cross_domain flag. When no surface domain dominates the
            ***REMOVED*** pool (surface_domain is None) we cannot judge, so default to
            ***REMOVED*** True (do not penalise — absence of evidence ≠ same-domain).
            cross_domain = (
                True if surface_domain is None else (dom != surface_domain)
            )
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "domain": dom,
                "type_id": item.get("type_id", ""),
                "description": item.get("description", ""),
                "score": display_score,
                "relevance": relevance,
                "cross_domain": cross_domain,
                "surface_domain": surface_domain,
            })
            if len(results) >= top_k:
                break
        return results

    def get_by_id(self, phenomenon_id: str) -> Optional[Dict]:
        return self.kb_by_id.get(phenomenon_id)

    def get_similar(self, phenomenon_id: str, top_k: int = 8) -> List[Dict]:
        """Given a phenomenon id, return structurally similar phenomena."""
        if phenomenon_id not in self.kb_by_id or self._embeddings is None:
            return []
        idx = self.idx_by_id.get(phenomenon_id)
        if idx is None:
            return []
        sims = np.dot(self._embeddings, self._embeddings[idx].T).flatten()
        sims[idx] = -1.0
        top_indices = np.argsort(sims)[::-1][:top_k]
        results = []
        for i in top_indices:
            score = float(sims[int(i)])
            if score < 0.3:
                break
            item = self.kb[int(i)]
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "domain": item.get("domain", ""),
                "type_id": item.get("type_id", ""),
                "description": item.get("description", ""),
                "score": round(score, 4),
            })
        return results

    def get_same_structure(self, type_id: str, exclude_id: str = "", limit: int = 6) -> List[Dict]:
        """Return other phenomena sharing the same structure type."""
        results = []
        for item in self.kb:
            if item.get("type_id") == type_id and item.get("id") != exclude_id:
                results.append({
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "domain": item.get("domain", ""),
                    "type_id": item.get("type_id", ""),
                    "description": item.get("description", ""),
                })
                if len(results) >= limit:
                    break
        return results
