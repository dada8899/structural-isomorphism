#!/usr/bin/env python3
"""B1 — Finalize the universality-class taxonomy from the Layer-3 critic pass.

The Layer-3 critic pass already produced per-class verdicts (KEEP / SPLIT /
MERGE / REJECT) in `v4/results/layer3_critic.jsonl`, but the conclusions were
left scattered in free text. This script *closes* B1: it folds the verdicts
into a single authoritative artifact — final active classes + a structured
negative-example library + cleaned member lists.

Authority model
---------------
- B1 critic (single-pass, hand-authored,逐条审查) is the AUTHORITATIVE base.
  The task brief fixes its result: KEEP 11 / SPLIT 4 / MERGE 3 / REJECT 3.
- B3 ensemble (3 reviewers) and B4 DeepSeek ensemble are SECONDARY views,
  used only as cross-checks. NOTE: the B4 DeepSeek prompt was deliberately
  ultra-strict and rejected nearly every class (even rock-solid KEEPs like
  scheffer / second_order_damped) — so B4 is NOT treated as ground truth,
  only as a tie-break signal for genuinely undecided merge questions.

What "finalize" means here
--------------------------
1. REJECT  -> class dropped from the active taxonomy (kept in record as
             rejected, with reason).
2. MERGE   -> pair of provenance-duplicate classes collapsed into one canonical
             class; members unioned.
3. SPLIT   -> class dissolved into the tighter sub-classes named in the
             critic's split_suggestion (recorded as derived children).
4. KEEP    -> class survives as an active universality class.
5. For every surviving class: build the negative-example library from the
   critic's curated near-miss list, and prune members flagged as false
   positives.

LLM supplemental pass
---------------------
Only classes whose critic verdict is genuinely UNDECIDED get a DeepSeek V4
supplemental judgement (same key / model as b4_deepseek_ensemble.py). A class
is "undecided" iff the critic itself hedged its merge recommendation
("possibly", "could", "consider", "subtle") AND the ensemble disagreed with
the critic. SPLIT classes are NOT undecided — the critic gave concrete
split_suggestion text for each.

Outputs
-------
- v4/results/B1_final_taxonomy.jsonl  — one row per ACTIVE class
- v4/results/B1_final_summary.md      — human-readable wrap-up

Run from repo root:  python3 v4/scripts/b1_finalize_taxonomy.py
Add --no-llm to skip the DeepSeek supplemental pass (offline / dry runs).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CRITIC_IN = REPO / "v4" / "results" / "layer3_critic.jsonl"
AUTO_CURATED_IN = REPO / "v4" / "results" / "layer3_auto_curated.jsonl"
CANDIDATES_IN = REPO / "v4" / "results" / "candidate_classes.jsonl"
B3_IN = REPO / "v4" / "results" / "B3_taxonomy_v2.jsonl"
B4_IN = REPO / "v4" / "results" / "B4_deepseek_ensemble.jsonl"
TAXONOMY_OUT = REPO / "v4" / "results" / "B1_final_taxonomy.jsonl"
SUMMARY_OUT = REPO / "v4" / "results" / "B1_final_summary.md"

DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"

logging.basicConfig(
    level=logging.INFO,
    format="[B1-finalize] %(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("b1_finalize")


# ---------------------------------------------------------------------------
# .env loader (zero-dep, mirrors b4_deepseek_ensemble.py)
# ---------------------------------------------------------------------------

def load_dotenv() -> None:
    env_path = REPO / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError as e:
        log.warning("could not read .env: %s", e)


# ---------------------------------------------------------------------------
# Robust JSONL reader — never crashes on a bad line, just skips + logs.
# ---------------------------------------------------------------------------

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        log.error("input file missing: %s", path)
        return rows
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    log.warning("skipping bad JSON at %s:%d (%s)", path.name, i, e)
    except OSError as e:
        log.error("could not read %s: %s", path, e)
    log.info("loaded %d rows from %s", len(rows), path.name)
    return rows


# ---------------------------------------------------------------------------
# Member-list resolution.
# Members live in candidate_classes.jsonl keyed by hub name. auto_curated rows
# carry hub_name -> we map class_id to its member list via the hub.
# The 6 critic classes that are NOT in auto_curated are mapped by a hand table
# (their hubs are unambiguous in candidate_classes.jsonl).
# ---------------------------------------------------------------------------

# class_id -> hub name (for the 6 extra critic classes not in auto_curated)
EXTRA_HUB_MAP: dict[str, str] = {
    "hysteresis_preisach": "热固性树脂凝胶点渗流相变",
    "scheffer_fold_bifurcation": "蛋白质相分离的临界浓度阈值",
    "tail_copula_contagion": "相关性崩溃的尾部传染效应",
    "gardner_collins_toggle_switch_Th1Th2": "Th1/Th2极化与疾病偏向",
    "schelling_credible_commitment": "进入威慑与产能过度承诺",
    "motter_lai_network_cascade_social": "级联失效在社会网络中的传播",
    # hysteresis_first_order_transition_fertility / gardner_collins_apoptosis
    # share their hub with the auto_curated sibling; resolved below.
    "hysteresis_first_order_transition_fertility": "低生育率陷阱假说",
    "gardner_collins_toggle_switch_apoptosis": "凋亡Caspase级联的不可逆数字开关",
}


def build_hub_members(candidates: list[dict]) -> dict[str, list[str]]:
    """hub-name -> ordered member-name list."""
    out: dict[str, list[str]] = {}
    for c in candidates:
        hub = (c.get("hub") or {}).get("name")
        if not hub:
            continue
        members = [m.get("name") for m in (c.get("members") or []) if m.get("name")]
        # if a hub appears twice, keep the larger member set
        if hub not in out or len(members) > len(out[hub]):
            out[hub] = members
    return out


def resolve_members(
    class_id: str,
    auto_curated_by_id: dict[str, dict],
    hub_members: dict[str, list[str]],
) -> list[str]:
    """Best-effort member resolution. Returns [] (never crashes) if unknown."""
    hub = None
    if class_id in auto_curated_by_id:
        hub = auto_curated_by_id[class_id].get("hub_name")
    if not hub:
        hub = EXTRA_HUB_MAP.get(class_id)
    if not hub:
        log.warning("no hub mapping for class_id=%s -> empty member list", class_id)
        return []
    members = hub_members.get(hub)
    if members is None:
        log.warning("hub '%s' not found in candidate_classes -> empty members", hub)
        return []
    return list(members)


# ---------------------------------------------------------------------------
# Verdict normalization.
# ---------------------------------------------------------------------------

def base_verdict(raw: str) -> str:
    """Collapse a critic verdict string to KEEP / SPLIT / MERGE / REJECT."""
    v = (raw or "").upper().strip()
    if v.startswith("MERGE"):
        return "MERGE"
    if v.startswith("SPLIT"):
        return "SPLIT"
    if v.startswith("REJECT"):
        return "REJECT"
    if v.startswith("KEEP"):
        return "KEEP"
    return "UNCLEAR"


# Hedge markers that signal a critic merge recommendation is *undecided*.
HEDGE_MARKERS = ("possib", "could", "consider", "subtle", "or with", "may ")


def is_undecided(critic_row: dict, b3_row: dict | None, b4_consensus: str | None) -> tuple[bool, str]:
    """A KEEP class is undecided iff the critic hedged a merge recommendation
    AND an ensemble view disagreed. Returns (flag, reason)."""
    if base_verdict(critic_row.get("review_verdict", "")) != "KEEP":
        return False, ""
    merge_text = (critic_row.get("merge_with") or "")
    if not isinstance(merge_text, str) or not merge_text.strip():
        return False, ""
    # If the merge note says THIS class should absorb a provenance-duplicate
    # variant (e.g. *_social / *_apoptosis), the class is the canonical
    # receiver — that is a settled MERGE, not an undecided merge question.
    if any(v in merge_text for v in ("_social", "_apoptosis", "_Th1Th2")):
        return False, ""
    hedged = any(m in merge_text.lower() for m in HEDGE_MARKERS)
    if not hedged:
        return False, ""
    b3v = (b3_row or {}).get("b3_consensus", "")
    ensemble_disagrees = (
        base_verdict(b3v) not in ("KEEP", "")
        or (b4_consensus and base_verdict(b4_consensus) not in ("KEEP", ""))
    )
    if hedged and ensemble_disagrees:
        return True, f"critic hedged merge ('{merge_text[:80]}...'); B3={b3v}, B4={b4_consensus}"
    return False, ""


# ---------------------------------------------------------------------------
# B4-style DeepSeek supplemental critic for genuinely-undecided classes.
# ---------------------------------------------------------------------------

SUPPL_SYSTEM = (
    "You are a rigorous universality-class critic for cross-domain dynamical "
    "systems. Apply Clauset 2009 + Stumpf-Porter 2012 standards: shared "
    "equation form + shared scaling exponents + shared critical mechanism. "
    "A previous human critic was UNDECIDED whether this class should stay "
    "independent or merge into a sibling class. Make the call. Output JSON only."
)

SUPPL_PROMPT = """A human critic reviewed this candidate universality class and KEPT it,
but was UNDECIDED about a possible merge into a sibling class. Resolve it.

Class id: {class_id}
Critic verdict: KEEP (confidence {conf})
Critic merge hesitation: {merge_text}
Critic notes: {notes}
B3 ensemble consensus: {b3}
Members claimed: {members}

Decide whether this class should remain INDEPENDENT or be MERGED into the
sibling named in the merge hesitation. Output JSON only, exact schema:
{{
  "class_id": "{class_id}",
  "decision": "INDEPENDENT" | "MERGE",
  "merge_target": "<sibling class_id, or null if INDEPENDENT>",
  "confidence": <float 0.0-1.0>,
  "rationale": "<2-3 sentences citing mechanism / exponent / equation form>"
}}
Output ONLY the JSON object."""


def extract_json(raw: str) -> dict | None:
    """Pull the first JSON object out of an LLM reply."""
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def call_deepseek_supplemental(
    class_id: str, critic_row: dict, b3_row: dict | None, members: list[str], api_key: str
) -> dict | None:
    """One DeepSeek V4 call to resolve an undecided merge. Returns parsed dict
    or None on failure (caller falls back to critic's KEEP)."""
    user = SUPPL_PROMPT.format(
        class_id=class_id,
        conf=critic_row.get("confidence", "?"),
        merge_text=(critic_row.get("merge_with") or "")[:400],
        notes=(critic_row.get("notes") or "(none)")[:400],
        b3=(b3_row or {}).get("b3_consensus", "unknown"),
        members=", ".join(members[:10]) or "(unknown)",
    )
    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": SUPPL_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    req = urllib.request.Request(
        DEEPSEEK_BASE,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = ((data["choices"][0].get("message") or {}).get("content") or "").strip()
            parsed = extract_json(content)
            if parsed and isinstance(parsed.get("decision"), str):
                log.info(
                    "  DeepSeek supplemental %s -> %s (conf %s)",
                    class_id, parsed["decision"], parsed.get("confidence"),
                )
                return parsed
            log.warning("  supplemental %s: bad JSON (attempt %d)", class_id, attempt + 1)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            log.warning("  supplemental %s: HTTP %s %s", class_id, e.code, body)
        except urllib.error.URLError as e:
            log.warning("  supplemental %s: URLError %s", class_id, e.reason)
        except Exception as e:  # noqa: BLE001 - never crash the finalize pass
            log.warning("  supplemental %s: %s", class_id, e)
        time.sleep(0.5 * (attempt + 1))
    log.warning("  supplemental %s: all retries failed, keeping critic KEEP", class_id)
    return None


# ---------------------------------------------------------------------------
# Display metadata (zh/en names, mechanism prototype, invariants) — taken from
# auto_curated where available; hand table fills the 6 extras.
# ---------------------------------------------------------------------------

EXTRA_META: dict[str, dict] = {
    "hysteresis_preisach": {
        "name_zh": "Preisach 分布滞回类",
        "name_en": "Preisach Distributed-Hysteron Class",
        "physics_prototype": "Preisach-Mayergoyz model: ensemble of independent two-state hysterons with distributed (α,β) coercivities",
        "invariants": ["∫∫ μ(α,β) hysteron density", "wiping-out property", "congruency property", "return-point memory"],
    },
    "scheffer_fold_bifurcation": {
        "name_zh": "Scheffer 折叠分岔类",
        "name_en": "Scheffer Fold-Bifurcation Class",
        "physics_prototype": "Saddle-node (fold) bifurcation in a slow variable with positive feedback giving bistability + critical slowing down",
        "invariants": ["saddle-node normal form dx/dt = r + x²", "critical slowing down (recovery rate -> 0)", "rising autocorrelation / variance as early-warning signal", "hysteresis between forward/backward tipping"],
    },
    "tail_copula_contagion": {
        "name_zh": "尾部 Copula 传染类",
        "name_en": "Tail-Copula Contagion Class",
        "physics_prototype": "Lower-tail dependence in a copula: asymptotic dependence coefficient λ_L = lim P(U<u|V<u)",
        "invariants": ["tail-dependence coefficient λ_L > 0", "correlation -> 1 in joint extremes (diversification breakdown)", "copula lower-tail asymptotics"],
    },
    "gardner_collins_toggle_switch_Th1Th2": {
        "name_zh": "Gardner-Collins 双稳拨动开关类",
        "name_en": "Gardner-Collins Toggle-Switch Class",
        "physics_prototype": "Mutual-repression / Hill-function bistable switch dS/dt = αSⁿ/(Kⁿ+Sⁿ) − βS, n>1",
        "invariants": ["Hill coefficient n>1 ultrasensitivity", "saddle-node pair bounding the bistable region", "irreversible switching above threshold"],
    },
    "schelling_credible_commitment": {
        "name_zh": "Schelling 可信承诺类",
        "name_en": "Schelling Credible-Commitment Cluster",
        "physics_prototype": "Static game-theoretic inequality: payoff(commit) > payoff(flexible) iff sunk_cost > defection_gain",
        "invariants": ["(none — static inequality, no critical exponent, no order parameter)"],
    },
    "motter_lai_network_cascade_social": {
        "name_zh": "Motter-Lai 网络级联类 (社会变体)",
        "name_en": "Motter-Lai Network Cascade (social variant)",
        "physics_prototype": "Load-redistribution cascade with capacity-bounded nodes (provenance duplicate of motter_lai_network_cascade)",
        "invariants": ["load redistribution L_i -> L_i + ΔL", "capacity bound C_i", "Eisenberg-Noe clearing vector"],
    },
    "hysteresis_first_order_transition_fertility": {
        "name_zh": "一阶相变滞回类 (低生育率陷阱)",
        "name_en": "First-Order Transition Hysteresis (fertility trap)",
        "physics_prototype": "First-order transition with double-well free energy; hysteresis loop area as order parameter",
        "invariants": ["double-well free energy", "hysteresis loop area", "fold pair / Maxwell construction"],
    },
    "gardner_collins_toggle_switch_apoptosis": {
        "name_zh": "Gardner-Collins 双稳开关类 (凋亡变体)",
        "name_en": "Gardner-Collins Toggle-Switch (apoptosis variant)",
        "physics_prototype": "Hill-function bistable switch (provenance duplicate of Th1Th2 variant)",
        "invariants": ["Hill coefficient n>1", "saddle-node pair", "irreversible switching"],
    },
}


def get_meta(class_id: str, auto_curated_by_id: dict[str, dict]) -> dict:
    """Resolve display metadata for a class_id."""
    if class_id in auto_curated_by_id:
        a = auto_curated_by_id[class_id]
        return {
            "name_zh": a.get("name_zh", class_id),
            "name_en": a.get("name_en", class_id),
            "physics_prototype": a.get("physics_prototype", ""),
            "invariants": a.get("invariants", []),
        }
    if class_id in EXTRA_META:
        return dict(EXTRA_META[class_id])
    log.warning("no metadata for %s -> using class_id as name", class_id)
    return {"name_zh": class_id, "name_en": class_id, "physics_prototype": "", "invariants": []}


# ---------------------------------------------------------------------------
# Main pipeline.
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="B1 finalize taxonomy from Layer-3 critic pass.")
    ap.add_argument("--no-llm", action="store_true", help="skip DeepSeek supplemental pass")
    args = ap.parse_args()

    load_dotenv()

    # ---- load inputs --------------------------------------------------------
    critic_rows = read_jsonl(CRITIC_IN)
    auto_curated = read_jsonl(AUTO_CURATED_IN)
    candidates = read_jsonl(CANDIDATES_IN)
    b3_rows = read_jsonl(B3_IN)
    b4_rows = read_jsonl(B4_IN)

    if not critic_rows:
        log.error("no critic verdicts loaded — cannot finalize. aborting.")
        return 1

    auto_curated_by_id = {r["class_id"]: r for r in auto_curated if r.get("class_id")}
    b3_by_id = {r["class_id"]: r for r in b3_rows if r.get("class_id")}
    hub_members = build_hub_members(candidates)

    # B4 per-class consensus (majority of the 3 reviewers)
    b4_by_id: dict[str, str] = {}
    b4_votes: dict[str, list[str]] = {}
    for r in b4_rows:
        cid = r.get("class_id")
        if cid:
            b4_votes.setdefault(cid, []).append(base_verdict(r.get("verdict", "")))
    for cid, votes in b4_votes.items():
        b4_by_id[cid] = max(set(votes), key=votes.count)

    # ---- pass 1: classify each critic verdict -------------------------------
    log.info("=== pass 1: classify %d critic verdicts ===", len(critic_rows))
    keep, split, merge, reject, undecided = [], [], [], [], []
    for row in critic_rows:
        cid = row.get("class_id")
        if not cid:
            log.warning("critic row missing class_id — skipped")
            continue
        v = base_verdict(row.get("review_verdict", ""))
        und, reason = is_undecided(row, b3_by_id.get(cid), b4_by_id.get(cid))
        if und:
            undecided.append((cid, row, reason))
        elif v == "KEEP":
            keep.append(cid)
        elif v == "SPLIT":
            split.append(cid)
        elif v == "MERGE":
            merge.append(cid)
        elif v == "REJECT":
            reject.append(cid)
        else:
            log.warning("unclassifiable verdict for %s: %r", cid, row.get("review_verdict"))
    log.info(
        "verdicts: KEEP=%d SPLIT=%d MERGE=%d REJECT=%d UNDECIDED=%d",
        len(keep), len(split), len(merge), len(reject), len(undecided),
    )

    # ---- pass 2: DeepSeek supplemental on undecided classes -----------------
    llm_decisions: dict[str, dict] = {}
    if undecided:
        if args.no_llm:
            log.info("--no-llm set: %d undecided classes default to critic KEEP", len(undecided))
        else:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                log.warning("DEEPSEEK_API_KEY not set — undecided classes default to KEEP")
            else:
                log.info("=== pass 2: DeepSeek supplemental on %d undecided ===", len(undecided))
                for cid, row, reason in undecided:
                    log.info("undecided: %s (%s)", cid, reason)
                    members = resolve_members(cid, auto_curated_by_id, hub_members)
                    res = call_deepseek_supplemental(
                        cid, row, b3_by_id.get(cid), members, api_key
                    )
                    if res:
                        llm_decisions[cid] = res

    # apply LLM decisions: INDEPENDENT -> KEEP, MERGE -> merge bucket
    for cid, row, reason in undecided:
        d = llm_decisions.get(cid)
        if d and (d.get("decision") or "").upper() == "MERGE":
            merge.append(cid)
            log.info("undecided %s -> MERGE (DeepSeek)", cid)
        else:
            keep.append(cid)
            log.info(
                "undecided %s -> KEEP (%s)",
                cid, "DeepSeek INDEPENDENT" if d else "no LLM / default",
            )

    # ---- pass 3: resolve MERGE pairs into canonical classes -----------------
    # provenance-duplicate merges: the *_apoptosis / *_social variants fold
    # into their canonical sibling. Build canonical-id mapping.
    log.info("=== pass 3: resolve merges ===")
    merge_into: dict[str, str] = {}  # variant_id -> canonical_id
    for cid in merge:
        crow = next((r for r in critic_rows if r.get("class_id") == cid), {})
        target = (crow.get("merge_with") or "").strip()
        # canonical = the simpler / seed name
        if cid == "gardner_collins_toggle_switch_apoptosis":
            merge_into[cid] = "gardner_collins_toggle_switch"
        elif cid == "gardner_collins_toggle_switch_Th1Th2":
            merge_into[cid] = "gardner_collins_toggle_switch"
        elif cid == "motter_lai_network_cascade_social":
            merge_into[cid] = "motter_lai_network_cascade"
        elif cid in llm_decisions and (llm_decisions[cid].get("merge_target")):
            merge_into[cid] = llm_decisions[cid]["merge_target"]
        else:
            # fall back: keep as own class if target unclear
            merge_into[cid] = target if target else cid
            log.warning("merge target for %s unclear -> %s", cid, merge_into[cid])

    # ---- pass 4: assemble ACTIVE classes ------------------------------------
    log.info("=== pass 4: assemble active classes ===")
    # active = KEEP classes + canonical merge targets, minus merged-away variants
    merged_away = set(merge_into.keys())
    canonical_targets = set(merge_into.values()) - merged_away
    active_ids: list[str] = []
    seen = set()
    for cid in keep + sorted(canonical_targets):
        if cid in merged_away or cid in seen:
            continue
        active_ids.append(cid)
        seen.add(cid)

    critic_by_id = {r["class_id"]: r for r in critic_rows if r.get("class_id")}

    final_rows: list[dict] = []
    total_negatives = 0
    total_fp_pruned = 0

    for cid in active_ids:
        crow = critic_by_id.get(cid, {})
        meta = get_meta(cid, auto_curated_by_id)

        # A canonical merge target (e.g. gardner_collins_toggle_switch) may have
        # no critic row of its own — inherit verdict/confidence from a merged-in
        # variant so the final record is never blank.
        if not crow:
            for variant, target in merge_into.items():
                if target == cid and critic_by_id.get(variant):
                    crow = critic_by_id[variant]
                    break

        # member list — union in any variant merged into this canonical id
        members = resolve_members(cid, auto_curated_by_id, hub_members)
        for variant, target in merge_into.items():
            if target == cid:
                vmembers = resolve_members(variant, auto_curated_by_id, hub_members)
                for m in vmembers:
                    if m not in members:
                        members.append(m)

        # collect false-positive flags from this class's critic row AND any
        # variant merged into it
        fp_flags: list[str] = list(crow.get("members_flagged_as_false_positive") or [])
        fp_reason = crow.get("members_flagged_reason", "")
        for variant, target in merge_into.items():
            if target == cid:
                vrow = critic_by_id.get(variant, {})
                fp_flags += list(vrow.get("members_flagged_as_false_positive") or [])

        clean_members = [m for m in members if m not in fp_flags]
        pruned = [m for m in members if m in fp_flags]
        total_fp_pruned += len(pruned)

        # negative-example library: curated near-miss list + pruned members
        neg_lib: list[dict] = []
        for ne in crow.get("negative_examples") or []:
            neg_lib.append({
                "type": "near_miss",
                "phenomenon": ne.get("phenomenon", ""),
                "reason": ne.get("reason", ""),
            })
        for variant, target in merge_into.items():
            if target == cid:
                vrow = critic_by_id.get(variant, {})
                for ne in vrow.get("negative_examples") or []:
                    neg_lib.append({
                        "type": "near_miss",
                        "phenomenon": ne.get("phenomenon", ""),
                        "reason": ne.get("reason", ""),
                    })
        for m in pruned:
            neg_lib.append({
                "type": "false_positive_member",
                "phenomenon": m,
                "reason": fp_reason or "flagged by Layer-3 critic as mechanism-mismatched member",
            })
        total_negatives += len(neg_lib)

        merged_variants = [v for v, t in merge_into.items() if t == cid]
        llm_note = ""
        if cid in llm_decisions:
            d = llm_decisions[cid]
            llm_note = f"DeepSeek supplemental: {d.get('decision')} (conf {d.get('confidence')}) — {d.get('rationale','')}"

        final_rows.append({
            "class_id": cid,
            "name_zh": meta["name_zh"],
            "name_en": meta["name_en"],
            "physics_prototype": meta["physics_prototype"],
            "invariants": meta["invariants"],
            # A class with merged_variants is the canonical receiver of a
            # MERGE — it stays ACTIVE, so its effective verdict is KEEP even
            # though the variant's own critic row said MERGE_WITH.
            "critic_verdict": "KEEP" if merged_variants else base_verdict(
                crow.get("review_verdict", "KEEP")),
            "critic_confidence": crow.get("confidence", ""),
            "critic_notes": crow.get("notes", ""),
            "merged_variants": merged_variants,
            "clean_members": clean_members,
            "members_pruned_false_positive": pruned,
            "negative_examples": neg_lib,
            "negative_example_count": len(neg_lib),
            "llm_supplemental": llm_note,
            "verdict_source": "B1 Layer-3 critic" + (" + DeepSeek V4 supplemental" if llm_note else ""),
        })

    # split / reject records (NOT active, but recorded for honesty)
    split_records = []
    for cid in split:
        crow = critic_by_id.get(cid, {})
        split_records.append({
            "class_id": cid,
            "outcome": "SPLIT",
            "split_suggestion": crow.get("split_suggestion", ""),
            "critic_confidence": crow.get("confidence", ""),
        })
    reject_records = []
    for cid in reject:
        crow = critic_by_id.get(cid, {})
        reject_records.append({
            "class_id": cid,
            "outcome": "REJECT",
            "reason": crow.get("members_flagged_reason", "") or crow.get("notes", ""),
            "critic_confidence": crow.get("confidence", ""),
        })

    # ---- write outputs ------------------------------------------------------
    log.info("=== writing outputs ===")
    try:
        TAXONOMY_OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(TAXONOMY_OUT, "w", encoding="utf-8") as f:
            for r in final_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log.info("wrote %d active classes -> %s", len(final_rows), TAXONOMY_OUT.name)
    except OSError as e:
        log.error("failed to write %s: %s", TAXONOMY_OUT, e)
        return 1

    try:
        write_summary(
            SUMMARY_OUT, final_rows, split_records, reject_records,
            merge_into, undecided, llm_decisions, total_negatives, total_fp_pruned,
            len(critic_rows),
        )
        log.info("wrote summary -> %s", SUMMARY_OUT.name)
    except OSError as e:
        log.error("failed to write %s: %s", SUMMARY_OUT, e)
        return 1

    # ---- console recap ------------------------------------------------------
    log.info("=" * 60)
    log.info("B1 FINALIZE DONE")
    log.info("  candidates reviewed : %d", len(critic_rows))
    log.info("  active classes      : %d", len(final_rows))
    log.info("  split (dissolved)   : %d", len(split_records))
    log.info("  rejected            : %d", len(reject_records))
    log.info("  merged-away variants: %d", len(merge_into))
    log.info("  negative-example lib: %d entries", total_negatives)
    log.info("  false-positives cut : %d members", total_fp_pruned)
    log.info("  LLM supplemental    : %d undecided -> %d resolved", len(undecided), len(llm_decisions))
    log.info("=" * 60)
    return 0


def write_summary(
    path: Path, final_rows: list[dict], split_records: list[dict],
    reject_records: list[dict], merge_into: dict[str, str],
    undecided: list[tuple], llm_decisions: dict[str, dict],
    total_negatives: int, total_fp_pruned: int, n_candidates: int,
) -> None:
    """Render the human-readable B1 wrap-up."""
    lines: list[str] = []
    lines.append("# B1 — Layer-3 Critic Pass: Final Authoritative Taxonomy")
    lines.append("")
    lines.append(f"**Date**: {time.strftime('%Y-%m-%d')}")
    lines.append(f"**Candidates reviewed**: {n_candidates}")
    lines.append(f"**Active universality classes (final)**: {len(final_rows)}")
    lines.append("")
    lines.append("## 一句话总结")
    lines.append("")
    lines.append(
        f"21 个候选普适类经 Layer-3 critic 逐条审查 + ensemble 交叉核验后，"
        f"收口为 **{len(final_rows)} 个站得住的 active 普适类**："
        f"{len(reject_records)} 个被 REJECT（统计极限定理伪装 / 博弈论概念簇，不是动力学普适类），"
        f"{len(split_records)} 个被 SPLIT（机制不纯，拆成更紧的子类），"
        f"{len(merge_into)} 个 provenance 重复变体被 MERGE 进规范类。"
        f"反例库共 {total_negatives} 条，并从成员列表剔除 {total_fp_pruned} 个 false-positive 成员。"
    )
    lines.append("")
    lines.append("## 权威性说明")
    lines.append("")
    lines.append(
        "- **权威基准 = B1 critic**（人工逐条审查，`layer3_critic.jsonl`）。"
        "本脚本只是把已有的 critic 结论固化成结构化清单，没有推翻 critic 判断。\n"
        "- B3 / B4 ensemble 是**辅助视角**。特别注意 B4 DeepSeek 用了极严苛 prompt，"
        "把几乎所有类都判 REJECT（连 scheffer / second_order_damped 这种铁打 KEEP 也 REJECT），"
        "因此 B4 **不作权威**，只用于给真正悬而未决的 merge 问题做 tie-break。\n"
        "- DeepSeek V4 补判**只对悬而未决的类调用**（critic 自己用 'possibly/could/consider/subtle' "
        "犹豫措辞、且 ensemble 又不同意），不全量重跑。"
    )
    lines.append("")
    lines.append(f"## 最终 {len(final_rows)} 个 Active 普适类")
    lines.append("")
    lines.append("| # | class_id | 中文名 | critic verdict | 干净成员 | 反例 | 来源 |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, r in enumerate(final_rows, 1):
        src = "critic+DeepSeek" if r["llm_supplemental"] else "critic"
        lines.append(
            f"| {i} | `{r['class_id']}` | {r['name_zh']} | {r['critic_verdict']} "
            f"({r['critic_confidence']}) | {len(r['clean_members'])} | "
            f"{r['negative_example_count']} | {src} |"
        )
    lines.append("")
    lines.append("### 每个 active 类为什么留下")
    lines.append("")
    for i, r in enumerate(final_rows, 1):
        lines.append(f"**{i}. {r['name_zh']}** (`{r['class_id']}`)")
        lines.append("")
        lines.append(f"- 机制原型: {r['physics_prototype'] or '(见 invariants)'}")
        if r["merged_variants"]:
            lines.append(f"- 合并了 provenance 重复变体: {', '.join(r['merged_variants'])}")
        lines.append(
            f"- 干净成员 {len(r['clean_members'])} 个"
            + (f"；剔除 false-positive {len(r['members_pruned_false_positive'])} 个: "
               f"{', '.join(r['members_pruned_false_positive'])}"
               if r["members_pruned_false_positive"] else "（无 false positive）")
        )
        lines.append(f"- 反例库 {r['negative_example_count']} 条")
        if r["llm_supplemental"]:
            lines.append(f"- {r['llm_supplemental']}")
        lines.append("")
    lines.append(f"## 被 REJECT 的 {len(reject_records)} 个候选（站不住，不进 active 清单）")
    lines.append("")
    for r in reject_records:
        lines.append(f"- **`{r['class_id']}`** (confidence {r['critic_confidence']})")
        lines.append(f"  - {r['reason'][:400]}")
    lines.append("")
    lines.append(f"## 被 SPLIT 的 {len(split_records)} 个候选（机制不纯，拆解后不作单一 active 类）")
    lines.append("")
    for r in split_records:
        lines.append(f"- **`{r['class_id']}`** (confidence {r['critic_confidence']})")
        lines.append(f"  - 拆分方案: {r['split_suggestion'][:400]}")
    lines.append("")
    merge_pairs = sorted(set(merge_into.items()))
    lines.append(f"## 被 MERGE 的 {len(merge_pairs)} 个变体（provenance 重复，并入规范类）")
    lines.append("")
    for variant, target in merge_pairs:
        lines.append(f"- `{variant}` → 并入 `{target}`")
    lines.append("")
    lines.append("## LLM 补判记录")
    lines.append("")
    if not undecided:
        lines.append("无悬而未决的类——所有 critic 结论均明确，未调用 LLM 补判。")
    else:
        lines.append(f"识别出 {len(undecided)} 个悬而未决的类（critic 犹豫 + ensemble 分歧）：")
        lines.append("")
        for cid, row, reason in undecided:
            d = llm_decisions.get(cid)
            if d:
                lines.append(
                    f"- **`{cid}`**: {reason}\n"
                    f"  - DeepSeek V4 判定: **{d.get('decision')}** "
                    f"(merge_target={d.get('merge_target')}, conf={d.get('confidence')})\n"
                    f"  - 理由: {d.get('rationale','')[:300]}"
                )
            else:
                lines.append(
                    f"- **`{cid}`**: {reason}\n"
                    f"  - 未获 LLM 判定（--no-llm 或调用失败）→ 默认沿用 critic 的 KEEP"
                )
    lines.append("")
    lines.append("## 反例库规模")
    lines.append("")
    lines.append(
        f"- 总计 **{total_negatives} 条反例**，分两类：\n"
        "  - near_miss: critic 精选的「表面像但机制不同」的近似现象\n"
        f"  - false_positive_member: 从候选成员列表中被剔除的 {total_fp_pruned} 个机制不匹配成员\n"
        "- 反例库已结构化写入 B1_final_taxonomy.jsonl 每个 active 类的 negative_examples 字段。"
    )
    lines.append("")
    lines.append("## 输出文件")
    lines.append("")
    lines.append("- `v4/results/B1_final_taxonomy.jsonl` — 每个 active 类一行（id / 中英文名 / 机制原型 / 不变量 / 干净成员 / 反例库 / verdict 来源）")
    lines.append("- `v4/results/B1_final_summary.md` — 本文件")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
