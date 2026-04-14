"""Merge all companies_opus_*.jsonl into companies_struct.jsonl with dedup + phase normalization."""
import json
from pathlib import Path
from collections import Counter

DATA = Path(__file__).parent.parent / "data"

CANONICAL_PHASE = {
    "stable", "saturated", "approaching_critical",
    "growth_phase", "post_transition", "unstable", "contracting",
}

PHASE_ALIASES = {
    "growth": "growth_phase",
    "growing": "growth_phase",
    "early_growth": "growth_phase",
    "late_growth": "growth_phase",
    "expansion": "growth_phase",
    "mature": "saturated",
    "saturation": "saturated",
    "saturated_mature": "saturated",
    "near_critical": "approaching_critical",
    "critical": "approaching_critical",
    "pre_transition": "approaching_critical",
    "post_critical": "post_transition",
    "post-transition": "post_transition",
    "declining": "contracting",
    "decline": "contracting",
    "shrinking": "contracting",
    "unstable_oscillation": "unstable",
    "chaotic": "unstable",
    "equilibrium": "stable",
    "steady_state": "stable",
}


def normalize_phase(p):
    if not p:
        return "stable"
    p = p.strip().lower().replace(" ", "_")
    if p in CANONICAL_PHASE:
        return p
    return PHASE_ALIASES.get(p, "stable")


def main():
    by_ticker = {}
    chunk_files = sorted(DATA.glob("companies_opus_*.jsonl"),
                         key=lambda f: int(f.stem.split("_")[-1]))
    print(f"Merging {len(chunk_files)} chunks...")

    for f in chunk_files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("_error"):
                    continue
                tk = d.get("ticker")
                if not tk:
                    continue
                d["phase_state"] = normalize_phase(d.get("phase_state"))
                if tk not in by_ticker:
                    by_ticker[tk] = d

    out = DATA / "companies_struct.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for tk in sorted(by_ticker.keys()):
            fh.write(json.dumps(by_ticker[tk], ensure_ascii=False) + "\n")

    families = Counter(d.get("dynamics_family") for d in by_ticker.values())
    phases = Counter(d.get("phase_state") for d in by_ticker.values())
    print(f"Wrote {len(by_ticker)} unique companies → {out.name}")
    print(f"\nDynamics families ({len(families)}):")
    for fam, n in families.most_common():
        print(f"  {n:3d}  {fam}")
    print(f"\nPhase states ({len(phases)}):")
    for p, n in phases.most_common():
        print(f"  {n:3d}  {p}")


if __name__ == "__main__":
    main()
