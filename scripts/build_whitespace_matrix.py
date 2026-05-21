***REMOVED***!/usr/bin/env python3
"""A2 Whitespace Map — precompute the universality-class × domain matrix.

核心思想：26 个普适类 × 183 个领域 = 一个矩阵。每个普适类的 `domains`
字段列出它目前已覆盖（filled）的领域。对未覆盖的格子，如果该领域的
KB 现象质心与普适类代表文本结构相似（相似度 >= LEAD_THRESHOLD），
则视为「研究空白」（whitespace lead）—— 结构上理论上应成立但还没人验证。

输出：web/data/whitespace_matrix.json
  {
    "meta": {...},
    "classes": [{class_id, class_name, hub_name}, ...],
    "domains": [domain_name, ...],
    "matrix": { class_id: { domain: {state, score} } },
    "leads": [ {class_id, class_name, domain, score, anchor_id, anchor_name}, ... ]
  }

state ∈ {"filled", "lead", "empty"}

Usage:
  cd <repo root> && .venv/bin/python scripts/build_whitespace_matrix.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("build_whitespace")

_REPO = Path(__file__).resolve().parent.parent

KB_FILE = _REPO / "data" / "kb-expanded.jsonl"
CLASSES_FILE = _REPO / "web" / "frontend" / "assets" / "data" / "universality-classes.json"
EMB_FILE = _REPO / "web" / "data" / "kb_v2_embeddings.npy"
EMB_IDS_FILE = _REPO / "web" / "data" / "kb_v2_embeddings_ids.json"
OUT_FILE = _REPO / "web" / "data" / "whitespace_matrix.json"

***REMOVED*** Lead selection is percentile-based, not a fixed cosine cutoff. The encoding
***REMOVED*** model produces a domain-specific score scale (surface-similarity base model
***REMOVED*** yields cosines ~0.0-0.36), so a fixed threshold is brittle. Instead, for
***REMOVED*** each universality class we flag the unfilled domains whose centroid
***REMOVED*** similarity sits in the top LEAD_PERCENTILE of that class's own unfilled
***REMOVED*** scores AND clears the class's median filled score — i.e. "structurally as
***REMOVED*** plausible as the domains we already know belong to this class".
LEAD_PERCENTILE = 90.0  ***REMOVED*** top 10% of a class's unfilled domains
MIN_LEADS_PER_CLASS = 3  ***REMOVED*** always surface at least this many (best unfilled)
MAX_LEADS_PER_CLASS = 12  ***REMOVED*** cap so the list stays actionable


def normalize_domain(name: str) -> str:
    """Canonicalize a domain name for cross-source matching.

    The universality-classes.json has near-duplicate domain labels (e.g.
    '加密货币/DeFi' vs '加密货币与DeFi'). We strip separators / whitespace
    so such variants collapse to one key.
    """
    if not name:
        return ""
    s = name.strip()
    for ch in (" ", "/", "\\", "·", "、", "，", ",", "与", "和"):
        s = s.replace(ch, "")
    return s


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """True cosine similarity — divides by real norms (embeddings are NOT
    L2-normalized; kb_v2_embeddings.npy has norms ~14-22)."""
    a = np.asarray(a, dtype=np.float64).flatten()
    b = np.asarray(b, dtype=np.float64).flatten()
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return max(-1.0, min(1.0, float(np.dot(a, b) / (na * nb))))


def load_kb() -> list[dict]:
    rows: list[dict] = []
    with open(KB_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def main() -> int:
    if not (KB_FILE.exists() and CLASSES_FILE.exists()
            and EMB_FILE.exists() and EMB_IDS_FILE.exists()):
        logger.error("Missing input file(s); aborting.")
        return 1

    kb = load_kb()
    classes = json.load(open(CLASSES_FILE, "r", encoding="utf-8"))["classes"]
    embeddings = np.load(EMB_FILE)
    emb_ids = json.load(open(EMB_IDS_FILE, "r", encoding="utf-8"))
    logger.info("kb=%d classes=%d emb=%s", len(kb), len(classes), embeddings.shape)

    ***REMOVED*** id -> embedding row index
    idx_by_id = {pid: i for i, pid in enumerate(emb_ids)}

    ***REMOVED*** --- Group KB phenomena by domain (use the original domain label as the
    ***REMOVED*** display key, but a normalized key for matching). ---
    ***REMOVED*** domain_disp -> list of (phenomenon dict, emb_index)
    domain_phen: dict[str, list[tuple[dict, int]]] = {}
    norm_to_disp: dict[str, str] = {}
    for item in kb:
        dom = item.get("domain", "")
        pid = item.get("id", "")
        if not dom or pid not in idx_by_id:
            continue
        domain_phen.setdefault(dom, []).append((item, idx_by_id[pid]))
        norm_to_disp.setdefault(normalize_domain(dom), dom)

    ***REMOVED*** domain centroid + per-domain embedding rows (for anchor selection)
    domain_centroid: dict[str, np.ndarray] = {}
    for dom, phens in domain_phen.items():
        rows = np.stack([embeddings[i] for _, i in phens])
        domain_centroid[dom] = rows.mean(axis=0)

    all_domains = sorted(domain_phen.keys())
    logger.info("domains with phenomena=%d", len(all_domains))

    ***REMOVED*** --- We need to encode each class's representative text. Lazy-import the
    ***REMOVED*** model so the script fails fast on missing inputs above first. ---
    from structural_isomorphism.model import load_model, encode_texts
    model = load_model()

    class_texts: list[str] = []
    for c in classes:
        ***REMOVED*** Representative text: name + hub phenomenon + a short summary.
        parts = [
            c.get("name_zh", ""),
            c.get("name_en", ""),
            c.get("hub_name", ""),
            c.get("physics_prototype", "") or "",
            (c.get("summary_zh", "") or "")[:200],
        ]
        class_texts.append(" ".join(p for p in parts if p))
    class_embs = np.asarray(encode_texts(model, class_texts), dtype=np.float32)

    ***REMOVED*** --- Build matrix + leads ---
    matrix: dict[str, dict] = {}
    leads: list[dict] = []
    n_filled = n_lead = n_empty = 0

    for ci, c in enumerate(classes):
        cid = c["class_id"]
        cname = c.get("name_zh", cid)
        c_emb = class_embs[ci]

        ***REMOVED*** filled domains: normalize so '加密货币/DeFi' == '加密货币与DeFi'
        filled_norm = {normalize_domain(d) for d in c.get("domains", [])}

        ***REMOVED*** First pass: score every domain, separate filled vs unfilled.
        scores: dict[str, float] = {
            dom: round(cosine(c_emb, domain_centroid[dom]), 4)
            for dom in all_domains
        }
        filled_scores = [scores[d] for d in all_domains
                         if normalize_domain(d) in filled_norm]
        unfilled = [d for d in all_domains
                    if normalize_domain(d) not in filled_norm]

        ***REMOVED*** Lead bar for this class: top LEAD_PERCENTILE of unfilled scores,
        ***REMOVED*** but never below the median of the class's own filled domains.
        unfilled_scores = sorted((scores[d] for d in unfilled), reverse=True)
        if unfilled_scores:
            pct_bar = float(np.percentile(unfilled_scores, LEAD_PERCENTILE))
        else:
            pct_bar = 1.0
        filled_median = (float(np.median(filled_scores))
                         if filled_scores else -1.0)
        lead_bar = max(pct_bar, filled_median)

        ***REMOVED*** Rank unfilled domains; force a MIN/MAX band so every class shows
        ***REMOVED*** a few leads and no class floods the list.
        ranked_unfilled = sorted(unfilled, key=lambda d: scores[d], reverse=True)
        lead_domains: set[str] = set()
        for rank, dom in enumerate(ranked_unfilled):
            if rank < MIN_LEADS_PER_CLASS:
                lead_domains.add(dom)
            elif rank < MAX_LEADS_PER_CLASS and scores[dom] >= lead_bar:
                lead_domains.add(dom)
            else:
                break

        cells: dict[str, dict] = {}
        for dom in all_domains:
            score = scores[dom]
            if normalize_domain(dom) in filled_norm:
                state = "filled"
                n_filled += 1
            elif dom in lead_domains:
                state = "lead"
                n_lead += 1
            else:
                state = "empty"
                n_empty += 1
            cells[dom] = {"state": state, "score": score}

            if state == "lead":
                ***REMOVED*** anchor = the phenomenon in this domain most similar to the
                ***REMOVED*** class — the concrete "entry point" for a researcher.
                best_phen, best_sim = None, -2.0
                for phen, ei in domain_phen[dom]:
                    s = cosine(c_emb, embeddings[ei])
                    if s > best_sim:
                        best_sim, best_phen = s, phen
                leads.append({
                    "class_id": cid,
                    "class_name": cname,
                    "class_name_en": c.get("name_en", ""),
                    "hub_name": c.get("hub_name", ""),
                    "domain": dom,
                    "score": score,
                    "anchor_id": best_phen.get("id", "") if best_phen else "",
                    "anchor_name": best_phen.get("name", "") if best_phen else "",
                    "anchor_desc": (best_phen.get("description", "")[:120]
                                    if best_phen else ""),
                })
        matrix[cid] = cells

    ***REMOVED*** leads: sort by score desc — highest structural plausibility first.
    leads.sort(key=lambda x: (-x["score"], x["class_id"], x["domain"]))

    out = {
        "meta": {
            "generated_by": "scripts/build_whitespace_matrix.py",
            "lead_percentile": LEAD_PERCENTILE,
            "min_leads_per_class": MIN_LEADS_PER_CLASS,
            "max_leads_per_class": MAX_LEADS_PER_CLASS,
            "n_classes": len(classes),
            "n_domains": len(all_domains),
            "n_filled": n_filled,
            "n_lead": n_lead,
            "n_empty": n_empty,
            "n_leads": len(leads),
        },
        "classes": [
            {
                "class_id": c["class_id"],
                "class_name": c.get("name_zh", c["class_id"]),
                "class_name_en": c.get("name_en", ""),
                "hub_name": c.get("hub_name", ""),
                "rank": c.get("rank", 0),
            }
            for c in classes
        ],
        "domains": all_domains,
        "matrix": matrix,
        "leads": leads,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    logger.info(
        "Wrote %s — filled=%d lead=%d empty=%d (leads=%d)",
        OUT_FILE, n_filled, n_lead, n_empty, len(leads),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
