#!/usr/bin/env python3
"""Session #16 — Single-shot prod fingerprint check.

The session #15 incident: prod was running stale code for 5 days while local
TTFT measurements LOOKED fine because they implicitly hit local. Root cause:
no single endpoint exposed "what model is the running code actually about
to call?". Now `/api/version` returns `model` + `git_sha` + `deployed_at`,
so the fingerprint check is one HTTP GET.

Usage:
    python3 scripts/dogfood_fingerprint.py \
        [--host https://beta.structural.bytedance.city] \
        [--expect-model deepseek/deepseek-chat:nitro] \
        [--expect-sha-startswith 4125b6a]

Exit code 0 = all expectations matched. Exit code != 0 = mismatch, run dogfood
nothing else until prod is verified to match the local source of truth.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_HOST = "https://beta.structural.bytedance.city"


def _local_git_sha() -> str:
    """Short SHA of the most recent commit that touched *deployable* code.

    Deploy never ships docs-only commits, so comparing prod's git_sha
    against a docs-only local HEAD raised false 'FINGERPRINT MISMATCH'
    alarms (session #17). Exclude docs/ and top-level *.md so the
    fingerprint tracks shippable state, not documentation churn.
    """
    try:
        return subprocess.check_output(
            ["git", "log", "-1", "--format=%h",
             "--", ".", ":(exclude)docs", ":(exclude)*.md"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
    except Exception:
        return ""


def fetch_version(host: str, timeout: float = 5.0) -> dict:
    url = host.rstrip("/") + "/api/version"
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--expect-model", default="deepseek/deepseek-chat:nitro",
                   help="Model the running code should be about to call.")
    p.add_argument(
        "--expect-sha-startswith",
        default=_local_git_sha(),
        help="Local short SHA — defaults to `git rev-parse --short=7 HEAD`."
             " Mismatch == prod is on a different commit than your tree.",
    )
    p.add_argument("--json", action="store_true",
                   help="Emit the raw /api/version JSON and exit 0 on fetch success.")
    args = p.parse_args()

    try:
        body = fetch_version(args.host)
    except URLError as e:
        print(f"❌ /api/version unreachable at {args.host}: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(body, indent=2))
        return 0

    failed = []
    # Model check — the most important one (session-15 root cause).
    if args.expect_model and body.get("model") != args.expect_model:
        failed.append(
            f"model mismatch: prod={body.get('model')!r} expected={args.expect_model!r}"
        )
    # SHA check — if user passed --expect-sha-startswith="" we skip silently.
    if args.expect_sha_startswith:
        sha = body.get("git_sha", "")
        if not sha.startswith(args.expect_sha_startswith):
            failed.append(
                f"git_sha mismatch: prod={sha!r} expected starts-with={args.expect_sha_startswith!r}"
            )
    else:
        # Validator session-#16 P2 — silent empty default can mask real
        # drift. Emit a stderr warning rather than appearing to verify SHA.
        print(
            "⚠ no --expect-sha-startswith supplied and `git rev-parse` returned "
            "nothing; git_sha was NOT verified.",
            file=sys.stderr,
        )

    print(f"host:         {args.host}")
    print(f"semver:       {body.get('semver')}")
    print(f"git_sha:      {body.get('git_sha')}")
    print(f"model:        {body.get('model')}")
    print(f"env:          {body.get('env')}")
    print(f"deployed_at:  {body.get('deployed_at')}")
    print(f"build_date:   {body.get('build_date')}")

    if failed:
        print("\n❌ FINGERPRINT MISMATCH")
        for f in failed:
            print(f"  - {f}")
        print("\nDo NOT trust dogfood numbers until prod matches local source of truth.")
        return 1

    print("\n✅ fingerprint OK — prod matches expectations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
