"""Fail-closed loader for the public historical-papers catalog."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit


SCHEMA_VERSION = "papers-manifest-v2"
ASSET_VERSION_RE = re.compile(r"^[0-9]{8}[a-z][0-9]+$")
SLUG_PATTERN = r"^(?!.*\.\.)(?!.*\.$)[a-z0-9][a-z0-9._-]{1,119}$"
SLUG_RE = re.compile(SLUG_PATTERN)
SOURCE_PREFIX = "/dada8899/structural-isomorphism/"
GROUP_COUNTS = {
    "unified": 1,
    "arxiv-drafts": 4,
    "phase-papers": 14,
    "tutorials": 1,
}
STATUS_COUNTS = {
    "historical-record": 14,
    "historical-draft": 5,
    "historical-tutorial": 1,
}


class PapersCatalogError(RuntimeError):
    """The public catalog cannot be trusted or served."""


@dataclass(frozen=True)
class PapersCatalog:
    """Immutable exact-match allowlist derived from the public manifest."""

    slugs: frozenset[str]
    records: Mapping[str, Mapping[str, Any]]
    manifest_path: Path

    def contains(self, slug: str) -> bool:
        return bool(isinstance(slug, str) and SLUG_RE.fullmatch(slug) and slug in self.slugs)


def _positive_integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PapersCatalogError(f"invalid positive integer: {field}")
    return value


def _required_text(value: Any, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise PapersCatalogError(f"invalid text field: {field}")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        raise PapersCatalogError(f"control character in field: {field}")
    return value.strip()


def _validate_source_url(value: Any) -> None:
    source = _required_text(value, "paper.source_url", 500)
    parsed = urlsplit(source)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(SOURCE_PREFIX)
    ):
        raise PapersCatalogError("paper source URL is outside the allowlist")


def _validate_meta(meta: Any) -> tuple[int, int, int, int]:
    if not isinstance(meta, dict):
        raise PapersCatalogError("manifest meta must be an object")
    if meta.get("schema_version") != SCHEMA_VERSION:
        raise PapersCatalogError("unsupported papers manifest schema")
    asset_version = meta.get("asset_version")
    if not isinstance(asset_version, str) or not ASSET_VERSION_RE.fullmatch(
        asset_version
    ):
        raise PapersCatalogError("invalid papers asset version")
    if meta.get("slug_pattern") != SLUG_PATTERN:
        raise PapersCatalogError("papers slug contract drift")
    contract = meta.get("result_contract")
    if not isinstance(contract, dict):
        raise PapersCatalogError("result boundary contract is missing")
    expected_contract = {
        "schema_version": "empirical-result-card-v1",
        "evidence_level": "historical_internal_record",
        "outcome_status": "not_normalized_in_current_ledger",
        "ledger_status": "not_bound",
        "review_status": "internal_only",
    }
    if any(contract.get(key) != expected for key, expected in expected_contract.items()):
        raise PapersCatalogError("result boundary contract drift")
    return (
        _positive_integer(meta.get("total_items"), "meta.total_items"),
        _positive_integer(meta.get("historical_result_records"), "meta.historical_result_records"),
        _positive_integer(meta.get("historical_research_drafts"), "meta.historical_research_drafts"),
        _positive_integer(meta.get("historical_tutorials"), "meta.historical_tutorials"),
    )


def _load_payload(manifest_path: Path) -> dict[str, Any]:
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PapersCatalogError(f"cannot read papers manifest: {manifest_path}") from exc
    if not isinstance(value, dict):
        raise PapersCatalogError("papers manifest root must be an object")
    return value


@lru_cache(maxsize=8)
def load_papers_catalog(manifest_path: str | Path) -> PapersCatalog:
    """Load, cross-check, and cache the exact public slug allowlist."""

    path = Path(manifest_path).resolve()
    payload = _load_payload(path)
    total, result_count, draft_count, tutorial_count = _validate_meta(payload.get("meta"))
    groups = payload.get("groups")
    if not isinstance(groups, list) or len(groups) != len(GROUP_COUNTS):
        raise PapersCatalogError("papers manifest group count drift")

    records: dict[str, Mapping[str, Any]] = {}
    statuses = {status: 0 for status in STATUS_COUNTS}
    for index, (expected_group, expected_count) in enumerate(GROUP_COUNTS.items()):
        group = groups[index]
        if not isinstance(group, dict) or group.get("id") != expected_group:
            raise PapersCatalogError("papers manifest group order drift")
        papers = group.get("papers")
        if not isinstance(papers, list) or len(papers) != expected_count:
            raise PapersCatalogError(f"paper group count drift: {expected_group}")
        for paper in papers:
            if not isinstance(paper, dict):
                raise PapersCatalogError("paper record must be an object")
            slug = _required_text(paper.get("slug"), "paper.slug", 120)
            if not SLUG_RE.fullmatch(slug):
                raise PapersCatalogError(f"invalid paper slug: {slug}")
            if slug in records:
                raise PapersCatalogError(f"duplicate paper slug: {slug}")
            if "external_link" in paper:
                raise PapersCatalogError("paper detail routes must be internal")
            status = paper.get("status")
            if status not in statuses:
                raise PapersCatalogError(f"invalid paper status: {status}")
            _required_text(paper.get("title_zh"), "paper.title_zh", 300)
            _required_text(paper.get("title_en"), "paper.title_en", 300)
            _validate_source_url(paper.get("source_url"))
            statuses[status] += 1
            records[slug] = MappingProxyType(dict(paper))

    expected_counts = (20, 14, 5, 1)
    if (total, result_count, draft_count, tutorial_count) != expected_counts:
        raise PapersCatalogError("papers manifest count contract drift")
    if total != result_count + draft_count + tutorial_count or len(records) != total:
        raise PapersCatalogError("papers manifest total does not reconcile")
    if statuses != STATUS_COUNTS:
        raise PapersCatalogError("papers manifest status counts do not reconcile")

    markdown_dir = path.parent / "papers"
    markdown_slugs = frozenset(item.stem for item in markdown_dir.glob("*.md") if item.is_file())
    record_slugs = frozenset(records)
    if markdown_slugs != record_slugs:
        missing = sorted(record_slugs - markdown_slugs)
        orphaned = sorted(markdown_slugs - record_slugs)
        raise PapersCatalogError(
            f"manifest/Markdown slug drift; missing={missing}, orphaned={orphaned}"
        )
    return PapersCatalog(
        slugs=record_slugs,
        records=MappingProxyType(records),
        manifest_path=path,
    )
