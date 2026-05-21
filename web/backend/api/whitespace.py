"""GET /api/whitespace/* — A2 研究空白地图（Whitespace Map）。

两个端点：
  GET /api/whitespace/matrix — 完整矩阵（普适类 × 领域），供前端画热力图。
  GET /api/whitespace/leads  — 排序后的研究空白 leads，可按 class_id / domain 过滤。

数据来自 web/data/whitespace_matrix.json（scripts/build_whitespace_matrix.py
预计算）。WhitespaceService 启动时加载一次并缓存。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

from services.whitespace_service import WhitespaceService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["whitespace"])

***REMOVED*** Module-level singleton — loaded lazily on first request, cached thereafter.
***REMOVED*** Tests monkeypatch this attribute to inject an isolated fixture.
_service: Optional[WhitespaceService] = None


def _get_service() -> WhitespaceService:
    global _service
    if _service is None:
        _service = WhitespaceService()
    return _service


@router.get("/whitespace/matrix")
async def get_matrix():
    """完整的普适类 × 领域矩阵。每个格子带 state(filled/lead/empty) + score。"""
    svc = _get_service()
    payload = svc.get_matrix()
    payload["available"] = svc.available
    return payload


@router.get("/whitespace/leads")
async def get_leads(
    class_id: Optional[str] = Query(None, description="按普适类过滤"),
    domain: Optional[str] = Query(None, description="按目标领域过滤"),
    limit: int = Query(50, ge=1, le=500, description="返回条数上限"),
):
    """排序后的研究空白 leads（按结构相似度降序）。"""
    svc = _get_service()
    result = svc.get_leads(class_id=class_id, domain=domain, limit=limit)
    result["available"] = svc.available
    return result
