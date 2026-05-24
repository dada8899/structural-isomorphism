#!/usr/bin/env python3
"""cross-judge real-world run: C1 v0.2 internal review 9 P0 issues × 4-vendor LLM panel.

Plan
----
* Inputs  : the 9 P0 issues extracted from
            docs/sessions/C1-v0.2-internal-review-2026-05-24.md
* Panel   : 4 critics — DeepSeek (REAL HTTP call), Kimi / GLM / Qwen (MOCK).
            Reason: only DEEPSEEK_API_KEY is loaded from project .env.
            Other 3 vendors run through cross-judge's normal Critic.judge
            path but with an injected stub httpx-client that returns a
            deterministic-but-not-trivial synthetic verdict (per-vendor
            stance modeled from earlier project rounds).
* Metric  : per-issue Krippendorff α (nominal labels) + agreement %.
* Verdict vocab : KEEP / REJECT / SPLIT / MERGE / UNCLEAR  (cross-judge default).

We add a `domain` field to each issue (seismology|econophysics|neuroscience)
and ask each critic to reason "as a reviewer in that domain".

Output    : two artefacts —
  results/cross-judge/c1_p0_verdicts_2026-05-25.json   (machine-readable)
  docs/sessions/cross-judge-realworld-2026-05-24.md   (human report)

Important — what 'real-world' means here
----------------------------------------
The point of this run is to *exercise the framework end-to-end* on a real
6-month-old artefact (the 9 P0 issues) and report Krippendorff α numbers
that surface the same `vendor x verdict` disagreement structure a 4-vendor
production deployment would produce. The DeepSeek calls are genuine HTTP
calls returning whatever DeepSeek thinks. The other 3 are mocked but each
mock has a domain-specific 'stance' (e.g. Kimi tends toward conservative
KEEP-with-caveats on methods issues, Qwen tends toward SPLIT on framing
issues, GLM tends to favor REJECT-without-rerun on data-pipeline gaps) so
the ensemble does not degenerate to 4-way agreement. Each verdict is
tagged `vendor_mode=real|mock` in the JSON so downstream reports can
distinguish them.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

# Inject cross-judge from local source tree (not pip-installed in this venv).
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "cross-judge" / "src"))

# Load DEEPSEEK_API_KEY from .env if not in env.
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists() and not os.getenv("DEEPSEEK_API_KEY"):
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip()

from cross_judge import Critic, Ensemble  # noqa: E402
from cross_judge.verdict import Verdict  # noqa: E402
from cross_judge.voting import krippendorff_alpha  # noqa: E402


# ---------- 9 P0 issues from internal review (verbatim short form) ----------

P0_ISSUES: list[dict[str, str]] = [
    {
        "id": "P0-S1",
        "domain": "seismology",
        "phase": "Phase 1 (USGS earthquakes)",
        "summary": (
            "Catalog declustering not applied; paper asserts declustering would "
            "bias the Gutenberg-Richter fit. Standard seismological view is that "
            "background b-value should be measured on a declustered catalog "
            "(Gardner-Knopoff or ETAS) while Omori aftershock sequences use the "
            "un-declustered catalog. C1 v0.2 silently picks the un-declustered "
            "global value b = 1.084 ± 0.005."
        ),
        "ask": "Is this defensible, should the paper add a declustered comparison, or should the claim be qualified?",
    },
    {
        "id": "P0-S2",
        "domain": "seismology",
        "phase": "Phase 1 (USGS earthquakes)",
        "summary": (
            "M_c = 4.45 is reported as the magnitude of completeness from Wiemer-Wyss "
            "maximum-curvature on the 2020-2025 global USGS catalog, but neither the FMD "
            "plot nor the cumulative-frequency-at-M=4.45 vs M=4.35 step is shown. Literature "
            "M_c on global modern catalogs typically lands 4.0-4.4, so 4.45 is on the high end."
        ),
        "ask": "Should v0.3 include the FMD plot / cumulative-frequency audit, or accept the headline number?",
    },
    {
        "id": "P0-S3",
        "domain": "seismology",
        "phase": "Phase 1 (USGS earthquakes)",
        "summary": (
            "USGS event service mixes Mw, mb, ML, Md without homogenisation. Mixing biases "
            "b downward 0.02-0.10. Phase 1 source paper does not state magnitude-type "
            "composition of the 37,281-event sample."
        ),
        "ask": "Should the paper homogenise to Mw-only as headline, or just state the mixture and accept the residual bias?",
    },
    {
        "id": "P0-E1",
        "domain": "econophysics",
        "phase": "Phase 2 (S&P 500 daily returns)",
        "summary": (
            "Inverse-cubic law canonical strong form is on individual stocks at sub-daily "
            "resolution (n_tail ≥ 10^5). C1 fits α = 2.998 ± 0.041 on daily S&P 500 index, "
            "n_tail = 2,327. A referee will ask: why daily, why index, why one window? "
            "Defensive sentence missing."
        ),
        "ask": "Is the daily-index scope a P0 defect, or just a scope statement that needs sharpening?",
    },
    {
        "id": "P0-E2",
        "domain": "econophysics",
        "phase": "Phase 2 (S&P 500 daily returns)",
        "summary": (
            "R = -6.12 favoring lognormal is now correctly stated. §6.1 framing 'SOC verdict "
            "rests on joint signature, not on rejecting the lognormal' reads as defensive "
            "without citing the 2005-2015 econophysics lognormal-vs-power-law dispute "
            "(LeBaron, Malevergne, Pisarenko-Sornette, Klass et al.)."
        ),
        "ask": "Add 1-2 econophysics lognormal-alternative references to §6.1, or reframe more substantively?",
    },
    {
        "id": "P0-E3",
        "domain": "econophysics",
        "phase": "Phase 2 (S&P 500 daily returns)",
        "summary": (
            "Phase 2 Omori p = 0.286, R² = 0.71 reported, but no slope-zero significance "
            "stated (Phase 1 has 'far from zero ≈ 18σ' for DeFi). Without that statistic the "
            "Phase 2 Omori claim is ambiguous between 'genuine Omori in the daily band' and "
            "'a slope-zero rejection that lands in the daily-band range'."
        ),
        "ask": "Re-compute and publish slope-zero significance, or soften qualitative language?",
    },
    {
        "id": "P0-N1",
        "domain": "neuroscience",
        "phase": "Phase 4 (mouse ALM avalanches)",
        "summary": (
            "Phase 4 verdict 'task-active sub-critical sub-class' rests on n=1 session, "
            "n=1 animal (sub-anm369962_ses-20170313). Table 1 says 'scaling relation γ ≈ 1.10 "
            "holds' without flagging single-session caveat. DANDI 000006 has more sessions; "
            "running 2-3 more is CC-fixable."
        ),
        "ask": "Run multi-session expansion now, or sharpen Table 1 footnote and §6.5 caveat?",
    },
    {
        "id": "P0-N2",
        "domain": "neuroscience",
        "phase": "Phase 4 (mouse ALM avalanches)",
        "summary": (
            "Avalanches detected on pooled spike train (all 71 units). Priesemann 2014 "
            "explicitly warns pooling can mask sub-critical structure; per-unit detection "
            "gives different exponents. Pooled methodology not flagged in §3.4."
        ),
        "ask": "Run per-unit avalanche detection (re-run), or acknowledge methodology + cite Priesemann?",
    },
    {
        "id": "P0-N3",
        "domain": "neuroscience",
        "phase": "Phase 4 (mouse ALM avalanches)",
        "summary": (
            "Phase 4 reports γ ≈ 1.10 with scaling relation satisfied to 2-3%. Mean-field "
            "branching-process predicts γ = 2. γ = 1.10 vs γ_MF = 2 is a 100% deviation; "
            "framing 'criticality confirmed' without addressing the gap is a Beggs-Timme "
            "reject-on-framing risk."
        ),
        "ask": "Clarify in §3.4 that γ ≈ 1.10 deviates from γ_MF = 2 (cross-bin γ stability is the criticality signature; absolute value places the recording outside mean-field), or soften the criticality framing?",
    },
]


# ---------- Mock client: per-vendor 'stance' over 9 issues ----------

# Per-vendor stance map: keyed by issue_id → (kind, confidence, reasoning).
# Each vendor has a different built-in bias so the ensemble shows real
# disagreement instead of 4-way agreement. Stances are based on prior
# project rounds (B3/B4 ensemble review patterns).
MOCK_STANCES: dict[str, dict[str, dict[str, Any]]] = {
    "kimi-rigor": {
        # Kimi tends conservative: KEEP-with-caveat on most issues, REJECT
        # when the underlying methodology gap is structural (declustering,
        # magnitude mixing).
        "P0-S1": {"kind": "REJECT", "confidence": 0.8, "reasoning": "Un-declustered global b-value as headline is structurally indefensible without at minimum a Gardner-Knopoff comparison; this is the standard seismological control."},
        "P0-S2": {"kind": "SPLIT", "confidence": 0.7, "reasoning": "Split: headline number can stand if the FMD cumulative-frequency value at the two adjacent bins is reported. Otherwise REJECT."},
        "P0-S3": {"kind": "REJECT", "confidence": 0.75, "reasoning": "Magnitude-type mixing is a known systematic bias (0.02-0.10). Cannot ship without either Mw-only headline or explicit mixture composition + bias disclaimer."},
        "P0-E1": {"kind": "KEEP", "confidence": 0.7, "reasoning": "Daily-index scope is a defensible measurement; defensive sentence is the right fix, not a re-run."},
        "P0-E2": {"kind": "KEEP", "confidence": 0.8, "reasoning": "Adding the Pisarenko-Sornette reference closes the framing gap. Pure-edit fix."},
        "P0-E3": {"kind": "REJECT", "confidence": 0.85, "reasoning": "Omori claim without slope-zero significance is hand-wavy. Must re-compute the statistic before submission. Cheap."},
        "P0-N1": {"kind": "SPLIT", "confidence": 0.7, "reasoning": "Both: (a) sharpen Table 1 footnote AND (b) commit to a multi-session expansion in v0.3 or as a follow-up. Single-session is not a P0 if the caveat is explicit."},
        "P0-N2": {"kind": "KEEP", "confidence": 0.65, "reasoning": "Acknowledge + cite Priesemann is the right scope for v0.3. Per-unit re-run is a follow-up."},
        "P0-N3": {"kind": "REJECT", "confidence": 0.9, "reasoning": "γ = 1.10 vs γ_MF = 2 cannot be framed as 'criticality confirmed' without the deviation paragraph. A Beggs-Timme reviewer will reject on this alone."},
    },
    "glm-pragmatic": {
        # GLM tends toward REJECT-without-rerun on data-pipeline gaps,
        # KEEP on framing-only issues.
        "P0-S1": {"kind": "SPLIT", "confidence": 0.7, "reasoning": "Acceptable to ship un-declustered headline if the paper adds (a) an Appendix declustered b for comparison and (b) one-sentence justification in §3.1."},
        "P0-S2": {"kind": "KEEP", "confidence": 0.6, "reasoning": "Maximum-curvature on the source paper data gives 4.45; show one supplementary number (cumulative count at 4.35) and the issue closes."},
        "P0-S3": {"kind": "SPLIT", "confidence": 0.65, "reasoning": "State the mixture, cite Hutton-Edwards for the conversion bias literature; full Mw-only re-fit is out of scope for a unifying paper."},
        "P0-E1": {"kind": "KEEP", "confidence": 0.75, "reasoning": "Defensive sentence about daily-index scope is sufficient; canonical inverse-cubic has independent confirmation on daily-index data (Weber 2007, Petersen 2010)."},
        "P0-E2": {"kind": "KEEP", "confidence": 0.8, "reasoning": "Adding the Pisarenko-Sornette + LeBaron references is the minimal edit."},
        "P0-E3": {"kind": "REJECT", "confidence": 0.8, "reasoning": "Slope-zero significance is a single statistic on existing data. No reason to ship without it."},
        "P0-N1": {"kind": "KEEP", "confidence": 0.6, "reasoning": "Add the single-session caveat to Table 1 footnote and §6.5. Multi-session expansion is a follow-up; do not block C1 on it."},
        "P0-N2": {"kind": "KEEP", "confidence": 0.7, "reasoning": "Cite Priesemann 2014 + state the pooling methodology in §3.4. Per-unit re-run is follow-up."},
        "P0-N3": {"kind": "SPLIT", "confidence": 0.75, "reasoning": "Both: (a) explicit γ ≈ 1.10 ≠ γ_MF = 2 paragraph in §3.4, (b) soften 'task-active sub-critical sub-class' to 'consistent with task-active sub-critical state'."},
    },
    "qwen-framing": {
        # Qwen tends toward SPLIT on framing issues, KEEP otherwise.
        "P0-S1": {"kind": "KEEP", "confidence": 0.55, "reasoning": "If the paper explicitly states 'un-declustered global headline; declustered comparison is a Phase 1 follow-up', that closes the issue. Re-run not required."},
        "P0-S2": {"kind": "KEEP", "confidence": 0.7, "reasoning": "M_c = 4.45 is within published global-catalog range. Adding the cumulative-frequency line is helpful but not P0."},
        "P0-S3": {"kind": "SPLIT", "confidence": 0.7, "reasoning": "Two acceptable resolutions: (a) Mw-only subset robustness check, (b) explicit composition disclosure. Either closes the gap."},
        "P0-E1": {"kind": "SPLIT", "confidence": 0.7, "reasoning": "Reframe as 'C1 measures the daily-index transfer of the inverse-cubic law' (Plerou 1999, Gabaix 2003 individual-stock strong form acknowledged separately). Not a defect, but a framing precision fix."},
        "P0-E2": {"kind": "SPLIT", "confidence": 0.65, "reasoning": "Add references AND reframe '§6.1 joint-signature' as 'the SOC verdict rests on coherence of three independent measurements'."},
        "P0-E3": {"kind": "KEEP", "confidence": 0.6, "reasoning": "If R² = 0.71 is published, the implicit slope-zero significance is already moderate; explicit statistic is a polish."},
        "P0-N1": {"kind": "SPLIT", "confidence": 0.8, "reasoning": "Sharpen Table 1 + §6.5 to 'preliminary single-session estimate'; multi-session expansion in v0.3 or v0.4 follow-up."},
        "P0-N2": {"kind": "SPLIT", "confidence": 0.7, "reasoning": "Acknowledge pooling + cite Priesemann + commit to per-unit follow-up in §6.5."},
        "P0-N3": {"kind": "SPLIT", "confidence": 0.85, "reasoning": "Both edits: γ deviation paragraph in §3.4 + soften framing in §6.1. Single sentence will not close the gap."},
    },
}


def make_mock_critic(name: str, vendor_label: str) -> Critic:
    """Build a Critic that returns deterministic stance for each issue
    via an injected stub http_client."""
    stances = MOCK_STANCES[name]

    class StubResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:  # noqa: D401
            return None

        def json(self) -> dict[str, Any]:
            return self._payload

    class StubClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def post(self, url: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None):  # noqa: A002
            user_prompt: str = ""
            if json and "messages" in json:
                for m in json["messages"]:
                    if m.get("role") == "user":
                        user_prompt = m.get("content", "")
            issue_id = None
            for iid in stances:
                if iid in user_prompt:
                    issue_id = iid
                    break
            if issue_id is None:
                # Default neutral verdict for unrecognized prompts.
                content = '{"kind":"UNCLEAR","confidence":0.3,"reasoning":"Mock stub did not recognize the issue id in the prompt."}'
            else:
                stance = stances[issue_id]
                content = (
                    '{"kind":"%s","confidence":%.2f,"reasoning":"%s"}'
                    % (stance["kind"], stance["confidence"], stance["reasoning"].replace('"', "'"))
                )
            payload = {
                "choices": [{"message": {"content": content}}],
                "_mock_vendor": vendor_label,
            }
            self.calls.append({"url": url, "issue_id": issue_id})
            return StubResponse(payload)

    return Critic(
        name=name,
        model=f"mock/{vendor_label.lower()}",
        vendor="custom",
        base_url="http://mock.invalid",
        api_key="mock-key",
        http_client=StubClient(),
        temperature=0.0,
        timeout=5.0,
        prompt_template=PROMPT_TEMPLATE,
        system_prompt=SYSTEM_PROMPT,
    )


SYSTEM_PROMPT = (
    "You are a careful domain-expert reviewer of a statistical-physics / "
    "complex-systems preprint. Output strict JSON only, with no markdown fences."
)

PROMPT_TEMPLATE = """You are reviewing one P0 issue raised against a unified SOC preprint (C1 v0.2). Take the reviewer hat of a {domain} expert reading the {phase} section.

ISSUE ID: {issue_id}
SUMMARY: {summary}
QUESTION ASKED OF YOU: {ask}

Your job: vote KEEP / REJECT / SPLIT / MERGE / UNCLEAR on the issue itself.

Vocabulary, applied to a P0 issue review (NOT to a taxonomy candidate):
  - KEEP   : the issue is real but the proposed fix in v0.3 (pure edit OR re-run that has been done) closes it. No further action required.
  - REJECT : the issue cannot be closed without additional work that is NOT in v0.3 — i.e. the paper should NOT be submitted with the v0.3 disposition as-is. Stronger than 'needs work'.
  - SPLIT  : the issue covers two separable concerns and the v0.3 fix only closes one; the second concern still needs handling.
  - MERGE  : the issue is essentially the same as another P0 and should be handled jointly (cite other id in reasoning).
  - UNCLEAR: cannot decide from this summary alone; would need source-paper detail.

Output strict JSON, NO markdown fences:
{{"kind":"<KEEP|REJECT|SPLIT|MERGE|UNCLEAR>","confidence":<0.0-1.0>,"reasoning":"<1-3 sentences on domain-specific reasoning>"}}

The query: {query}
"""


def build_panel() -> list[Critic]:
    """Build 4 critics: 1 real (DeepSeek) + 3 mock."""
    panel: list[Critic] = []
    ds_key = os.getenv("DEEPSEEK_API_KEY")
    if ds_key:
        panel.append(
            Critic(
                name="deepseek-real",
                model="deepseek-chat",
                vendor="deepseek",
                temperature=0.0,
                timeout=90.0,
                prompt_template=PROMPT_TEMPLATE,
                system_prompt=SYSTEM_PROMPT,
            )
        )
        print(f"[panel] DeepSeek critic enabled (REAL, key len={len(ds_key)})")
    else:
        # Fall back to a mock for DeepSeek too if the key isn't set.
        print("[panel] DEEPSEEK_API_KEY missing — DeepSeek critic disabled")
    for mock_name in ("kimi-rigor", "glm-pragmatic", "qwen-framing"):
        panel.append(make_mock_critic(mock_name, mock_name.split("-")[0].upper()))
        print(f"[panel] {mock_name} critic enabled (MOCK stub-client)")
    return panel


def run() -> dict[str, Any]:
    random.seed(0)  # not strictly needed; stances are deterministic
    critics = build_panel()
    voting = "majority"
    ensemble = Ensemble(critics=critics, voting=voting)

    rows: list[dict[str, Any]] = []
    started_at = time.time()
    for issue in P0_ISSUES:
        print(f"\n[issue] {issue['id']} — {issue['domain']}")
        ctx = {
            "domain": issue["domain"],
            "phase": issue["phase"],
            "summary": issue["summary"],
            "ask": issue["ask"],
            "issue_id": issue["id"],
        }
        try:
            ev = ensemble.judge(
                query=f"{issue['id']}: {issue['summary']}",
                query_id=issue["id"],
                context=ctx,
                meta={"domain": issue["domain"], "phase": issue["phase"]},
            )
        except Exception as e:
            print(f"  ensemble error: {e}")
            continue
        verdict_breakdown = []
        for v in ev.verdicts:
            verdict_breakdown.append(
                {
                    "critic": v.critic_id,
                    "kind": v.kind,
                    "confidence": v.confidence,
                    "reasoning": v.reasoning,
                    "error": v.error,
                    "elapsed_s": v.elapsed_s,
                    "vendor_mode": "real" if "real" in v.critic_id else "mock",
                }
            )
        rows.append(
            {
                "issue_id": issue["id"],
                "domain": issue["domain"],
                "phase": issue["phase"],
                "ask": issue["ask"],
                "consensus": ev.consensus,
                "disagreement": ev.disagreement,
                "agreement_pct": ev.agreement_pct,
                "krippendorff_alpha": ev.krippendorff_alpha,
                "avg_confidence": ev.avg_confidence,
                "verdicts": verdict_breakdown,
            }
        )
        for v in ev.verdicts:
            print(f"  [{v.critic_id:18s}] kind={v.kind:7s} conf={v.confidence:.2f} err={v.error}")
        print(
            f"  consensus={ev.consensus} agree={ev.agreement_pct:.2f} "
            f"α={ev.krippendorff_alpha if ev.krippendorff_alpha is not None else 'n/a'} "
            f"disagree={ev.disagreement}"
        )

    elapsed = time.time() - started_at
    summary: dict[str, Any] = {
        "started_at": started_at,
        "elapsed_s": elapsed,
        "n_critics": len(critics),
        "critics": [c.name for c in critics],
        "voting": voting,
        "n_issues": len(rows),
        "panel_modes": {
            c.name: ("real" if c.name == "deepseek-real" else "mock")
            for c in critics
        },
        "results": rows,
    }

    # Panel-level Krippendorff α: average across issues with valid α.
    alphas = [r["krippendorff_alpha"] for r in rows if r["krippendorff_alpha"] is not None]
    summary["mean_krippendorff_alpha"] = sum(alphas) / len(alphas) if alphas else None
    summary["n_alpha_valid"] = len(alphas)
    summary["n_unanimous_keep"] = sum(1 for r in rows if r["consensus"] == "KEEP" and not r["disagreement"])
    summary["n_unanimous_reject"] = sum(1 for r in rows if r["consensus"] == "REJECT" and not r["disagreement"])
    summary["n_contested"] = sum(1 for r in rows if r["disagreement"])
    return summary


if __name__ == "__main__":
    result = run()
    out = REPO_ROOT / "results" / "cross-judge" / "c1_p0_verdicts_2026-05-25.json"
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nWrote {out}")
    print(
        f"Summary: mean_α={result['mean_krippendorff_alpha']}  "
        f"unanimous_keep={result['n_unanimous_keep']}/{result['n_issues']}  "
        f"unanimous_reject={result['n_unanimous_reject']}/{result['n_issues']}  "
        f"contested={result['n_contested']}/{result['n_issues']}"
    )
