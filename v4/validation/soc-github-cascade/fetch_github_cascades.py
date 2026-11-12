#!/usr/bin/env python3
"""Phase 6 — fetch GitHub event-cascade data via the GitHub API (gh CLI).

PROBLEM WITH PRIOR GITHUB PILOTS
--------------------------------
`soc-github-stars` measures cumulative star counts — a preferential-attachment
GROWTH process, not a threshold cascade. `soc-github-resolution` measures
issue-resolution durations — heavy-tailed but a per-issue waiting time, again
not a cascade. Neither has the "one trigger releases a burst of derived
events that decays in time" structure that Phase 1 (earthquakes: mainshock ->
aftershock burst) requires for a true structural isomorphism.

PHASE 6 CASCADE DEFINITION (the precise object we test)
-------------------------------------------------------
Within a single repository's event stream (every issue + PR `created_at`
timestamp), a **main event** is an issue/PR whose engagement
(comments + reactions, "loudness") exceeds a per-repo threshold
mu + 2*sigma. This is the GitHub analogue of a mainshock: a hot bug report,
a security advisory, a major feature proposal — something that visibly
"shakes" the project.

The **cascade** triggered by a main event = every issue/PR opened in the
SAME repo within the [1h, 30d] window AFTER the main event. Two observables:

  1. CASCADE SIZE  s = number of derived events in that window.
     SOC prediction: P(s) ~ s^-alpha  (power-law size distribution),
     same class as earthquake aftershock-sequence sizes / DeFi liquidation
     sizes. Pre-registered band alpha in [1.5, 3.5] (wide — no established
     literature value for GitHub cascades; threshold-cascade SOC systems
     in this project's Phase 1-4 land 1.8-3.0).

  2. OMORI TIMING  the stacked delay (seconds) of each derived event after
     its main event should decay as rate(t) ~ K/(t+c)^p, p in [0.3, 1.3]
     (canonical Omori band, same as Phase 1 earthquakes / Phase 3 DeFi).

This IS structurally isomorphic to Phase 1: a localized trigger releases a
burst of correlated follow-on events whose RATE decays as a power law and
whose total SIZE is power-law distributed.

DATA SOURCE
-----------
GitHub GraphQL API via `gh api graphql`. We pull, per repo, the most recent
ISSUE_WINDOW issues and PRs with their createdAt + comments/reactions counts.
Authenticated quota is 5000 points/hour; each GraphQL page (100 nodes) costs
~1 point, so ~25 repos x ~10 pages each is well within budget.

HONESTY
-------
- Real data only in the committed result. `--self-test` builds a tiny
  synthetic stream purely to exercise the parsing/cascade logic; it never
  writes events.jsonl.
- Repo list, fetched counts and any API failures are recorded in
  fetch_log.json verbatim.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent
EVENTS_JSONL = OUT_DIR / "events.jsonl"
FETCH_LOG = OUT_DIR / "fetch_log.json"

# Curated set of large, ACTIVE OSS repos. Picked for high issue/PR throughput
# (so cascade windows actually contain derived events) and topical diversity
# (languages, infra, ML, frameworks) to avoid single-project artefacts.
# These are real repositories on github.com.
REPOS: list[str] = [
    "kubernetes/kubernetes",
    "facebook/react",
    "microsoft/vscode",
    "tensorflow/tensorflow",
    "pytorch/pytorch",
    "rust-lang/rust",
    "nodejs/node",
    "microsoft/TypeScript",
    "golang/go",
    "django/django",
    "flutter/flutter",
    "elastic/elasticsearch",
    "ansible/ansible",
    "angular/angular",
    "electron/electron",
    "vercel/next.js",
    "denoland/deno",
    "home-assistant/core",
    "grafana/grafana",
    "apache/airflow",
    "godotengine/godot",
    "ClickHouse/ClickHouse",
    "ray-project/ray",
    "huggingface/transformers",
    "n8n-io/n8n",
]

# How many of the most-recent issues+PRs to pull per repo. 100/page; we take
# up to 6 pages = 600 events/repo. 25 repos x 600 ~= 15k events total.
PAGES_PER_REPO = 6
PAGE_SIZE = 100

GQL = """
query($owner:String!, $name:String!, $issuesCursor:String, $prsCursor:String){
  repository(owner:$owner, name:$name){
    issues(first:%(ps)d, after:$issuesCursor, orderBy:{field:CREATED_AT, direction:DESC}){
      pageInfo{ hasNextPage endCursor }
      nodes{ number createdAt comments{totalCount} reactions{totalCount} }
    }
    pullRequests(first:%(ps)d, after:$prsCursor, orderBy:{field:CREATED_AT, direction:DESC}){
      pageInfo{ hasNextPage endCursor }
      nodes{ number createdAt comments{totalCount} reactions{totalCount} }
    }
  }
}
""" % {"ps": PAGE_SIZE}


def _parse_iso(ts: str) -> float:
    """ISO8601 'YYYY-MM-DDTHH:MM:SSZ' -> unix seconds (UTC)."""
    return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone


def _gh_graphql(owner: str, name: str, icur: str | None, pcur: str | None) -> dict[str, Any]:
    """One GraphQL page for a repo. Returns parsed JSON 'data' block."""
    cmd = [
        "gh", "api", "graphql",
        "-f", f"query={GQL}",
        "-F", f"owner={owner}",
        "-F", f"name={name}",
    ]
    if icur:
        cmd += ["-F", f"issuesCursor={icur}"]
    if pcur:
        cmd += ["-F", f"prsCursor={pcur}"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"gh exit {out.returncode}: {out.stderr[:300]}")
    return json.loads(out.stdout)


def fetch_repo(repo: str) -> list[dict[str, Any]]:
    """Pull recent issues+PRs for one repo. Returns event records."""
    owner, name = repo.split("/", 1)
    records: list[dict[str, Any]] = []
    icur: str | None = None
    pcur: str | None = None
    i_more = p_more = True
    for page in range(PAGES_PER_REPO):
        if not (i_more or p_more):
            break
        try:
            data = _gh_graphql(owner, name, icur if i_more else None,
                               pcur if p_more else None)
        except Exception as e:
            print(f"  {repo} page {page}: {e}", file=sys.stderr)
            break
        rep = (data.get("data") or {}).get("repository")
        if rep is None:
            print(f"  {repo}: no repository node (errors={data.get('errors')})",
                  file=sys.stderr)
            break
        for kind, key in (("issue", "issues"), ("pr", "pullRequests")):
            block = rep.get(key) or {}
            for nd in block.get("nodes") or []:
                ca = nd.get("createdAt")
                if not ca:
                    continue
                try:
                    ts = _parse_iso(ca)
                except (ValueError, TypeError):
                    continue
                records.append({
                    "repo": repo,
                    "kind": kind,
                    "number": nd.get("number"),
                    "created_at": ca,
                    "ts_unix": ts,
                    "comments": (nd.get("comments") or {}).get("totalCount", 0),
                    "reactions": (nd.get("reactions") or {}).get("totalCount", 0),
                })
            pi = block.get("pageInfo") or {}
            if key == "issues":
                i_more = bool(pi.get("hasNextPage"))
                icur = pi.get("endCursor")
            else:
                p_more = bool(pi.get("hasNextPage"))
                pcur = pi.get("endCursor")
        time.sleep(0.3)  # be polite to the API
    return records


def synth_stream(n: int = 400, seed: int = 7) -> list[dict[str, Any]]:
    """Tiny synthetic stream — ONLY for --self-test of the parsing path.

    Never written to events.jsonl. A handful of bursty 'main' events with
    Omori-like follow-on clustering, so the analyze.py logic can be smoke
    tested without burning API quota.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    base = 1_600_000_000.0
    recs: list[dict[str, Any]] = []
    t = base
    num = 0
    for _ in range(n):
        t += rng.exponential(3600.0)
        loud = rng.random() < 0.05
        recs.append({
            "repo": "synthetic/repo", "kind": "issue", "number": num,
            "created_at": "synthetic", "ts_unix": float(t),
            "comments": int(rng.integers(40, 120)) if loud else int(rng.integers(0, 5)),
            "reactions": int(rng.integers(10, 60)) if loud else 0,
        })
        num += 1
        if loud:  # inject an Omori-decaying aftershock burst
            for k in range(int(rng.integers(5, 30))):
                dt = (k + 1) ** 1.4 * rng.exponential(1800.0)
                recs.append({
                    "repo": "synthetic/repo", "kind": "issue", "number": num,
                    "created_at": "synthetic", "ts_unix": float(t + dt),
                    "comments": int(rng.integers(0, 4)), "reactions": 0,
                })
                num += 1
    recs.sort(key=lambda r: r["ts_unix"])
    return recs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true",
                    help="exercise parsing on synthetic data, write nothing")
    args = ap.parse_args()

    if args.self_test:
        recs = synth_stream()
        print(f"[self-test] {len(recs)} synthetic events (NOT written)")
        return

    log: dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "github GraphQL api (gh api graphql)",
        "repos_requested": REPOS,
        "pages_per_repo": PAGES_PER_REPO,
        "page_size": PAGE_SIZE,
        "per_repo_counts": {},
        "failures": [],
    }
    all_records: list[dict[str, Any]] = []
    for i, repo in enumerate(REPOS, 1):
        print(f"[{i}/{len(REPOS)}] fetching {repo} ...", file=sys.stderr, flush=True)
        try:
            recs = fetch_repo(repo)
        except Exception as e:
            print(f"  FAILED {repo}: {e}", file=sys.stderr)
            log["failures"].append({"repo": repo, "error": str(e)})
            recs = []
        log["per_repo_counts"][repo] = len(recs)
        print(f"  {repo}: {len(recs)} events", file=sys.stderr, flush=True)
        all_records.extend(recs)
        # checkpoint after every repo so a mid-run crash keeps progress
        with EVENTS_JSONL.open("w") as f:
            for r in all_records:
                f.write(json.dumps(r) + "\n")

    log["n_events_total"] = len(all_records)
    log["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with FETCH_LOG.open("w") as f:
        json.dump(log, f, indent=2)
    print(f"wrote {len(all_records)} events -> {EVENTS_JSONL}", file=sys.stderr)


if __name__ == "__main__":
    main()
