#!/usr/bin/env python3
"""Verify that every document referenced by the static site exists."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    index = root / "site" / "index.html"
    docs = root / "site" / "docs"
    html = index.read_text(encoding="utf-8")
    tree_match = re.search(r"const DOC_TREE = \[(.*?)\n\];", html, re.DOTALL)
    tree_source = tree_match.group(1) if tree_match else ""
    slug_list = re.findall(r"slug:\s*'([^']+)'", tree_source)
    slugs = set(slug_list)
    quick_match = re.search(r"const quickItems = \[(.*?)\n  \];", html, re.DOTALL)
    quick_source = quick_match.group(1) if quick_match else ""
    quick_slugs = set(re.findall(r"slug:\s*'([^']+)'", quick_source))
    files = {path.stem for path in docs.glob("*.md")}
    missing = sorted(slugs - files)
    orphaned = sorted(files - slugs)
    duplicates = sorted(slug for slug in slugs if slug_list.count(slug) > 1)
    removed_markers = sorted(
        path.name
        for path in docs.glob("*.md")
        if "***REMOVED***" in path.read_text(encoding="utf-8")
    )

    errors: list[str] = []
    if not slugs:
        errors.append("no document slugs found in site/index.html")
    if not quick_slugs:
        errors.append("no quick-link slugs found in site/index.html")
    elif not quick_slugs <= slugs:
        errors.append("quick links absent from navigation: " + ", ".join(sorted(quick_slugs - slugs)))
    if missing:
        errors.append("missing documents: " + ", ".join(missing))
    if orphaned:
        errors.append("orphaned documents: " + ", ".join(orphaned))
    if duplicates:
        errors.append("duplicate slugs: " + ", ".join(duplicates))
    if removed_markers:
        errors.append("unrepaired scrub markers: " + ", ".join(removed_markers))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"OK: {len(slugs)} navigation slugs resolve to Markdown files")
    print(f"OK: {len(files)} Markdown files contain no scrub markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
