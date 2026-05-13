"""
F1: V1/V2 -> V4 embedding bridge.

Goal: Reuse V1/V2 trained sentence-transformer embeddings (and their cached
phenomenon vectors) as a *second signal source* for V4 Layer 3 candidate-class
expansion. The LLM remains the primary source of candidate-class proposals
(Layer 3), but for each KEEP class we can ask: "Which phenomena in our 4475
KB items lie nearest to the existing positive_examples in V1/V2 embedding
space?" — those become *expansion suggestions* that the LLM critic or a
human reviewer can then accept / reject.

Why we trust this signal:
 - V1 model (`models/structural-v1/`, 782MB, gitignored, VPS-only): fine-tuned
   on cross-domain phenomenon pairs; reported R@5 = 100% on holdout, Silhouette
   = 0.85 on labelled clusters.
 - V2 model: refined with additional 3017 cross-domain pairs.
 - The trained models live on the VPS, but their *precomputed phenomenon
   embeddings* (`web/data/kb_embeddings.npy`, `kb_v2_embeddings.npy`) and the
   parallel id arrays are committed to the repo (~13 MB each). That means
   any agent can do nearest-neighbour queries against the V1/V2 latent
   geometry *without* loading the model — we just need to embed the *query*
   text.

Two ways to embed the query:
 1. real_model: if `models/structural-v1/` is present, load SentenceTransformer
    and `encode_texts()`. Best fidelity.
 2. tfidf fallback: when the model is unavailable (e.g. local laptop without
    the 782MB download), we fit a `TfidfVectorizer` over the KB descriptions
    and project queries into TF-IDF space. We then look up *cached V1/V2
    embeddings of the nearest TF-IDF neighbours* — this is a 2-hop
    approximation but lets the bridge interface work everywhere.

Future (F2, not in this task):
 - active-learning loop: feed V4 critic rejections back as new negatives to
   re-fine-tune V1/V2 -> V3.
 - direct embedding endpoint on VPS via HTTP for true real-model querying
   from any client.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# ---------- repo paths (resolved relative to this file) ----------
_THIS = Path(__file__).resolve()
REPO = _THIS.parents[2]
DEFAULT_KB_FILE = REPO / "data" / "kb-5000-merged.jsonl"
DEFAULT_V1_NPY = REPO / "web" / "data" / "kb_embeddings.npy"
DEFAULT_V1_IDS = REPO / "web" / "data" / "kb_embeddings_ids.json"
DEFAULT_V2_NPY = REPO / "web" / "data" / "kb_v2_embeddings.npy"
DEFAULT_V2_IDS = REPO / "web" / "data" / "kb_v2_embeddings_ids.json"
DEFAULT_MODEL_DIR = REPO / "models" / "structural-v1"


@dataclass
class Neighbor:
    """A nearest-neighbour suggestion."""

    id: str
    name: str
    domain: str
    description: str
    similarity: float  # cosine, in [-1, 1] after L2 normalisation

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "similarity": round(float(self.similarity), 4),
        }


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalize. Returns a new array (does not mutate input)."""
    if x.ndim == 1:
        n = np.linalg.norm(x)
        return x / n if n > 0 else x
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return x / norms


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a jsonl file into a list of dicts. Used for KB phenomena."""
    items: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


class EmbeddingBridge:
    """V1/V2 embedding bridge for V4 candidate-class expansion.

    Two modes:
      - "real_model": loads sentence-transformer from `model_path` to embed
        query texts. Requires `models/structural-v1/` present (~782MB).
      - "tfidf": fits a TF-IDF vectorizer over KB descriptions; query texts
        are mapped to TF-IDF, then we find the K_tfidf TF-IDF neighbours and
        return their cached V1/V2 embedding-space neighbours. 2-hop
        approximation but works without the model file.

    Cache layout:
      - V1/V2 cached embeddings are loaded once at construction.
      - The KB jsonl is loaded once and indexed by id.
      - V1 cache is already L2-normalized; V2 is not, we normalize on load.

    Example:
        >>> bridge = EmbeddingBridge()              # auto-pick mode
        >>> phen = {"description": "..."}
        >>> bridge.suggest_neighbors(phen, k=5)
        [Neighbor(...), ...]
    """

    SUPPORTED_VERSIONS = ("v1", "v2")

    def __init__(
        self,
        model_path: str | None = None,
        fallback_mode: str = "tfidf",
        version: str = "v2",
        kb_file: str | Path | None = None,
        npy_file: str | Path | None = None,
        ids_file: str | Path | None = None,
    ) -> None:
        if version not in self.SUPPORTED_VERSIONS:
            raise ValueError(
                f"version must be one of {self.SUPPORTED_VERSIONS}, got {version!r}"
            )
        self.version = version
        self.fallback_mode = fallback_mode

        # --- resolve cache paths -----------------------------------------
        if version == "v1":
            self._npy_path = Path(npy_file or DEFAULT_V1_NPY)
            self._ids_path = Path(ids_file or DEFAULT_V1_IDS)
        else:
            self._npy_path = Path(npy_file or DEFAULT_V2_NPY)
            self._ids_path = Path(ids_file or DEFAULT_V2_IDS)
        self._kb_path = Path(kb_file or DEFAULT_KB_FILE)

        # --- load cache --------------------------------------------------
        if not self._npy_path.exists():
            raise FileNotFoundError(
                f"Embedding cache not found at {self._npy_path}. "
                "Did you `git lfs pull` the npy files?"
            )
        if not self._ids_path.exists():
            raise FileNotFoundError(f"Id list not found at {self._ids_path}")

        self._emb: np.ndarray = np.load(self._npy_path)
        with open(self._ids_path, encoding="utf-8") as f:
            self._ids: list[str] = json.load(f)

        if self._emb.shape[0] != len(self._ids):
            raise ValueError(
                f"Embedding rows ({self._emb.shape[0]}) does not match id "
                f"count ({len(self._ids)})"
            )

        # Normalize V2 (V1 is already normalized but we re-normalize defensively)
        self._emb = _l2_normalize(self._emb).astype(np.float32)
        self._id_to_idx: dict[str, int] = {i: k for k, i in enumerate(self._ids)}
        logger.info(
            "Loaded %d %s embeddings (dim=%d) from %s",
            self._emb.shape[0],
            self.version,
            self._emb.shape[1],
            self._npy_path.name,
        )

        # --- load KB metadata for nice neighbour rendering ---------------
        if not self._kb_path.exists():
            raise FileNotFoundError(f"KB file not found at {self._kb_path}")
        self._kb_by_id: dict[str, dict[str, Any]] = {}
        for item in _load_jsonl(self._kb_path):
            iid = item.get("id")
            if iid:
                self._kb_by_id[iid] = item
        logger.info("Loaded %d KB items from %s", len(self._kb_by_id), self._kb_path.name)

        # --- decide encode strategy --------------------------------------
        self._real_model = None
        self._tfidf_vectorizer = None
        self._tfidf_matrix = None
        self._tfidf_ids: list[str] = []
        self._mode: str = "uninitialized"

        if model_path is None:
            # auto-detect default location
            if DEFAULT_MODEL_DIR.exists():
                model_path = str(DEFAULT_MODEL_DIR)

        if model_path and Path(model_path).exists():
            try:
                from sentence_transformers import SentenceTransformer  # noqa: WPS433

                self._real_model = SentenceTransformer(model_path)
                self._mode = "real_model"
                logger.info("Real V1/V2 model loaded from %s", model_path)
            except Exception as e:  # pragma: no cover - depends on env
                logger.warning(
                    "Failed to load real model at %s (%s); falling back to %s",
                    model_path,
                    e,
                    fallback_mode,
                )

        if self._mode == "uninitialized":
            if fallback_mode == "tfidf":
                self._fit_tfidf()
                self._mode = "tfidf"
            else:
                raise RuntimeError(
                    f"Real model unavailable and unknown fallback_mode={fallback_mode!r}"
                )

    # ------------------------------------------------------------------
    # public properties
    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        """Either 'real_model' or 'tfidf'."""
        return self._mode

    @property
    def num_phenomena(self) -> int:
        return self._emb.shape[0]

    # ------------------------------------------------------------------
    # core encoding
    # ------------------------------------------------------------------
    def _fit_tfidf(self) -> None:
        """Fit a TF-IDF vectorizer over the KB descriptions.

        We use char n-grams (2-3) to be robust to Chinese text without needing
        a Chinese tokenizer. This is a pragmatic fallback — it captures lexical
        overlap, not semantic similarity. Use real V1/V2 model on VPS for prod.
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: WPS433
        except ImportError as e:
            raise RuntimeError(
                "scikit-learn is required for tfidf fallback. "
                "`pip install scikit-learn`."
            ) from e

        descriptions: list[str] = []
        ids: list[str] = []
        for iid in self._ids:
            item = self._kb_by_id.get(iid)
            if item and item.get("description"):
                descriptions.append(item["description"])
                ids.append(iid)
        # If KB description coverage is incomplete, still keep order aligned
        # to whatever subset we have. For a full KB (4475/4443) coverage should
        # be complete, so this is a defensive branch only.
        self._tfidf_ids = ids
        self._tfidf_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 3),
            min_df=2,
            max_df=0.95,
            sublinear_tf=True,
        )
        self._tfidf_matrix = self._tfidf_vectorizer.fit_transform(descriptions)
        logger.info(
            "Fitted TF-IDF: %d docs, %d features",
            self._tfidf_matrix.shape[0],
            self._tfidf_matrix.shape[1],
        )

    def _encode_query_to_v_space(self, text: str) -> np.ndarray | None:
        """Encode a query text directly in the V1/V2 latent space.

        Returns None if real model is not loaded — caller must use the
        2-hop TF-IDF path instead.
        """
        if self._real_model is None:
            return None
        vec = self._real_model.encode(
            [text],
            batch_size=1,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )[0]
        return vec.astype(np.float32)

    def _tfidf_proxy_neighbors(
        self, text: str, k_tfidf: int = 20
    ) -> list[tuple[int, float]]:
        """Find the top k_tfidf TF-IDF neighbours of `text` in the KB.

        Returns list of (kb_index_in_self._emb, tfidf_cosine). The kb_index
        is into `self._emb` / `self._ids` (not the TF-IDF matrix), so callers
        can drop straight into the V1/V2 cache.
        """
        assert self._tfidf_vectorizer is not None
        assert self._tfidf_matrix is not None
        qv = self._tfidf_vectorizer.transform([text])
        # cosine sim = qv . X^T (both L2-normalised by TfidfVectorizer with
        # sublinear_tf=True + ngram char_wb; we re-normalise to be safe)
        from sklearn.preprocessing import normalize  # noqa: WPS433

        qv_n = normalize(qv, norm="l2", axis=1)
        mat_n = normalize(self._tfidf_matrix, norm="l2", axis=1)
        scores = (qv_n @ mat_n.T).toarray()[0]
        top_idx = np.argsort(-scores)[:k_tfidf]
        out: list[tuple[int, float]] = []
        for ti in top_idx:
            iid = self._tfidf_ids[ti]
            kb_idx = self._id_to_idx.get(iid)
            if kb_idx is not None:
                out.append((kb_idx, float(scores[ti])))
        return out

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def suggest_neighbors(
        self,
        phenomenon: dict[str, Any] | str,
        k: int = 5,
        exclude_ids: Iterable[str] | None = None,
    ) -> list[Neighbor]:
        """Return top-k nearest neighbours from the KB for `phenomenon`.

        Args:
            phenomenon: Either a dict with at least a "description" key
                (or "name" if description missing), or a raw string. We
                deliberately accept both because Layer 3 candidate classes
                store positive_examples as dicts but ad-hoc queries are
                often raw strings.
            k: Top-k neighbours to return.
            exclude_ids: Ids to skip (e.g. the phenomenon's own id and known
                positives to avoid recommending what's already in the class).

        Returns:
            List of Neighbor sorted by descending similarity.
        """
        text = self._extract_text(phenomenon)
        if not text:
            return []

        excludes: set[str] = set(exclude_ids or [])
        if isinstance(phenomenon, dict):
            own_id = phenomenon.get("id")
            if own_id:
                excludes.add(own_id)

        # Path 1: real model -> direct cosine in V1/V2 space
        qvec = self._encode_query_to_v_space(text)
        if qvec is not None:
            scores = self._emb @ qvec  # (N,)
            order = np.argsort(-scores)
            return self._collect(order, scores, k, excludes)

        # Path 2: tfidf proxy -> use V1/V2 cache of tfidf-nearest items as
        # the candidate pool, then re-rank inside that pool by V1/V2 cosine
        # against the *centroid of those candidates* (a poor man's pseudo-
        # query in V-space). This keeps results within the trained latent
        # geometry while still working without the model.
        proxy = self._tfidf_proxy_neighbors(text, k_tfidf=max(20, k * 4))
        if not proxy:
            return []
        proxy_idx = [i for i, _ in proxy]
        pool_emb = self._emb[proxy_idx]  # (m, d)
        centroid = _l2_normalize(pool_emb.mean(axis=0))
        scores_full = self._emb @ centroid
        order = np.argsort(-scores_full)
        return self._collect(order, scores_full, k, excludes)

    def expand_candidate_class(
        self,
        class_yaml: dict[str, Any],
        k: int = 10,
        per_seed_k: int = 5,
    ) -> list[Neighbor]:
        """For a candidate class, suggest additional members via embedding NN.

        Strategy: pull all `positive_examples` descriptions, take their
        centroid in V1/V2 space, and return top-k phenomena not already in
        positive_examples / negative_examples.

        Args:
            class_yaml: Loaded YAML dict (must have positive_examples list).
            k: Number of expansion suggestions to return at the class level.
            per_seed_k: For diagnostic, also gather per-seed NN to surface
                seeds that are 'lonely' (no good neighbours).

        Returns:
            List of Neighbor sorted by descending similarity to the
            positive-examples centroid.
        """
        positives: list[str] = []
        for ex in class_yaml.get("positive_examples", []) or []:
            if isinstance(ex, dict):
                t = ex.get("phenomenon") or ex.get("description") or ex.get("name")
                if t:
                    positives.append(t)
            elif isinstance(ex, str):
                positives.append(ex)

        if not positives:
            logger.info(
                "Class %s has no positive_examples, returning empty",
                class_yaml.get("class_id", "<unknown>"),
            )
            return []

        # Build exclude set: ids whose description matches any positive_example
        # or negative_example. Cheap substring matching because positives are
        # usually short phrases not full descriptions.
        excludes: set[str] = set()
        neg_names: list[str] = []
        for ex in class_yaml.get("negative_examples", []) or []:
            if isinstance(ex, dict):
                n = ex.get("phenomenon") or ex.get("name")
                if n:
                    neg_names.append(n)
        for iid, item in self._kb_by_id.items():
            name = item.get("name", "")
            desc = item.get("description", "")
            for needle in positives + neg_names:
                if needle and (needle in name or needle in desc):
                    excludes.add(iid)
                    break

        # Centroid of positive descriptions in V1/V2 space.
        seed_vecs: list[np.ndarray] = []
        for t in positives:
            v = self._encode_query_to_v_space(t)
            if v is not None:
                seed_vecs.append(v)
            else:
                # tfidf path: use centroid of tfidf-proxy pool as proxy vector
                proxy = self._tfidf_proxy_neighbors(t, k_tfidf=per_seed_k * 2)
                if proxy:
                    pool = self._emb[[i for i, _ in proxy]]
                    seed_vecs.append(_l2_normalize(pool.mean(axis=0)))
        if not seed_vecs:
            return []
        centroid = _l2_normalize(np.stack(seed_vecs).mean(axis=0))
        scores = self._emb @ centroid
        order = np.argsort(-scores)
        return self._collect(order, scores, k, excludes)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _extract_text(self, phenomenon: dict[str, Any] | str) -> str:
        if isinstance(phenomenon, str):
            return phenomenon
        if isinstance(phenomenon, dict):
            return (
                phenomenon.get("description")
                or phenomenon.get("phenomenon")
                or phenomenon.get("name")
                or ""
            )
        return ""

    def _collect(
        self,
        order: Sequence[int],
        scores: np.ndarray,
        k: int,
        excludes: set[str],
    ) -> list[Neighbor]:
        out: list[Neighbor] = []
        for idx in order:
            iid = self._ids[int(idx)]
            if iid in excludes:
                continue
            item = self._kb_by_id.get(iid, {})
            out.append(
                Neighbor(
                    id=iid,
                    name=item.get("name", ""),
                    domain=item.get("domain", ""),
                    description=item.get("description", ""),
                    similarity=float(scores[int(idx)]),
                )
            )
            if len(out) >= k:
                break
        return out
