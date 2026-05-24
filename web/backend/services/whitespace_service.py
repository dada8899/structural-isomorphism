"""WhitespaceService — A2 研究空白地图数据访问层。

读取 scripts/build_whitespace_matrix.py 预计算的 web/data/whitespace_matrix.json，
启动时加载一次并缓存。提供矩阵 + 排序/过滤后的 leads。

json 缺失时优雅降级：返回空结构 + 记录日志，不抛异常。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("structural.whitespace")

# web/data/whitespace_matrix.json relative to this file:
# services/ -> backend/ -> web/ -> web/data/
_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "whitespace_matrix.json"


class WhitespaceService:
    """封装研究空白矩阵的查询。无状态、只读。"""

    def __init__(self, data_file: Optional[str | Path] = None):
        self.data_file = Path(data_file) if data_file else _DEFAULT_PATH
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if not self.data_file.exists():
            logger.warning(
                "whitespace_matrix.json not found at %s — serving empty data. "
                "Run scripts/build_whitespace_matrix.py to generate it.",
                self.data_file,
            )
            self._data = self._empty()
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # Minimal shape validation — guard against a truncated / wrong file.
            if not isinstance(raw, dict) or "matrix" not in raw or "leads" not in raw:
                logger.error("whitespace_matrix.json has unexpected shape — serving empty data.")
                self._data = self._empty()
                return
            self._data = raw
            logger.info(
                "Loaded whitespace matrix: %d classes, %d domains, %d leads",
                len(raw.get("classes", [])),
                len(raw.get("domains", [])),
                len(raw.get("leads", [])),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load whitespace_matrix.json: %s", e)
            self._data = self._empty()

    @staticmethod
    def _empty() -> dict:
        return {
            "meta": {"n_classes": 0, "n_domains": 0, "n_leads": 0},
            "classes": [],
            "domains": [],
            "matrix": {},
            "leads": [],
        }

    @property
    def available(self) -> bool:
        """True when a real precomputed matrix is loaded."""
        return bool(self._data.get("matrix"))

    def get_matrix(self) -> dict:
        """Return the full matrix payload (meta + classes + domains + matrix)."""
        return {
            "meta": self._data.get("meta", {}),
            "classes": self._data.get("classes", []),
            "domains": self._data.get("domains", []),
            "matrix": self._data.get("matrix", {}),
        }

    def get_leads(
        self,
        class_id: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """Return ranked research-whitespace leads, optionally filtered.

        Args:
            class_id: keep only leads for this universality class.
            domain:   keep only leads targeting this domain.
            limit:    max number of leads to return (clamped to 1..500).
        """
        leads = self._data.get("leads", [])
        if class_id:
            leads = [x for x in leads if x.get("class_id") == class_id]
        if domain:
            leads = [x for x in leads if x.get("domain") == domain]
        # leads in the json are already score-desc sorted; defensive re-sort.
        leads = sorted(leads, key=lambda x: -x.get("score", 0.0))
        total = len(leads)
        limit = max(1, min(int(limit), 500))
        return {
            "total": total,
            "count": min(total, limit),
            "limit": limit,
            "filters": {"class_id": class_id, "domain": domain},
            "leads": leads[:limit],
        }
