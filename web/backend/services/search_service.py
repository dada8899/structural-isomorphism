"""
SearchService — 封装 StructuralSearch，支持自定义知识库路径。
"""
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from structural_isomorphism.model import load_model, encode_texts

logger = logging.getLogger("structural.search_service")


class SearchService:
    """
    封装跨领域结构同构搜索。

    与 structural_isomorphism.StructuralSearch 的区别：
    - 支持直接指定单个 kb 文件（4475 条版本）
    - 预加载嵌入，提供 O(1) id 查找
    - 按 id 查找、按 type 查找等产品需要的方法
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        kb_file: str = "kb-expanded.jsonl",
        model_path: Optional[str] = None,
        precomputed_embeddings: Optional[str] = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else None
        self.kb_file = kb_file
        self.model = load_model(model_path=model_path)

        # Load KB
        self.kb: List[Dict] = []
        self.kb_by_id: Dict[str, Dict] = {}
        # id -> list index, built at load time so mapping / analyze endpoints
        # can skip O(N) scans on every request.
        self.idx_by_id: Dict[str, int] = {}
        self._load_kb()

        # Bind the instance method to the query embedding cache. We use a
        # per-instance lru_cache (attached in __init__) so that replacing the
        # service (during reload) doesn't retain stale embeddings.
        self._encode_query_cached = lru_cache(maxsize=1024)(self._encode_query_uncached)

        # Try precomputed embeddings first (saves ~10 min on CPU-only machines)
        self._embeddings = None
        if precomputed_embeddings:
            pre_path = Path(precomputed_embeddings)
            if pre_path.exists() and self.kb:
                try:
                    self._embeddings = np.load(pre_path)
                    if self._embeddings.shape[0] != len(self.kb):
                        logger.warning(
                            f"Precomputed embeddings size mismatch: "
                            f"{self._embeddings.shape[0]} vs kb {len(self.kb)}. "
                            f"Will re-encode."
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

        # Encode KB if no precomputed embeddings
        if self._embeddings is None and self.kb:
            logger.info(f"Encoding {len(self.kb)} phenomena (this may take a while)...")
            descriptions = [item["description"] for item in self.kb]
            self._embeddings = encode_texts(self.model, descriptions, show_progress=True)
            logger.info(f"Embeddings shape: {self._embeddings.shape}")

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
    # encode_texts does a forward pass through the sentence-transformer model;
    # on CPU this is ~200-400ms. Caching by raw query string removes that cost
    # for repeated searches (e.g. examples endpoint + common user questions).
    def _encode_query_uncached(self, query: str) -> np.ndarray:
        emb = encode_texts(self.model, query)
        return np.asarray(emb, dtype=np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        """Cached single-query encode. Returns a 1-d or 2-d numpy array."""
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

    def search(
        self,
        query: str,
        top_k: int = 12,
        min_score: float = 0.4,
    ) -> List[Dict]:
        """Search for structurally similar phenomena."""
        if self._embeddings is None or not query.strip():
            return []

        query_emb = self.encode_query(query)
        similarities = np.dot(self._embeddings, query_emb.T).flatten()
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < min_score:
                break
            item = self.kb[int(idx)]
            results.append({
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "domain": item.get("domain", ""),
                "type_id": item.get("type_id", ""),
                "description": item.get("description", ""),
                "score": round(score, 4),
            })
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
        # Exclude self
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
