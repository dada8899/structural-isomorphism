***REMOVED***!/usr/bin/env python3
"""Send a markdown newsletter draft to Buttondown — W7-D mini-brief 3 (2026-05-24).

Pairs with `scripts/generate_weekly_signals.py`. Two modes:

    --status draft   (default): create as draft, no broadcast — human reviews in
                                 Buttondown UI before pressing send.
    --status about_to_send:     create as scheduled / about-to-send. Reserved
                                 for automated cron once we trust the pipeline.

API ref: https://docs.buttondown.email/api-emails-introduction
    POST https://api.buttondown.email/v1/emails
    Headers: Authorization: Token <BUTTONDOWN_API_KEY>
    Body:    { "subject": str, "body": str (markdown), "status": str }

Mock mode:
    If `BUTTONDOWN_API_KEY` is unset, this script logs what it WOULD have sent
    and exits 0. That makes it safe to run in CI and on dev machines.

Usage:
    python3 scripts/send_to_buttondown.py newsletter/weekly/2026-05-25.md
    python3 scripts/send_to_buttondown.py newsletter/weekly/2026-05-25.md --subject "Custom subject"
    python3 scripts/send_to_buttondown.py newsletter/weekly/2026-05-25.md --status about_to_send
    python3 scripts/send_to_buttondown.py newsletter/weekly/2026-05-25.md --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("structural.buttondown_sender")

_BUTTONDOWN_URL = "https://api.buttondown.email/v1/emails"


def _read_subject(md_text: str, fallback: str) -> str:
    """Use the first `***REMOVED*** ` heading as subject; fallback to filename stem."""
    for line in md_text.splitlines():
        line = line.strip()
        if line.startswith("***REMOVED*** "):
            return line[2:].strip()
    return fallback


def _post_buttondown(api_key: str, payload: dict) -> dict:
    """POST to Buttondown. Returns parsed JSON response. Raises on HTTP error."""
    req = urllib.request.Request(
        _BUTTONDOWN_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def send(
    md_path: Path,
    subject: Optional[str] = None,
    status: str = "draft",
    api_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Core entry point — used by `main()` and the test suite.

    Returns a result dict:
        { "ok": bool, "mode": "real"|"mock", "subject": str, "status": str,
          "response": <api response or None> }
    """
    if not md_path.exists():
        raise FileNotFoundError(md_path)

    md_text = md_path.read_text(encoding="utf-8")
    subj = subject or _read_subject(md_text, fallback=md_path.stem)

    payload = {
        "subject": subj,
        "body": md_text,
        "status": status,
    }

    if dry_run or not api_key:
        mode = "mock" if not api_key else "dry-run"
        logger.info(
            "buttondown send (%s): subject=%r status=%s bytes=%d",
            mode, subj, status, len(md_text),
        )
        return {
            "ok": True,
            "mode": mode,
            "subject": subj,
            "status": status,
            "response": None,
        }

    try:
        resp = _post_buttondown(api_key, payload)
        return {
            "ok": True,
            "mode": "real",
            "subject": subj,
            "status": status,
            "response": resp,
        }
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        logger.error("buttondown HTTP %s: %s", e.code, body)
        return {
            "ok": False,
            "mode": "real",
            "subject": subj,
            "status": status,
            "error": f"http_{e.code}",
            "detail": body,
        }
    except Exception as e:
        logger.exception("buttondown send failed: %s", e)
        return {
            "ok": False,
            "mode": "real",
            "subject": subj,
            "status": status,
            "error": str(e),
        }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Send markdown to Buttondown")
    parser.add_argument("md_path", help="Path to newsletter .md file")
    parser.add_argument("--subject", help="Override subject (default: first H1)")
    parser.add_argument(
        "--status", default="draft",
        choices=["draft", "about_to_send", "scheduled"],
        help="Buttondown email status (default: draft for human review)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't POST; just log")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    result = send(
        md_path=Path(args.md_path),
        subject=args.subject,
        status=args.status,
        api_key=os.environ.get("BUTTONDOWN_API_KEY"),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
