"""
F2 Active learning: contrastive fine-tune V1/V2 embedding from V4 critic feedback.

Approach: SimCSE-style InfoNCE loss with mined hard negatives.

This module ships *scaffold + simulation*, not the real torch fine-tune.
Why:
 - The V1/V2 sentence-transformer checkpoints are gitignored (782 MB) and
   live only on the VPS. Loading + tuning them needs GPU + the matching
   torch / transformers stack which we deliberately keep out of CI here.
 - The contrastive loss is straightforward; the *integration points* (data
   loaders, weighting, eval split, accept gates) are where bugs hide. We
   nail those down here with a math-faithful simulation that runs on
   sklearn + numpy, leaving only the optimizer swap for the real run.

Real-run swap (see `F2_active_learning_design.md` §3):
 - `ContrastiveFinetuner.fit` would replace the simulated rerank with a
   torch.optim loop over `SentenceTransformer.encode` query encoder.
 - `evaluate` keeps the same signatures.

Interface stability: this module IS callable on a laptop today; it just
returns simulated metrics. Production VPS run flips a flag and uses the
same dataclasses / training pair format.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data classes
# ---------------------------------------------------------------------------
@dataclass
class TrainingPair:
    """One contrastive training pair."""

    text_a: str
    text_b: str
    label: int          # 1 = similar (positive), 0 = dissimilar (hard negative)
    weight: float = 1.0
    source_class: str = ""
    source_verdict: str = ""
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrainingPair":
        return cls(
            text_a=d["text_a"],
            text_b=d["text_b"],
            label=int(d["label"]),
            weight=float(d.get("weight", 1.0)),
            source_class=d.get("source_class", ""),
            source_verdict=d.get("source_verdict", ""),
            confidence=float(d.get("confidence") or 0.0),
        )


@dataclass
class FinetuneMetrics:
    """Reported by `fit` and `evaluate`."""

    r_at_5: float = 0.0
    r_at_10: float = 0.0
    mrr: float = 0.0
    silhouette: float = 0.0
    cross_domain_r_at_5: float = 0.0
    train_loss: float = 0.0
    n_pairs: int = 0
    n_positives: int = 0
    n_hard_negatives: int = 0
    epochs: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# loss helper (math reference — not used in simulation path, but here so
# tests / readers can sanity-check the contrastive loss)
# ---------------------------------------------------------------------------
def info_nce_loss(
    anchor: np.ndarray,
    positive: np.ndarray,
    negatives: np.ndarray,
    temperature: float = 0.05,
) -> float:
    """SimCSE-style InfoNCE loss for one (anchor, positive, K-negative) triple.

    All inputs L2-normalised. Returns scalar loss.

    L = -log[ exp(sim(a, p) / τ) / (exp(sim(a, p) / τ) + Σ_k exp(sim(a, n_k) / τ)) ]
    """
    a = anchor / max(np.linalg.norm(anchor), 1e-12)
    p = positive / max(np.linalg.norm(positive), 1e-12)
    if negatives.ndim == 1:
        negatives = negatives[None, :]
    ns = negatives / np.linalg.norm(negatives, axis=1, keepdims=True).clip(1e-12, None)
    sim_pos = float(a @ p) / temperature
    sim_negs = (ns @ a) / temperature
    # logsumexp for numerical stability
    m = max(sim_pos, float(sim_negs.max()))
    denom = math.exp(sim_pos - m) + float(np.exp(sim_negs - m).sum())
    return -(sim_pos - m - math.log(denom))


# ---------------------------------------------------------------------------
# main scaffold
# ---------------------------------------------------------------------------
class ContrastiveFinetuner:
    """Scaffold for V1/V2 -> V3 contrastive fine-tune.

    Two modes:
      - "simulated" (default, runs anywhere): uses a TF-IDF vectorizer as a
        stand-in encoder; "fine-tune" is implemented by a per-pair weight
        re-scaling of dimensions plus a centroid rerank. Math-faithful for
        the loss + eval pipeline; no torch dep.
      - "real" (placeholder, VPS-only): loads SentenceTransformer from
        `base_model_path` and runs a torch optim loop. Raises NotImplementedError
        in this scaffold — to be filled by F2.1.

    Both modes share the same `load_pairs` / `fit` / `evaluate` signatures so
    callers can swap without code change.
    """

    def __init__(
        self,
        base_model_path: str | Path | None = None,
        lr: float = 1e-5,
        margin: float = 0.3,
        temperature: float = 0.05,
        mode: str = "simulated",
        out_dir: str | Path | None = None,
    ) -> None:
        self.base_model_path = Path(base_model_path) if base_model_path else None
        self.lr = lr
        self.margin = margin
        self.temperature = temperature
        self.mode = mode
        # default to a tmp dir-style location *inside* the test (callers
        # passing out_dir win); keep this off-repo to avoid stray artefacts.
        import tempfile
        self.out_dir = (
            Path(out_dir)
            if out_dir
            else Path(tempfile.gettempdir()) / "structural_iso_f2_ckpt"
        )

        if mode not in ("simulated", "real"):
            raise ValueError(f"mode must be 'simulated' or 'real', got {mode!r}")

        # Lazily fitted on `load_pairs` (simulated mode).
        self._vectorizer: Any = None
        self._pair_corpus: list[str] = []
        # Per-feature weight vector that fit() updates ("the model" in
        # simulated mode).
        self._weights: np.ndarray | None = None
        self._last_metrics: FinetuneMetrics | None = None

    # ---------- I/O ----------------------------------------------------------
    def load_pairs(
        self,
        positives_path: str | Path,
        negatives_path: str | Path,
    ) -> list[TrainingPair]:
        """Load mined pairs from miner output (jsonl)."""
        positives_path = Path(positives_path)
        negatives_path = Path(negatives_path)
        pairs: list[TrainingPair] = []

        for path, expect_label in ((positives_path, 1), (negatives_path, 0)):
            if not path.exists():
                logger.warning("Pair file missing: %s", path)
                continue
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    pair = TrainingPair.from_dict(d)
                    if pair.label != expect_label:
                        logger.warning(
                            "Label mismatch in %s: expected %d got %d",
                            path,
                            expect_label,
                            pair.label,
                        )
                    pairs.append(pair)

        logger.info(
            "Loaded %d pairs (%d positives, %d hard negatives) from %s + %s",
            len(pairs),
            sum(1 for p in pairs if p.label == 1),
            sum(1 for p in pairs if p.label == 0),
            positives_path.name,
            negatives_path.name,
        )
        return pairs

    # ---------- training ----------------------------------------------------
    def fit(
        self,
        pairs: list[TrainingPair],
        epochs: int = 3,
        batch_size: int = 32,
        vocab_corpus: Sequence[str] | None = None,
    ) -> FinetuneMetrics:
        """Fit the encoder on `pairs`.

        In "simulated" mode this fits a TF-IDF vectorizer over all pair text
        (or `vocab_corpus` if provided — useful when you want train+eval to
        share a vocabulary) and then updates a per-feature weight vector by
        gradient-free accumulation: positives push weights *up* on
        overlapping features, hard negatives push weights *down*.

        In "real" mode this would be the torch optim loop. Not implemented here.

        Returns FinetuneMetrics with `train_loss` and dataset sizes filled in;
        full eval metrics (R@5 etc.) come from `evaluate`.
        """
        if not pairs:
            raise ValueError("No pairs to fit on")

        if self.mode == "real":
            raise NotImplementedError(
                "Real-model fine-tune deferred to F2.1 (VPS GPU run). "
                "See v4/lib/F2_active_learning_design.md §3."
            )

        # ---- simulated fit -------------------------------------------------
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "scikit-learn required for simulated mode."
            ) from e

        pair_corpus: list[str] = []
        for p in pairs:
            pair_corpus.append(p.text_a)
            pair_corpus.append(p.text_b)
        self._pair_corpus = pair_corpus
        fit_corpus = list(vocab_corpus) if vocab_corpus else pair_corpus

        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 3),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
        )
        self._vectorizer.fit(fit_corpus)
        X = self._vectorizer.transform(pair_corpus)  # (2N, F)
        n_features = X.shape[1]
        weights = np.ones(n_features, dtype=np.float32)

        # Iterate (epochs) over pairs; accumulate small per-feature deltas.
        # The update rule (gradient-free, math-faithful to contrastive
        # objective):
        #   - for a positive pair: boost weights on features both texts share
        #     (those features signal "same class")
        #   - for a hard negative: cut weights on features both texts share
        #     (those features falsely linked them in the old space)
        # Magnitude scales with `lr * pair.weight * (margin - target*sim)`,
        # the standard hinge-style step. We allow weights to grow up to 10x
        # and shrink to 0.1x — a one-decade dynamic range that's plenty for
        # rerank purposes.
        total_loss = 0.0
        loss_count = 0
        rng = np.random.default_rng(seed=42)
        all_indices = np.arange(len(pairs))

        for epoch in range(epochs):
            rng.shuffle(all_indices)
            for start in range(0, len(all_indices), batch_size):
                batch_idx = all_indices[start : start + batch_size]
                for i in batch_idx:
                    p = pairs[int(i)]
                    va = X[int(i) * 2].toarray().ravel()
                    vb = X[int(i) * 2 + 1].toarray().ravel()
                    wva = va * weights
                    wvb = vb * weights
                    na = np.linalg.norm(wva)
                    nb = np.linalg.norm(wvb)
                    if na < 1e-9 or nb < 1e-9:
                        continue
                    sim = float(wva @ wvb / (na * nb))
                    target = 1.0 if p.label == 1 else -1.0
                    # hinge-style margin: only update if we're inside the margin
                    margin_violation = self.margin - target * sim
                    if margin_violation <= 0:
                        continue
                    shared = va * vb  # nonneg; nonzero only on shared features
                    if shared.max() <= 0:
                        continue
                    # normalise shared so per-pair update magnitude is bounded
                    shared = shared / max(shared.max(), 1e-12)
                    delta = self.lr * target * p.weight * margin_violation * shared
                    weights = np.clip(weights + delta, 0.1, 10.0)
                    total_loss += margin_violation
                    loss_count += 1

        self._weights = weights
        train_loss = total_loss / max(1, loss_count)
        metrics = FinetuneMetrics(
            train_loss=train_loss,
            n_pairs=len(pairs),
            n_positives=sum(1 for p in pairs if p.label == 1),
            n_hard_negatives=sum(1 for p in pairs if p.label == 0),
            epochs=epochs,
        )
        self._last_metrics = metrics

        # Persist a small "checkpoint" — the weight vector + vocabulary names.
        # Real run would call SentenceTransformer.save(self.out_dir).
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            np.save(self.out_dir / "weights.npy", weights)
            with open(self.out_dir / "metrics.json", "w", encoding="utf-8") as f:
                json.dump(metrics.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Could not persist sim checkpoint: %s", e)

        logger.info(
            "Simulated fit done: %d pairs, %d epochs, train_loss=%.4f",
            len(pairs),
            epochs,
            train_loss,
        )
        return metrics

    # ---------- evaluation --------------------------------------------------
    def evaluate(
        self,
        eval_pairs: list[TrainingPair],
        kb_texts: Sequence[str] | None = None,
        kb_domains: Sequence[str] | None = None,
    ) -> FinetuneMetrics:
        """Compute R@5, R@10, MRR, Silhouette on `eval_pairs`.

        For each positive pair (a, b), we score `b`'s rank among all *other*
        eval pair texts when querying with `a`. Cross-domain R@5 restricts to
        pairs where `a.domain != b.domain` if domains are provided.

        Silhouette: across positive vs negative pairs, are positives' cosine
        sim higher than negatives' on average? We compute a simple proxy:
        median(sim_pos) - median(sim_neg), squashed into [-1, 1].
        """
        if self._vectorizer is None or self._weights is None:
            raise RuntimeError("Call fit() before evaluate()")

        # encode all eval texts
        texts: list[str] = []
        for p in eval_pairs:
            texts.append(p.text_a)
            texts.append(p.text_b)
        X = self._vectorizer.transform(texts).toarray() * self._weights
        # L2 normalize rows
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        Xn = X / norms

        # R@k / MRR over positives
        ranks: list[int] = []
        cross_domain_hits: list[int] = []
        cross_domain_total = 0
        positives = [(i, p) for i, p in enumerate(eval_pairs) if p.label == 1]
        for pos_idx, pair in positives:
            a_row = pos_idx * 2
            b_row = pos_idx * 2 + 1
            sims = Xn @ Xn[a_row]
            sims[a_row] = -np.inf  # exclude self
            order = np.argsort(-sims)
            # rank of correct partner
            rank = int(np.where(order == b_row)[0][0]) + 1
            ranks.append(rank)

        r_at_5 = float(sum(1 for r in ranks if r <= 5) / max(1, len(ranks)))
        r_at_10 = float(sum(1 for r in ranks if r <= 10) / max(1, len(ranks)))
        mrr = float(sum(1.0 / r for r in ranks) / max(1, len(ranks)))

        # silhouette proxy: positives' sim should beat negatives' sim
        sim_pos: list[float] = []
        sim_neg: list[float] = []
        for i, p in enumerate(eval_pairs):
            s = float(Xn[i * 2] @ Xn[i * 2 + 1])
            (sim_pos if p.label == 1 else sim_neg).append(s)
        if sim_pos and sim_neg:
            sil = float(np.median(sim_pos) - np.median(sim_neg))
        elif sim_pos:
            sil = float(np.median(sim_pos))
        else:
            sil = 0.0
        # squash to [-1, 1]
        sil = max(-1.0, min(1.0, sil))

        # cross-domain R@5: only valid if kb_domains aligned with eval texts
        if kb_domains and len(kb_domains) == len(texts):
            ranks_xd: list[int] = []
            for pos_idx, pair in positives:
                a_row = pos_idx * 2
                b_row = pos_idx * 2 + 1
                if kb_domains[a_row] == kb_domains[b_row]:
                    continue
                cross_domain_total += 1
                sims = Xn @ Xn[a_row]
                sims[a_row] = -np.inf
                order = np.argsort(-sims)
                rank = int(np.where(order == b_row)[0][0]) + 1
                ranks_xd.append(rank)
            xd_r5 = (
                float(sum(1 for r in ranks_xd if r <= 5) / max(1, len(ranks_xd)))
                if ranks_xd
                else 0.0
            )
        else:
            xd_r5 = 0.0

        m = FinetuneMetrics(
            r_at_5=r_at_5,
            r_at_10=r_at_10,
            mrr=mrr,
            silhouette=sil,
            cross_domain_r_at_5=xd_r5,
            train_loss=self._last_metrics.train_loss if self._last_metrics else 0.0,
            n_pairs=len(eval_pairs),
            n_positives=sum(1 for p in eval_pairs if p.label == 1),
            n_hard_negatives=sum(1 for p in eval_pairs if p.label == 0),
            epochs=self._last_metrics.epochs if self._last_metrics else 0,
        )
        return m

    # ---------- introspection -----------------------------------------------
    @property
    def is_fitted(self) -> bool:
        return self._weights is not None

    @property
    def last_metrics(self) -> FinetuneMetrics | None:
        return self._last_metrics
