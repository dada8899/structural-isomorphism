"""
V3 Option A: variant-type predictor scaffold.

Loads V1 embedding (SentenceTransformer from models/structural-v1) as frozen feature extractor,
trains a small MLP head to predict variant type multi-label from (A_desc, B_desc) concatenation.

Training data: plans/v4-seed-cases.yaml (after user review + LLM expansion to 200-500 cases).

This is a SCAFFOLD — wiring is done but actual train data loader assumes the expanded case file exists.
Run order:
  1. python v4_validate_seeds.py                             # user reviews starter seeds
  2. python v4_expand_seeds.py                                # LLM expands 10 → 200-500 cases (separate script TODO)
  3. python v4_train_transform_predictor.py --train           # this script
  4. python v4_train_transform_predictor.py --eval --split layer2-survivors  # eval on Layer 2 幸存

Usage:
    python v4_train_transform_predictor.py --train --epochs 20
    python v4_train_transform_predictor.py --eval
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "models" / "structural-v1"
PLANS_DIR = PROJECT_DIR / "plans"
V3_DIR = PROJECT_DIR / "models" / "v3-transform-predictor"

# Lazy imports: torch + sentence-transformers are heavy
def _lazy_imports():
    import numpy as np
    import torch
    import torch.nn as nn
    from sentence_transformers import SentenceTransformer
    return np, torch, nn, SentenceTransformer


def load_variant_ids() -> list[str]:
    with open(PLANS_DIR / "v4-variant-types.yaml") as f:
        data = yaml.safe_load(f)
    return [t["id"] for t in data["types"]]


def load_seed_cases(path: Path) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data["seeds"]


def case_to_features(case: dict, encoder) -> "np.ndarray":
    """Encode (A_desc, B_desc) as concatenated embeddings."""
    a_text = f"{case['source_domain']}: {case['source_concept']} — {case.get('source_equation','')}"
    b_text = f"{case['target_domain']}: {case['target_concept']} — {case.get('target_equation','')}"
    emb_a = encoder.encode(a_text, convert_to_numpy=True)
    emb_b = encoder.encode(b_text, convert_to_numpy=True)
    # Concatenation + elementwise diff (common for pair tasks)
    import numpy as np
    return np.concatenate([emb_a, emb_b, np.abs(emb_a - emb_b)])


def case_to_labels(case: dict, variant_ids: list[str]) -> "np.ndarray":
    """Multi-hot encoding of transformation types used in the case."""
    import numpy as np
    used = {t["type"] for t in case.get("transformations", [])}
    return np.array([1.0 if v in used else 0.0 for v in variant_ids], dtype="float32")


class TransformPredictorHead:
    """Minimal MLP head: (3*768) → 256 → len(variants). Not a real nn.Module here (lazy)."""

    def __init__(self, input_dim: int, n_variants: int, hidden: int = 256):
        _, _, nn, _ = _lazy_imports()
        self.model = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, n_variants),
        )

    def forward(self, x):
        return self.model(x)


def cmd_train(args):
    np, torch, nn, SentenceTransformer = _lazy_imports()

    variant_ids = load_variant_ids()
    n_variants = len(variant_ids)

    seed_file = PROJECT_DIR / args.seed_file
    if not seed_file.exists():
        print(f"ERROR: seed file not found: {seed_file}")
        print("       first run v4_validate_seeds.py, then v4_expand_seeds.py")
        sys.exit(1)

    cases = load_seed_cases(seed_file)
    print(f"Loaded {len(cases)} cases from {seed_file}")
    if len(cases) < 50:
        print(f"⚠️  only {len(cases)} cases — prototype quality will be rough. "
              f"Run v4_expand_seeds.py to scale to 200-500.")

    print(f"Loading V1 encoder from {MODEL_DIR}...")
    encoder = SentenceTransformer(str(MODEL_DIR))
    encoder.eval()
    for p in encoder.parameters():
        p.requires_grad = False

    print("Encoding features...")
    X = np.stack([case_to_features(c, encoder) for c in cases])
    Y = np.stack([case_to_labels(c, variant_ids) for c in cases])
    print(f"X shape: {X.shape}, Y shape: {Y.shape}")

    # Split 80/20
    n_train = int(0.8 * len(cases))
    perm = np.random.RandomState(42).permutation(len(cases))
    tr_idx, te_idx = perm[:n_train], perm[n_train:]

    X_tr = torch.tensor(X[tr_idx], dtype=torch.float32)
    Y_tr = torch.tensor(Y[tr_idx], dtype=torch.float32)
    X_te = torch.tensor(X[te_idx], dtype=torch.float32)
    Y_te = torch.tensor(Y[te_idx], dtype=torch.float32)

    head = TransformPredictorHead(X.shape[1], n_variants, hidden=256)
    optimizer = torch.optim.Adam(head.model.parameters(), lr=1e-3)
    loss_fn = nn.BCEWithLogitsLoss()

    print(f"Training {args.epochs} epochs...")
    for epoch in range(args.epochs):
        head.model.train()
        optimizer.zero_grad()
        logits = head.forward(X_tr)
        loss = loss_fn(logits, Y_tr)
        loss.backward()
        optimizer.step()

        if (epoch + 1) % max(1, args.epochs // 10) == 0:
            head.model.eval()
            with torch.no_grad():
                val_logits = head.forward(X_te)
                val_loss = loss_fn(val_logits, Y_te)
                val_preds = (torch.sigmoid(val_logits) > 0.5).float()
                acc = (val_preds == Y_te).float().mean().item()
                print(f"  epoch {epoch+1:3d}  train_loss={loss.item():.4f}  val_loss={val_loss.item():.4f}  val_acc={acc:.3f}")

    V3_DIR.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": head.model.state_dict(),
        "variant_ids": variant_ids,
        "input_dim": X.shape[1],
    }, V3_DIR / "head.pt")
    print(f"Saved: {V3_DIR / 'head.pt'}")


def cmd_eval(args):
    print("TODO: eval on Layer 2 survivors — needs cmd_train to produce head.pt first.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--seed-file", default="plans/v4-seed-cases.yaml",
                        help="defaults to post-review file; fall back to starter if absent")
    args = parser.parse_args()

    # Fallback to starter file if reviewed file missing
    if args.train and not (PROJECT_DIR / args.seed_file).exists():
        fallback = "plans/v4-seed-cases-starter.yaml"
        print(f"note: {args.seed_file} not found, falling back to {fallback}")
        args.seed_file = fallback

    if args.train:
        cmd_train(args)
    elif args.eval:
        cmd_eval(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
