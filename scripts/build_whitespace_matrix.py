***REMOVED***!/usr/bin/env python3
"""A2 Whitespace Map — precompute the universality-class × domain matrix.

核心思想：26 个普适类 × 183 个领域 = 一个矩阵。每个普适类的 `domains`
字段列出它目前已覆盖（filled）的领域。对未覆盖的格子，如果该领域结构上
理论上应属于该普适类，则视为「研究空白」（whitespace lead）。

Session ***REMOVED***18 深化（A2 二版）——解决初版"所有类恰好顶到 12 条上限"的短板：

  1. 信号融合（非 LLM）：不再只用 base-model 的 embedding 质心余弦。
     裸 embedding 是 surface-similarity，区分度极低。新增 type_id 结构信号：
       - 每个普适类有一个「type_id 签名」——它在 members_by_domain 里
         列出的成员现象，回查 KB 拿到的 type_id 归一化直方图。
       - 每个领域有一个「type_id 画像」——该领域所有 KB 现象的 type_id
         归一化直方图。
       - type_match 用「富集度」（enrichment）而非裸重叠：把领域画像里
         每个 type_id 的占比，按"该 type_id 在类签名里的权重 / 在全 KB
         里的基线占比"加权求和。这样通用 type_id（到处都有）不加分，
         只有该领域真的富集了该普适类的特征结构才得高分。富集度量纲
         无上界，用 tanh 压缩到 [0,1) 再参与融合。
     融合分 = SIGNAL_BLEND·type_match + (1-SIGNAL_BLEND)·embedding_cos。
     type_id 富集信号比裸 embedding（和裸重叠）锐利得多——实测某类
     enrichment 跨领域中位数 0.4、最高 10.6，区分度充足。

  2. lead 选择不再用僵硬的 MIN/MAX 配额。改为：未覆盖领域里融合分
     >= 该类自身已覆盖领域融合分中位数（绝对、类相对的门槛）的格子才
     算 lead。"和这个类已知成员一样结构合理"才入选，因类而异。

  3. LLM 评判层（仅在配置了 OPENROUTER_API_KEY 时运行 `--llm`）：
     对每个普适类取候选格子（融合分 top LLM_CANDIDATE_TOPK 的未覆盖领域），
     让 LLM 逐个评判"这个领域是否真的大概率存在属于该普适类的现象"，
     返回 plausible(yes/maybe/no) + 一句理由 + 一个具体可验证的研究问题。
     no 的剔除，yes/maybe 保留为 lead 并写入 rationale / research_question。
     无 key 时跳过本层，保留第 1-2 点的非 LLM 信号结果（优雅降级）。

输出：web/data/whitespace_matrix.json
  {
    "meta": {...},
    "classes": [{class_id, class_name, hub_name, ...}, ...],
    "domains": [domain_name, ...],
    "matrix": { class_id: { domain: {state, score} } },
    "leads": [ {class_id, ..., domain, score, anchor_id, anchor_name,
                signal: {type_match, embedding_cos},
                plausible?, rationale?, research_question?}, ... ]
  }

state ∈ {"filled", "lead", "empty"}

Usage:
  cd <repo root> && .venv/bin/python scripts/build_whitespace_matrix.py
  cd <repo root> && OPENROUTER_API_KEY=... .venv/bin/python \
      scripts/build_whitespace_matrix.py --llm
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
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

***REMOVED*** --- Signal fusion ---
***REMOVED*** The base encoding model is surface-similarity (cosines cluster ~0.0-0.36
***REMOVED*** with almost no spread), so it cannot discriminate leads on its own.
***REMOVED*** We blend it with a type_id enrichment signal. SIGNAL_BLEND is the weight
***REMOVED*** on the (sharper) type_id signal; the remainder goes to embedding.
SIGNAL_BLEND = 0.7

***REMOVED*** Raw enrichment is unbounded; ENRICH_SCALE sets the tanh squash so a
***REMOVED*** "neutral" enrichment (~baseline, value ~1) maps to a modest score and a
***REMOVED*** strongly enriched domain (value ~5+) saturates near 1.
ENRICH_SCALE = 2.5

***REMOVED*** A class needs at least this many KB-resolvable members for its type_id
***REMOVED*** signature to be trustworthy; below it we fall back to embedding-only.
MIN_MEMBERS_FOR_SIGNATURE = 3

***REMOVED*** Lead bar = max(class filled-domain median, LEAD_BAR_FLOOR). The floor is
***REMOVED*** an absolute cut on the fused score so classes with weak/empty filled sets
***REMOVED*** still get a meaningful bar instead of admitting everything. To avoid an
***REMOVED*** empty list, always keep at least MIN_LEADS_FLOOR best unfilled domains;
***REMOVED*** MAX_LEADS_CAP keeps the list actionable.
LEAD_BAR_FLOOR = 0.30
MIN_LEADS_FLOOR = 3
MAX_LEADS_CAP = 20

***REMOVED*** --- LLM judging layer (only with --llm + OPENROUTER_API_KEY) ---
LLM_CANDIDATE_TOPK = 18   ***REMOVED*** judge this many top-fused unfilled domains per class
_PLAUSIBLE_ENUM = {"yes", "maybe", "no"}


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


***REMOVED*** --------------------------------------------------------------------------
***REMOVED*** type_id structural signal
***REMOVED*** --------------------------------------------------------------------------


def histogram(type_ids: list[str]) -> dict[str, float]:
    """Normalized (sums to 1) histogram of type_id occurrences."""
    counts: dict[str, float] = {}
    for t in type_ids:
        if t:
            counts[t] = counts.get(t, 0.0) + 1.0
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def type_enrichment(
    sig: dict[str, float],
    profile: dict[str, float],
    baseline: dict[str, float],
) -> float:
    """Raw enrichment of a domain's type_id profile against a class signature.

    For each type_id the class cares about, weight the domain's share of
    that type_id by how *characteristic* it is for the class relative to
    the global KB baseline (sig_t / baseline_t). A type_id that is common
    everywhere (high baseline) contributes little even if the class has it;
    a type_id the class is concentrated in but the KB at large is not gives
    a big multiplier — i.e. genuine structural enrichment, not surface mass.

    Range [0, +inf). ~1 ≈ baseline; >>1 = strongly enriched. Squash with
    `squash_enrichment` before blending.
    """
    if not sig or not profile or not baseline:
        return 0.0
    total = 0.0
    for t, w in sig.items():
        base = baseline.get(t, 0.0)
        if base <= 1e-9:
            continue
        total += profile.get(t, 0.0) * (w / base)
    return float(total)


def squash_enrichment(value: float) -> float:
    """Squash an unbounded enrichment value into [0, 1) via tanh.

    ENRICH_SCALE controls the knee: a neutral enrichment (~1) maps to a
    modest score, a strongly enriched domain saturates toward 1.
    """
    import math
    return math.tanh(max(0.0, value) / ENRICH_SCALE)


def class_type_signature(
    cls: dict, kb_by_name: dict[str, dict]
) -> tuple[dict[str, float], int]:
    """Build a class's type_id signature from its members_by_domain names.

    Returns (normalized histogram, n_resolved_members). When too few members
    resolve against the KB the signature is unreliable — caller should then
    fall back to the embedding-only signal.
    """
    type_ids: list[str] = []
    for mbd in cls.get("members_by_domain", []) or []:
        for nm in mbd.get("names", []) or []:
            row = kb_by_name.get(nm)
            if row and row.get("type_id"):
                type_ids.append(str(row["type_id"]))
    return histogram(type_ids), len(type_ids)


***REMOVED*** --------------------------------------------------------------------------
***REMOVED*** LLM judging layer
***REMOVED*** --------------------------------------------------------------------------

_LLM_SYSTEM = (
    "你是跨学科结构科学的评审。给定一个「普适类」（一种抽象的结构/动力学模式）"
    "和一个候选学科领域，你要判断：这个领域里是否大概率真实存在属于该普适类的现象。"
    "只依据结构合理性判断，不要被表面术语误导。"
    "严格返回 JSON：{\"plausible\":\"yes|maybe|no\",\"rationale\":\"一句中文理由\","
    "\"research_question\":\"一句具体、可验证的中文研究问题\"}。"
    "plausible=yes 表示结构上几乎必然存在；maybe 表示有合理可能但需验证；"
    "no 表示结构上不太可能。research_question 必须具体到可设计验证，"
    "不要泛泛而谈。"
)


def _build_llm_user_prompt(cls: dict, domain: str, anchor: dict | None) -> str:
    parts = [
        f"普适类名称：{cls.get('name_zh', cls.get('class_id'))}",
        f"枢纽现象：{cls.get('hub_name', '')}",
        f"物理原型：{cls.get('physics_prototype', '') or '—'}",
    ]
    inv = cls.get("invariants") or []
    if inv:
        parts.append("结构不变量：" + "；".join(str(x) for x in inv[:4]))
    summary = (cls.get("summary_zh", "") or "")[:240]
    if summary:
        parts.append(f"普适类简述：{summary}")
    parts.append(f"\n候选领域：{domain}")
    if anchor:
        parts.append(
            f"该领域一个结构最接近的现象（参考切入点）："
            f"{anchor.get('name', '')} — {(anchor.get('description', '') or '')[:160]}"
        )
    parts.append(
        "\n请判断该领域是否大概率存在属于该普适类的现象，并给出研究问题。"
    )
    return "\n".join(parts)


def _coerce_llm_verdict(raw: object) -> dict | None:
    """Validate one LLM verdict dict. Returns a clean dict or None to reject.

    Guardrails (never trust LLM output on the execution path):
      - must be a dict;
      - plausible coerced into {yes,maybe,no}, else rejected;
      - 'no' verdicts rejected here (caller drops them from leads);
      - rationale / research_question coerced to non-empty strings, with a
        graceful fallback when research_question is missing.
    """
    if not isinstance(raw, dict):
        return None
    plausible = str(raw.get("plausible", "")).strip().lower()
    if plausible not in _PLAUSIBLE_ENUM:
        return None
    if plausible == "no":
        return {"plausible": "no"}  ***REMOVED*** signal: drop this lead
    rationale = str(raw.get("rationale", "") or "").strip()
    question = str(raw.get("research_question", "") or "").strip()
    if not rationale:
        rationale = "（LLM 未给出理由）"
    ***REMOVED*** research_question missing -> caller substitutes a templated fallback.
    return {
        "plausible": plausible,
        "rationale": rationale[:400],
        "research_question": question[:400],  ***REMOVED*** may be "" -> fallback at caller
    }


def _fallback_research_question(class_name: str, domain: str, anchor_name: str) -> str:
    """Templated research question used when the LLM omits one."""
    tail = f"以「{anchor_name}」为切入点验证。" if anchor_name else ""
    return f"{domain}中是否存在属于「{class_name}」的结构同构现象？{tail}"


async def _judge_one(cls: dict, domain: str, anchor: dict | None) -> dict | None:
    """Run one LLM verdict for a (class, domain) candidate. None on failure."""
    from services.llm_client import complete_json

    raw = await complete_json(
        system=_LLM_SYSTEM,
        user=_build_llm_user_prompt(cls, domain, anchor),
        temperature=0.3,
        max_tokens=600,
    )
    if raw is None:
        return None
    return _coerce_llm_verdict(raw)


async def run_llm_layer(
    classes: list[dict],
    candidates: dict[str, list[dict]],
) -> dict[str, dict[str, dict]]:
    """Judge candidate leads with the LLM, class by class.

    Args:
        classes:    universality-class dicts (for prompt context).
        candidates: class_id -> list of candidate lead dicts (each has
                    'domain' + optional 'anchor' for prompt context).
    Returns:
        class_id -> { domain -> verdict dict }  (verdict per _coerce_llm_verdict)
    """
    cls_by_id = {c["class_id"]: c for c in classes}
    verdicts: dict[str, dict[str, dict]] = {}
    for cid, cands in candidates.items():
        cls = cls_by_id.get(cid)
        if not cls:
            continue
        verdicts[cid] = {}
        for cand in cands:
            dom = cand["domain"]
            v = await _judge_one(cls, dom, cand.get("anchor"))
            if v is not None:
                verdicts[cid][dom] = v
        logger.info(
            "LLM judged class=%s candidates=%d verdicts=%d",
            cid, len(cands), len(verdicts[cid]),
        )
    return verdicts


***REMOVED*** --------------------------------------------------------------------------
***REMOVED*** main
***REMOVED*** --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build A2 whitespace matrix.")
    parser.add_argument(
        "--llm", action="store_true",
        help="Run the LLM judging layer (needs OPENROUTER_API_KEY).",
    )
    args = parser.parse_args(argv)

    if not (KB_FILE.exists() and CLASSES_FILE.exists()
            and EMB_FILE.exists() and EMB_IDS_FILE.exists()):
        logger.error("Missing input file(s); aborting.")
        return 1

    kb = load_kb()
    kb_by_name = {r.get("name"): r for r in kb if r.get("name")}
    classes = json.load(open(CLASSES_FILE, "r", encoding="utf-8"))["classes"]
    embeddings = np.load(EMB_FILE)
    emb_ids = json.load(open(EMB_IDS_FILE, "r", encoding="utf-8"))
    logger.info("kb=%d classes=%d emb=%s", len(kb), len(classes), embeddings.shape)

    ***REMOVED*** id -> embedding row index
    idx_by_id = {pid: i for i, pid in enumerate(emb_ids)}

    ***REMOVED*** --- Group KB phenomena by domain. ---
    domain_phen: dict[str, list[tuple[dict, int]]] = {}
    for item in kb:
        dom = item.get("domain", "")
        pid = item.get("id", "")
        if not dom or pid not in idx_by_id:
            continue
        domain_phen.setdefault(dom, []).append((item, idx_by_id[pid]))

    ***REMOVED*** domain centroid (embedding) + domain type_id profile.
    domain_centroid: dict[str, np.ndarray] = {}
    domain_type_profile: dict[str, dict[str, float]] = {}
    for dom, phens in domain_phen.items():
        rows = np.stack([embeddings[i] for _, i in phens])
        domain_centroid[dom] = rows.mean(axis=0)
        domain_type_profile[dom] = histogram(
            [str(p.get("type_id", "")) for p, _ in phens]
        )

    all_domains = sorted(domain_phen.keys())
    logger.info("domains with phenomena=%d", len(all_domains))

    ***REMOVED*** Global type_id baseline over the whole KB — the denominator for the
    ***REMOVED*** enrichment signal (a type_id common everywhere should not score).
    type_baseline = histogram(
        [str(r.get("type_id", "")) for r in kb if r.get("type_id")]
    )

    ***REMOVED*** --- Encode each class's representative text (embedding signal). ---
    from structural_isomorphism.model import load_model, encode_texts
    model = load_model()

    class_texts: list[str] = []
    for c in classes:
        parts = [
            c.get("name_zh", ""),
            c.get("name_en", ""),
            c.get("hub_name", ""),
            c.get("physics_prototype", "") or "",
            (c.get("summary_zh", "") or "")[:200],
        ]
        class_texts.append(" ".join(p for p in parts if p))
    class_embs = np.asarray(encode_texts(model, class_texts), dtype=np.float32)

    ***REMOVED*** --- Build matrix + leads (non-LLM signal). ---
    matrix: dict[str, dict] = {}
    leads: list[dict] = []
    ***REMOVED*** candidates handed to the optional LLM layer.
    llm_candidates: dict[str, list[dict]] = {}
    n_filled = n_lead = n_empty = 0
    n_sig_used = 0  ***REMOVED*** how many classes had a usable type_id signature

    for ci, c in enumerate(classes):
        cid = c["class_id"]
        cname = c.get("name_zh", cid)
        c_emb = class_embs[ci]

        ***REMOVED*** type_id signature for this class.
        sig, n_members = class_type_signature(c, kb_by_name)
        use_sig = n_members >= MIN_MEMBERS_FOR_SIGNATURE and bool(sig)
        if use_sig:
            n_sig_used += 1

        filled_norm = {normalize_domain(d) for d in c.get("domains", [])}

        ***REMOVED*** --- Score every domain: fuse embedding cosine + type_id enrichment. ---
        emb_cos: dict[str, float] = {}
        type_match: dict[str, float] = {}  ***REMOVED*** squashed enrichment, in [0, 1)
        fused: dict[str, float] = {}
        for dom in all_domains:
            ec = cosine(c_emb, domain_centroid[dom])
            emb_cos[dom] = round(ec, 4)
            if use_sig:
                enr = type_enrichment(
                    sig, domain_type_profile.get(dom, {}), type_baseline
                )
                tm = squash_enrichment(enr)
                type_match[dom] = round(tm, 4)
                ***REMOVED*** Both signals in [~0, 1]; type_id enrichment is the sharper.
                fused[dom] = round(
                    SIGNAL_BLEND * tm + (1.0 - SIGNAL_BLEND) * max(0.0, ec), 4
                )
            else:
                type_match[dom] = 0.0
                fused[dom] = emb_cos[dom]

        filled_scores = [fused[d] for d in all_domains
                         if normalize_domain(d) in filled_norm]
        unfilled = [d for d in all_domains
                    if normalize_domain(d) not in filled_norm]

        ***REMOVED*** Lead bar = max(class filled-domain median, absolute floor). A lead
        ***REMOVED*** must be "as structurally plausible as the domains we already know
        ***REMOVED*** belong here" AND clear an absolute floor. No rigid per-class quota
        ***REMOVED*** — counts vary by class.
        filled_median = (float(np.median(filled_scores))
                         if filled_scores else 0.0)
        lead_bar = max(filled_median, LEAD_BAR_FLOOR)

        ranked_unfilled = sorted(unfilled, key=lambda d: fused[d], reverse=True)
        lead_domains: list[str] = []
        for rank, dom in enumerate(ranked_unfilled):
            if len(lead_domains) >= MAX_LEADS_CAP:
                break
            if rank < MIN_LEADS_FLOOR:
                lead_domains.append(dom)          ***REMOVED*** always surface a few
            elif fused[dom] >= lead_bar:
                lead_domains.append(dom)
            else:
                break  ***REMOVED*** ranked desc — nothing below clears the bar either
        lead_set = set(lead_domains)

        cells: dict[str, dict] = {}
        for dom in all_domains:
            score = fused[dom]
            if normalize_domain(dom) in filled_norm:
                state = "filled"
                n_filled += 1
            elif dom in lead_set:
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
                lead = {
                    "class_id": cid,
                    "class_name": cname,
                    "class_name_en": c.get("name_en", ""),
                    "hub_name": c.get("hub_name", ""),
                    "domain": dom,
                    "score": score,
                    "signal": {
                        "type_match": type_match[dom],
                        "embedding_cos": emb_cos[dom],
                        "used_type_signature": use_sig,
                    },
                    "anchor_id": best_phen.get("id", "") if best_phen else "",
                    "anchor_name": best_phen.get("name", "") if best_phen else "",
                    "anchor_desc": (best_phen.get("description", "")[:120]
                                    if best_phen else ""),
                }
                leads.append(lead)
                llm_candidates.setdefault(cid, []).append(
                    {"domain": dom, "anchor": best_phen, "_lead_ref": lead}
                )
        matrix[cid] = cells

    ***REMOVED*** Keep only the top-K candidates per class for the LLM layer (by score).
    for cid in llm_candidates:
        llm_candidates[cid] = sorted(
            llm_candidates[cid],
            key=lambda x: -x["_lead_ref"]["score"],
        )[:LLM_CANDIDATE_TOPK]

    ***REMOVED*** --- Optional LLM judging layer. ---
    llm_ran = False
    n_llm_dropped = 0
    if args.llm:
        if not os.getenv("OPENROUTER_API_KEY"):
            logger.warning(
                "--llm requested but OPENROUTER_API_KEY unset — skipping LLM layer."
            )
        else:
            logger.info("Running LLM judging layer over candidate leads...")
            verdicts = asyncio.run(run_llm_layer(classes, llm_candidates))
            llm_ran = True
            kept: list[dict] = []
            for lead in leads:
                v = verdicts.get(lead["class_id"], {}).get(lead["domain"])
                if v is None:
                    ***REMOVED*** LLM gave no verdict (network / parse fail) — keep the
                    ***REMOVED*** lead on the non-LLM signal, no LLM fields attached.
                    kept.append(lead)
                    continue
                if v.get("plausible") == "no":
                    n_llm_dropped += 1
                    ***REMOVED*** demote the matrix cell from lead -> empty.
                    cell = matrix.get(lead["class_id"], {}).get(lead["domain"])
                    if cell:
                        cell["state"] = "empty"
                    continue
                lead["plausible"] = v["plausible"]
                lead["rationale"] = v["rationale"]
                q = v.get("research_question") or ""
                lead["research_question"] = q or _fallback_research_question(
                    lead["class_name"], lead["domain"], lead.get("anchor_name", "")
                )
                kept.append(lead)
            leads = kept
            ***REMOVED*** recount lead / empty after LLM demotions.
            n_lead = sum(1 for cls in matrix.values()
                         for cell in cls.values() if cell["state"] == "lead")
            n_empty = sum(1 for cls in matrix.values()
                          for cell in cls.values() if cell["state"] == "empty")
            logger.info("LLM layer: dropped %d leads (plausible=no)", n_llm_dropped)

    ***REMOVED*** strip internal-only refs before serializing.
    for lead in leads:
        lead.pop("_lead_ref", None)

    ***REMOVED*** leads: sort by score desc — highest structural plausibility first.
    leads.sort(key=lambda x: (-x["score"], x["class_id"], x["domain"]))

    ***REMOVED*** lead-count spread diagnostics.
    from collections import Counter
    lead_counts = Counter(x["class_id"] for x in leads)
    counts_sorted = sorted(lead_counts.values(), reverse=True)

    out = {
        "meta": {
            "generated_by": "scripts/build_whitespace_matrix.py",
            "signal_blend": SIGNAL_BLEND,
            "enrich_scale": ENRICH_SCALE,
            "lead_bar_floor": LEAD_BAR_FLOOR,
            "min_leads_floor": MIN_LEADS_FLOOR,
            "max_leads_cap": MAX_LEADS_CAP,
            "classes_with_type_signature": n_sig_used,
            "llm_layer_ran": llm_ran,
            "llm_dropped": n_llm_dropped,
            "n_classes": len(classes),
            "n_domains": len(all_domains),
            "n_filled": n_filled,
            "n_lead": n_lead,
            "n_empty": n_empty,
            "n_leads": len(leads),
            "lead_count_min": min(counts_sorted) if counts_sorted else 0,
            "lead_count_max": max(counts_sorted) if counts_sorted else 0,
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
        "Wrote %s — filled=%d lead=%d empty=%d (leads=%d, per-class %d..%d)",
        OUT_FILE, n_filled, n_lead, n_empty, len(leads),
        out["meta"]["lead_count_min"], out["meta"]["lead_count_max"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
