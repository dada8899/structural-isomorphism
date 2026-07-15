#!/usr/bin/env python3
"""Fail-closed static contract for public links and controls.

This complements browser journeys: it scans every tracked beta HTML page and
the Phase source tree so dead local links, unsafe external links, unlabeled
buttons, or retired product surfaces cannot silently return.
"""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "frontend"
PHASE = ROOT / "web" / "phase-detector"

PUBLIC_BETA_ROUTES = {
    "/", "/about", "/analyze", "/apply", "/auth/login", "/auth/verify",
    "/classes", "/diagnose",
    "/discoveries", "/insights", "/learn", "/lint", "/methods",
    "/papers", "/phenomenon", "/pricing", "/privacy", "/report", "/reports",
    "/search", "/start-here", "/stress-test", "/taxonomy-v2",
    "/thank-you", "/tools", "/whitespace",
}
DYNAMIC_BETA_PREFIXES = ("/paper/", "/phenomenon/", "/report/", "/api/")
RETIRED_PUBLIC_PREFIXES = ("/connections", "/phase/")


class ControlParser(HTMLParser):
    def __init__(self, source: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.controls: list[dict[str, str]] = []
        self.errors: list[str] = []
        self._stack: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        script_src = values.get("src") or ""
        if tag == "script" and urlsplit(script_src).hostname == "plausible.bytedance.city":
            self.errors.append(
                f"{self.source}: analytics must use the consent-gated Events API transport"
            )
        if tag in {"a", "button"}:
            record = {"tag": tag, "text": "", **{k: v or "" for k, v in values.items()}}
            self.controls.append(record)
            self._stack.append(record)
        if tag == "button" and values.get("type") not in {"button", "submit", "reset"}:
            self.errors.append(
                f"{self.source}: <button> must declare button/submit/reset type"
            )
        if tag == "a":
            self._check_link(values)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"a", "button"} and self._stack:
            record = self._stack.pop()
            label = (record.get("aria-label") or record.get("title") or record["text"]).strip()
            if not label:
                self.errors.append(f"{self.source}: unlabeled <{tag}>")

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1]["text"] += data

    def _check_link(self, attrs: dict[str, str | None]) -> None:
        href = (attrs.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            return
        parsed = urlsplit(href)
        if parsed.scheme in {"http", "https"}:
            if attrs.get("target") == "_blank" and "noopener" not in (attrs.get("rel") or ""):
                self.errors.append(f"{self.source}: target=_blank lacks noopener: {href}")
            return
        if not href.startswith("/"):
            self.errors.append(f"{self.source}: non-canonical relative link: {href}")
            return
        path = parsed.path.rstrip("/") or "/"
        if path.endswith(".html"):
            self.errors.append(f"{self.source}: legacy .html link: {href}")
            return
        if path.startswith(RETIRED_PUBLIC_PREFIXES):
            self.errors.append(f"{self.source}: retired public surface linked: {href}")
            return
        if path in PUBLIC_BETA_ROUTES or path.startswith(DYNAMIC_BETA_PREFIXES):
            return
        if path.startswith("/assets/"):
            if not (FRONTEND / path.removeprefix("/assets/")).exists():
                self.errors.append(f"{self.source}: missing asset: {href}")
            return
        self.errors.append(f"{self.source}: unknown local route: {href}")


def scan_beta() -> tuple[list[dict[str, str]], list[str]]:
    controls: list[dict[str, str]] = []
    errors: list[str] = []
    for page in sorted(FRONTEND.glob("*.html")):
        if page.name in {"404.html", "connections.html"}:
            continue
        parser = ControlParser(page.relative_to(ROOT))
        parser.feed(page.read_text(encoding="utf-8"))
        controls.extend({"file": str(page.relative_to(ROOT)), **item} for item in parser.controls)
        errors.extend(parser.errors)
    return controls, errors


def scan_phase_sources() -> list[str]:
    errors: list[str] = []
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for folder in (PHASE / "app", PHASE / "components")
        for path in folder.rglob("*.tsx")
    )
    forbidden = {
        'href="/?critical_point_state=': "legacy home screener link",
        "登录后将自动同步": "unavailable auth promise",
        "登录后可在多设备间同步": "unavailable auth promise",
        "next/font/google": "network-dependent build font",
    }
    for needle, label in forbidden.items():
        if needle in source:
            errors.append(f"Phase source contains {label}: {needle}")
    checkout = PHASE / "app" / "checkout" / "mock" / "page.tsx"
    if "redirect(" not in checkout.read_text(encoding="utf-8"):
        errors.append("legacy checkout must remain a server redirect")
    return errors


def run() -> tuple[list[dict[str, str]], list[str]]:
    controls, errors = scan_beta()
    errors.extend(scan_phase_sources())
    return controls, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", action="store_true")
    args = parser.parse_args()
    controls, errors = run()
    if args.inventory:
        print(json.dumps({"control_count": len(controls), "controls": controls}, ensure_ascii=False))
    if errors:
        print("\n".join(errors))
        return 1
    print(f"public control contract ok: {len(controls)} static beta controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
