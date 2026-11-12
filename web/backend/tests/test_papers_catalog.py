from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent.parent
MANIFEST = ROOT / "web" / "frontend" / "assets" / "data" / "papers-manifest.json"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def test_backend_catalog_uses_the_frontend_manifest_as_its_only_slug_allowlist() -> None:
    from services.papers_catalog import load_papers_catalog

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {
        paper["slug"]
        for group in manifest["groups"]
        for paper in group["papers"]
    }
    catalog = load_papers_catalog(MANIFEST)

    assert catalog.slugs == frozenset(expected)
    assert len(catalog.slugs) == 20
    assert "unified-pipeline-v0.2-2026-05-13" in catalog.slugs


@pytest.mark.parametrize(
    "slug",
    [
        "",
        ".hidden",
        "../soc-earthquake-2026-04-15",
        "soc..earthquake",
        "soc-earthquake-2026-04-15/extra",
        "SOC-earthquake-2026-04-15",
        "not-a-real-paper",
    ],
)
def test_backend_catalog_rejects_noncanonical_or_unknown_slugs(slug: str) -> None:
    from services.papers_catalog import load_papers_catalog

    assert load_papers_catalog(MANIFEST).contains(slug) is False


def test_backend_catalog_fails_closed_on_duplicate_or_missing_markdown(tmp_path: Path) -> None:
    from services.papers_catalog import PapersCatalogError, load_papers_catalog

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["groups"][1]["papers"][0]["slug"] = payload["groups"][0]["papers"][0]["slug"]
    bad_manifest = tmp_path / "papers-manifest.json"
    bad_manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PapersCatalogError, match="duplicate"):
        load_papers_catalog(bad_manifest)


@pytest.mark.parametrize("asset_version", [None, "", "20260714", "../n2", "20260714N2"])
def test_backend_catalog_rejects_malformed_asset_versions(
    tmp_path: Path, asset_version: object,
) -> None:
    from services.papers_catalog import PapersCatalogError, load_papers_catalog

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["meta"]["asset_version"] = asset_version
    bad_manifest = tmp_path / "papers-manifest.json"
    bad_manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PapersCatalogError, match="asset version"):
        load_papers_catalog(bad_manifest)


def test_real_paper_route_serves_only_exact_manifest_members(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURAL_ENV", "dev")
    monkeypatch.setenv("STRUCTURAL_SHARE_TOKEN_SECRET", "test-secret-for-suite")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main

    client = TestClient(main.app)
    known = client.get("/paper/unified-pipeline-v0.2-2026-05-13")
    unknown = client.get("/paper/not-a-real-paper")

    assert known.status_code == 200
    assert 'id="paper-boundary"' in known.text
    assert unknown.status_code == 404
    assert "text/html" in unknown.headers["content-type"]
