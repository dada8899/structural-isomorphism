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


# --- Hybrid retrieval config -------------------------------------------------

# Rule-based trigger phrases -> dynamics_family. Matched against the raw query.
# When any trigger fires, phenomena from the corresponding family receive a
# +BOOST_DYNAMICS bonus on their normalized fused score.
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


# Lightweight English stopwords (to dampen uninformative BM25 scores)
_EN_STOP = {"the", "a", "an", "of", "in", "on", "to", "for", "and", "or",
            "is", "are", "was", "were", "be", "been", "by", "with", "as",
            "at", "from", "this", "that", "it", "its", "into", "not"}
# Chinese question words / fillers
_ZH_STOP = {"为什么", "怎么", "如何", "什么", "吗", "呢", "的", "了", "是",
            "有", "会", "在", "和", "与", "或", "以及", "为", "对", "给",
            "那么", "反而", "更", "一个", "一些", "一种"}


def _tokenize(text: str) -> List[str]:
    """Tokenize mixed CJK + English text for BM25."""
    if not text:
        return []
    # Try jieba for Chinese; fall back to char-level if unavailable.
    try:
        import jieba
        raw = list(jieba.cut_for_search(text))
    except Exception:
        raw = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text)
    toks: List[str] = []
    for t in raw:
        t = t.strip().lower()
        if not t or t in _EN_STOP or t in _ZH_STOP:
            continue
        if len(t) == 1 and not re.match(r"[\u4e00-\u9fff]", t):
            # drop single ASCII char / punctuation
            continue
        toks.append(t)
    return toks


def _infer_dynamics_families(query: str) -> List[str]:
    """Return the set of dynamics_family tags implied by the query."""
    q = query.lower()
    hits: List[str] = []
    for triggers, families in DYNAMICS_TRIGGERS:
        if any(t.lower() in q for t in triggers):
            hits.extend(families)
    # de-dup preserving order
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

        # Load KB
        self.kb: List[Dict] = []
        self.kb_by_id: Dict[str, Dict] = {}
        self.idx_by_id: Dict[str, int] = {}
        self._load_kb()

        # Per-instance query encode cache (replaced on reload)
        self._encode_query_cached = lru_cache(maxsize=1024)(self._encode_query_uncached)

        # Load precomputed or encode fresh embeddings
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

        # Build BM25 index over name + description (name doubled for weighting)
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

        # Load StructTuple index (phenomenon_id -> struct record)
        self._struct_by_id: Dict[str, Dict] = {}
        struct_path = None
        if struct_file:
            struct_path = Path(struct_file)
        elif self.data_dir:
            # default: v3/results/kb-expanded-struct.jsonl relative to project root
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

    # --- Query embedding cache -------------------------------------------------
    def _encode_query_uncached(self, query: str) -> np.ndarray:
        emb = encode_texts(self.model, query)
        return np.asarray(emb, dtype=np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        return self._encode_query_cached(query)

    @property
    def kb_size(self) -> int:
        return len(self.kb)

    @property
    def domain_count(self) -> int:
        return len({item.get("domain", "") for item in self.kb if item.get("domain")})

    @property
    def type_count(self) -> int:
        return len({item.get("type_id", "") for item in self.kb if item.get("type_id")})

    # --- Hybrid retrieval core -----------------------------------------------

    # Weight knobs. BM25 carries lexical match; embeddings carry semantic
    # structure. For short keyword queries BM25 dominates naturally; for long
    # NL queries embeddings keep control. 0.45/0.55 is the balanced default.
    BM25_WEIGHT = 0.45
    EMB_WEIGHT = 0.55
    BOOST_DYNAMICS = 0.10  # added to fused score for matching dynamics_family
    DOMAIN_CAP_IN_TOP5 = 2  # diversity guard threshold

    def _fused_scores(self, query: str) -> np.ndarray:
        """Return a (N,) array of fused scores aligned with self.kb."""
        n = len(self.kb)
        if n == 0 or self._embeddings is None:
            return np.zeros(0, dtype=np.float32)

        # --- Embedding similarity ---
        q_emb = self.encode_query(query)
        emb_sims = np.dot(self._embeddings, q_emb.T).flatten().astype(np.float32)
        emb_norm = _minmax(emb_sims)

        # --- BM25 ---
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

        # --- StructTuple dynamics_family boost ---
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
            # Only enforce cap while filling the first cap_window slots.
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

    def search(
        self,
        query: str,
        top_k: int = 12,
        min_score: float = 0.05,
    ) -> List[Dict]:
        """Search for structurally similar phenomena via hybrid BM25+embedding."""
        if self._embeddings is None or not query.strip():
            return []

        fused = self._fused_scores(query)
        if fused.size == 0:
            return []

        # Take a larger candidate pool, then diversity-rank down to top_k.
        pool_size = min(len(self.kb), max(top_k * 4, 40))
        top_pool = np.argsort(fused)[::-1][:pool_size].tolist()
        ranked = self._domain_guard(top_pool, top_k)

        results = []
        for idx in ranked:
            score = float(fused[idx])
            if score < min_score:
                continue
            item = self.kb[int(idx)]
            # Scale displayed score to legacy ~[5, 20] band so frontend bars
            # keep their visual proportions. Fused is in [0, ~1.15].
            display_score = round(10.0 * score + 6.0, 4)
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "domain": item.get("domain", ""),
                "type_id": item.get("type_id", ""),
                "description": item.get("description", ""),
                "score": display_score,
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
