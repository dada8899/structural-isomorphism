#!/usr/bin/env python3
"""W13-E (session #10): build client-side Cmd+K search index.

Scans the repo for searchable content and outputs a single JSON blob to
`web/phase-detector/public/search-index.json` for the Cmd+K palette to
fetch at runtime.

Sources:
  1. Companies — `v4/product/d1_phase_detector/companies.jsonl` (100 tickers)
  2. Universality classes — `v4/taxonomy/classes/*.yaml` (~38 classes)
  3. Papers — `paper/*.md` (headings as anchors)
  4. Newsletters — `docs/community/newsletters/issue-*.md`
  5. Docs — `docs/**/*.md`

Output schema:
  [
    {
      "id":       string,
      "type":     "company" | "universality_class" | "paper" | "newsletter" | "docs",
      "title":    string,
      "subtitle": string,
      "url":      string,
      "keywords": [string],
      "weight":   float    # 0..1 — used for ranking ties
    },
    ...
  ]

The script is idempotent (deterministic ordering, stable IDs) and intended
to run on every commit via a pre-commit hook OR a build script.

Usage:
  python scripts/build_search_index.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

COMPANIES_JSONL = REPO_ROOT / "v4" / "product" / "d1_phase_detector" / "companies.jsonl"
TAXONOMY_CLASSES_DIR = REPO_ROOT / "v4" / "taxonomy" / "classes"
PAPER_DIR = REPO_ROOT / "paper"
NEWSLETTER_DIR = REPO_ROOT / "docs" / "community" / "newsletters"
DOCS_DIR = REPO_ROOT / "docs"
OUTPUT = REPO_ROOT / "web" / "phase-detector" / "public" / "search-index.json"

# Type weight — used as a tiebreaker after match score.
TYPE_WEIGHT = {
    "company": 1.0,
    "universality_class": 0.95,
    "paper": 0.85,
    "newsletter": 0.7,
    "docs": 0.6,
}

# Sector → readable label (mirrors lib/labels.ts roughly).
SECTOR_LABELS = {
    "tech_hardware": "Technology · Hardware",
    "tech_software": "Technology · Software",
    "tech_internet": "Technology · Internet",
    "tech_semiconductor": "Technology · Semiconductor",
    "tech_ai": "Technology · AI",
    "tech_ev": "Technology · EV",
    "tech_other": "Technology",
    "consumer_retail": "Consumer · Retail",
    "consumer_brand": "Consumer · Brand",
    "consumer_food": "Consumer · Food",
    "consumer_luxury": "Consumer · Luxury",
    "consumer_other": "Consumer",
    "finance_bank": "Finance · Bank",
    "finance_insurance": "Finance · Insurance",
    "finance_fintech": "Finance · Fintech",
    "finance_other": "Finance",
    "healthcare_pharma": "Healthcare · Pharma",
    "healthcare_biotech": "Healthcare · Biotech",
    "healthcare_devices": "Healthcare · Devices",
    "healthcare_other": "Healthcare",
    "energy_oil": "Energy · Oil & Gas",
    "energy_renewable": "Energy · Renewable",
    "energy_other": "Energy",
    "industrial": "Industrial",
    "materials": "Materials",
    "telecom": "Telecom",
    "utilities": "Utilities",
    "realestate": "Real Estate",
    "media": "Media",
    "transportation": "Transportation",
}


def slugify(text: str) -> str:
    """Lowercase ascii-friendly slug; preserves digits."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s\-_]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def extract_keywords(*values: str) -> list[str]:
    """Tokenize values into keyword list (deduped, lowercase, length≥2)."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if not v:
            continue
        # Split on whitespace + punctuation; keep CJK characters intact.
        tokens = re.split(r"[\s,;.\-_/()\[\]{}'\"<>!?]+", v.lower())
        for t in tokens:
            t = t.strip()
            if len(t) < 2:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
    return out


def index_companies() -> list[dict[str, Any]]:
    """Index ticker + company_name + sector."""
    if not COMPANIES_JSONL.exists():
        print(f"[warn] missing {COMPANIES_JSONL}", file=sys.stderr)
        return []
    entries: list[dict[str, Any]] = []
    with COMPANIES_JSONL.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ticker = row.get("ticker", "").strip()
            name = row.get("company_name", "").strip()
            sector = row.get("sector", "").strip()
            if not ticker:
                continue
            sector_label = SECTOR_LABELS.get(sector, sector.replace("_", " ").title())
            entries.append({
                "id": f"company-{ticker}",
                "type": "company",
                "title": f"{name} ({ticker})" if name else ticker,
                "subtitle": sector_label,
                "url": f"/company/{ticker}",
                "keywords": extract_keywords(ticker, name, sector_label),
                "weight": TYPE_WEIGHT["company"],
            })
    return entries


def index_universality_classes() -> list[dict[str, Any]]:
    """Index taxonomy class YAML files."""
    if not TAXONOMY_CLASSES_DIR.exists():
        print(f"[warn] missing {TAXONOMY_CLASSES_DIR}", file=sys.stderr)
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(TAXONOMY_CLASSES_DIR.glob("*.yaml")):
        try:
            with path.open() as fh:
                data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as e:
            print(f"[warn] yaml parse fail {path.name}: {e}", file=sys.stderr)
            continue
        class_id = data.get("class_id") or path.stem
        display_name = data.get("display_name", "").strip()
        display_name_zh = data.get("display_name_zh", "").strip()
        hub = data.get("hub_phenomenon", "").strip()
        status = data.get("status", "").strip() or "candidate"

        title = display_name or class_id
        if display_name_zh:
            subtitle = f"{display_name_zh} · status: {status}"
        else:
            subtitle = f"Universality class · status: {status}"

        # Keywords: include class_id, display name, zh name, status.
        # hub_phenomenon truncated to first 80 chars (avoid index bloat).
        hub_short = hub[:80]
        entries.append({
            "id": f"universality-{class_id}",
            "type": "universality_class",
            "title": title,
            "subtitle": subtitle,
            "url": f"/universality/{class_id}",
            "keywords": extract_keywords(
                class_id,
                display_name,
                display_name_zh,
                hub_short,
                status,
            ),
            "weight": TYPE_WEIGHT["universality_class"],
        })
    return entries


def _extract_md_title(text: str, fallback: str) -> str:
    """Return the first `# Heading` line, else fallback."""
    for line in text.splitlines()[:20]:
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _extract_md_headings(text: str, max_n: int = 6) -> list[tuple[str, str]]:
    """Return [(slug, heading)] for ## headings (skip the top-level title)."""
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+)$", line.strip())
        if not m:
            continue
        h = m.group(1).strip()
        # Strip leading numbering "1.", "2.1", etc.
        h_clean = re.sub(r"^[\d.]+\s*", "", h)
        slug = slugify(h_clean) or slugify(h)
        if slug:
            out.append((slug, h_clean))
        if len(out) >= max_n:
            break
    return out


def index_papers() -> list[dict[str, Any]]:
    """Index paper/*.md files; each top-level paper becomes 1 entry +
    1 entry per ## heading (anchor)."""
    if not PAPER_DIR.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(PAPER_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        slug = path.stem
        title = _extract_md_title(text, slug)
        # Date in filename if present: "...-2026-05-15.md"
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", slug)
        date = date_match.group(1) if date_match else ""
        subtitle = f"Paper · {date}" if date else "Paper"
        entries.append({
            "id": f"paper-{slug}",
            "type": "paper",
            "title": title,
            "subtitle": subtitle,
            "url": f"/methodology#{slug}",
            "keywords": extract_keywords(title, slug, "paper"),
            "weight": TYPE_WEIGHT["paper"],
            "date": date,
        })
        # Add up to 4 section anchors (lighter weight than paper itself).
        for hslug, heading in _extract_md_headings(text, max_n=4):
            entries.append({
                "id": f"paper-{slug}-{hslug}",
                "type": "paper",
                "title": heading,
                "subtitle": f"in: {title}",
                "url": f"/methodology#{slug}-{hslug}",
                "keywords": extract_keywords(heading, slug, "paper"),
                "weight": TYPE_WEIGHT["paper"] * 0.75,
                "date": date,
            })
    return entries


def index_newsletters() -> list[dict[str, Any]]:
    """Index docs/community/newsletters/issue-*.md."""
    if not NEWSLETTER_DIR.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(NEWSLETTER_DIR.glob("issue-*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Filename pattern: issue-001-2026-05-15.md
        m = re.match(r"^issue-(\d+)-(\d{4}-\d{2}-\d{2})$", path.stem)
        if not m:
            continue
        issue_num, date = m.group(1), m.group(2)
        title = _extract_md_title(text, f"Issue #{issue_num}")
        entries.append({
            "id": f"newsletter-{issue_num}",
            "type": "newsletter",
            "title": title,
            "subtitle": f"Newsletter · Issue #{issue_num} · {date}",
            "url": f"/newsletter/{issue_num.zfill(3)}",
            "keywords": extract_keywords(title, f"issue {issue_num}", date, "newsletter"),
            "weight": TYPE_WEIGHT["newsletter"],
            "date": date,
        })
    return entries


# Docs subtrees we exclude (machine output, drafts, internal handoffs).
_DOCS_EXCLUDE = {
    "_build",
    "arxiv-drafts",
    "sessions",
    "research-2026-05-03",
    "dogfood-ask-2026-05-15.json",
}


def index_docs() -> list[dict[str, Any]]:
    """Index docs/**/*.md (excluding community/newsletters which is its own bucket)."""
    if not DOCS_DIR.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        rel = path.relative_to(DOCS_DIR)
        # Skip newsletters (own bucket) + excluded subtrees.
        parts = rel.parts
        if parts and parts[0] == "community" and len(parts) > 1 and parts[1] == "newsletters":
            continue
        if any(p in _DOCS_EXCLUDE for p in parts):
            continue
        if rel.name.lower() == "readme.md":
            # Allow only top-level READMEs (skip nested noise).
            if len(parts) > 2:
                continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        title = _extract_md_title(text, rel.stem.replace("-", " ").title())
        slug = slugify(rel.with_suffix("").as_posix().replace("/", "-"))
        # Build a docs URL — best-effort: not all docs are statically served.
        # MkDocs convention: docs/foo/bar.md → /docs/foo/bar/
        url_path = rel.with_suffix("").as_posix()
        entries.append({
            "id": f"docs-{slug}",
            "type": "docs",
            "title": title,
            "subtitle": f"Docs · {rel.as_posix()}",
            "url": f"/docs/{url_path}",
            "keywords": extract_keywords(title, slug, "docs"),
            "weight": TYPE_WEIGHT["docs"],
        })
    return entries


def build() -> list[dict[str, Any]]:
    sections: list[tuple[str, list[dict[str, Any]]]] = [
        ("companies", index_companies()),
        ("universality_classes", index_universality_classes()),
        ("papers", index_papers()),
        ("newsletters", index_newsletters()),
        ("docs", index_docs()),
    ]
    all_entries: list[dict[str, Any]] = []
    for name, entries in sections:
        print(f"[info] {name}: {len(entries)} entries", file=sys.stderr)
        all_entries.extend(entries)
    return all_entries


def main() -> int:
    entries = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w") as fh:
        json.dump(entries, fh, ensure_ascii=False, separators=(",", ":"))
    size_kb = OUTPUT.stat().st_size / 1024
    print(
        f"[ok] wrote {len(entries)} entries to {OUTPUT.relative_to(REPO_ROOT)} "
        f"({size_kb:.1f} KB)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
