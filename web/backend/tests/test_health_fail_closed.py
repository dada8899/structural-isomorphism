from __future__ import annotations

import asyncio

from fastapi.responses import JSONResponse

import main


class _Search:
    def __init__(self, kb_size: int) -> None:
        self.kb_size = kb_size

    def cache_stats(self) -> dict[str, float]:
        return {"hits": 0, "misses": 0, "hit_rate": 0.0, "size": 0, "maxsize": 1}


def test_deep_health_fails_on_empty_kb(monkeypatch) -> None:
    monkeypatch.setattr(main, "app_state", {"search": _Search(0)})
    response = asyncio.run(main.health(deep=1))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503


def test_deep_health_requires_validated_manifest(monkeypatch) -> None:
    monkeypatch.setattr(main, "app_state", {"search": _Search(4443)})
    response = asyncio.run(main.health(deep=1))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503


def test_deep_health_ready_with_bundle(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "app_state",
        {
            "search": _Search(4443),
            "artifact": {
                "artifact_id": "bundle",
                "embedding_shape": [4443, 768],
            },
        },
    )
    response = asyncio.run(main.health(deep=1))
    assert response["status"] == "ok"
    assert response["artifact_id"] == "bundle"
