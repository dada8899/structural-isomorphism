"""
StructuralSearch: main search interface for structural isomorphism retrieval.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np

from structural_isomorphism.model import load_model, encode_texts
from structural_isomorphism.data import load_knowledge_base

logger = logging.getLogger(__name__)


class StructuralSearch:
    """
    Search engine for cross-domain structural similarity.

    Given a natural language description of a phenomenon, retrieves
    structurally similar phenomena from a knowledge base spanning
    diverse domains.

    Example:
        >>> search = StructuralSearch()
        >>> results = search.query("A thermostat keeps room temperature stable")
        >>> for r in results[:3]:
        ...     print(f"{r['name']} ({r['domain']}) - {r['score']:.3f}")
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        data_dir: Optional[str] = None,
        device: Optional[str] = None,
    ):
        """
        Initialize the search engine.

        Args:
            model_path: Path to the fine-tuned model or HuggingFace model ID.
                If None, tries local model, then HuggingFace, then base model.
            data_dir: Directory containing kb-*.jsonl knowledge base files.
                If None, uses the default data/ directory.
            device: Device for model inference ('cpu', 'cuda', 'mps').
                Auto-detected if None.
        """
        logger.info("Initializing StructuralSearch...")

        # Load model
        self.model = load_model(model_path=model_path, device=device)

        # Load knowledge base
        self.kb = load_knowledge_base(data_dir=data_dir)
        if not self.kb:
            logger.warning(
                "Knowledge base is empty. Search will return no results. "
                "Make sure kb-*.jsonl files exist in the data/ directory. "
                "You can download them from: "
                "https://huggingface.co/datasets/structural-isomorphism/SIBD"
            )
            self._kb_embeddings = None
        else:
            # Pre-compute knowledge base embeddings
            descriptions = [item["description"] for item in self.kb]
            self._kb_embeddings = encode_texts(
                self.model, descriptions, show_progress=True
            )
            logger.info(
                f"Indexed {len(self.kb)} phenomena "
                f"(embedding shape: {self._kb_embeddings.shape})"
            )

    def query(
        self,
        text: str,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> List[Dict]:
        """
        Search for structurally similar phenomena.

        Args:
            text: Natural language description of a phenomenon.
            top_k: Number of top results to return.
            threshold: Minimum similarity score (0-1) to include in results.

        Returns:
            List of dicts, each containing:
                - name: Phenomenon name
                - domain: Source domain
                - description: Full description
                - type_id: Structural type identifier
                - score: Cosine similarity score (0-1)
        """
        if self._kb_embeddings is None:
            logger.warning("No knowledge base loaded. Returning empty results.")
            return []

        # Encode query
        query_embedding = encode_texts(self.model, text)

        # Compute cosine similarities
        similarities = np.dot(self._kb_embeddings, query_embedding.T).flatten()

        # Rank by similarity
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < threshold:
                break
            item = self.kb[idx]
            results.append({
                "name": item.get("name", ""),
                "domain": item.get("domain", ""),
                "description": item.get("description", ""),
                "type_id": item.get("type_id", ""),
                "score": score,
            })

        return results

    def find_cross_domain_pairs(
        self,
        threshold: float = 0.7,
        max_pairs: int = 100,
    ) -> List[Dict]:
        """
        Find high-similarity cross-domain, cross-type pairs in the knowledge base.

        Useful for discovering potentially unknown structural connections.

        Args:
            threshold: Minimum similarity to consider.
            max_pairs: Maximum number of pairs to return.

        Returns:
            List of dicts with item_a, item_b, and similarity.
        """
        if self._kb_embeddings is None:
            logger.warning("No knowledge base loaded.")
            return []

        # Compute full similarity matrix
        sim_matrix = np.dot(self._kb_embeddings, self._kb_embeddings.T)

        pairs = []
        n = len(self.kb)
        for i in range(n):
            for j in range(i + 1, n):
                sim = float(sim_matrix[i][j])
                if sim < threshold:
                    continue
                # Skip same-type (already known)
                if self.kb[i].get("type_id") == self.kb[j].get("type_id"):
                    continue
                # Skip same-domain (less interesting)
                if self.kb[i].get("domain") == self.kb[j].get("domain"):
                    continue
                pairs.append({
                    "item_a": self.kb[i],
                    "item_b": self.kb[j],
                    "similarity": sim,
                })

        pairs.sort(key=lambda x: x["similarity"], reverse=True)
        return pairs[:max_pairs]

    def encode(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        Encode text(s) into structural embeddings.

        Args:
            text: Single string or list of strings.

        Returns:
            Numpy array of embeddings.
        """
        return encode_texts(self.model, text)

    def __repr__(self) -> str:
        kb_size = len(self.kb) if self.kb else 0
        return f"StructuralSearch(kb_size={kb_size})"
