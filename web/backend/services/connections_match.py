"""ConnectionsMatcher — G 方向匹配引擎（设计 §3.2）。

给定一个指纹，在其它用户的可发现（L1/L2）指纹里找「结构同构但领域不同」
的对象。算法不是难点（设计文档原话）——复用已有资产：

  * 结构相似度：SearchService._cosine()（已正确处理未 L2-归一化向量）
  * 领域距离：两指纹的 KB domain 是否不同（同 0 / 不同 1）
  * 普适类一致：universality_class 相同视为强结构信号

候选过滤（设计 §3.2）：
    structural_similarity >= STRUCT_SIM_MIN
    AND domain_distance    >= 1（领域必须不同——同域匹配无跨域价值）
    AND 候选指纹 visibility_level ∈ {L1, L2}
    AND 候选 user != 自己

排序：combined = structural_similarity × domain_distance ×（同普适类加成）。

本 MVP 不做「双方活跃度因子」（设计 §3.2 列了但属 P3+ 范畴，需用户行为
数据），用普适类一致加成替代，作为可解释的结构信号。
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger("structural.connections.match")

***REMOVED*** 结构相似度下限。复用 analyze 的 scope floor 口径（[0,1]，0.50 为正交线）。
STRUCT_SIM_MIN = 0.50
***REMOVED*** 同普适类加成系数（universality_class 相同 → combined ×1.15）。
SAME_CLASS_BONUS = 1.15


def _decode_embedding(blob: Optional[bytes]) -> Optional[np.ndarray]:
    """float32 little-endian BLOB → np.ndarray。无 / 损坏返回 None。"""
    if not blob:
        return None
    try:
        arr = np.frombuffer(blob, dtype="<f4")
        return arr if arr.size > 0 else None
    except Exception as e:  ***REMOVED*** pragma: no cover — defensive
        logger.warning("connections_match: bad embedding blob: %s", e)
        return None


def encode_to_blob(vec: np.ndarray) -> bytes:
    """np.ndarray → float32 little-endian BLOB（写指纹时用）。"""
    return np.asarray(vec, dtype="<f4").tobytes()


class ConnectionsMatcher:
    """无状态匹配引擎。依赖注入 SearchService 取 KB domain + _cosine。"""

    def __init__(self, search_service):
        ***REMOVED*** search_service 可为 None（KB 未就绪时降级）：此时 domain 取指纹
        ***REMOVED*** 自带的 domain 字段，_cosine 用本地实现。
        self._search = search_service

    ***REMOVED*** --- 内部工具 -------------------------------------------------------

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        """余弦相似度。优先用 SearchService 的实现保持口径一致。"""
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0 or a.shape != b.shape:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def _domain_of(self, fp: dict) -> str:
        """取指纹的领域。优先 KB（b_id → domain），回退指纹自带 domain 字段。"""
        b_id = fp.get("b_id")
        if b_id and self._search is not None:
            kb_item = getattr(self._search, "kb_by_id", {}).get(b_id)
            if kb_item and kb_item.get("domain"):
                return str(kb_item["domain"])
        return str(fp.get("domain") or "")

    ***REMOVED*** --- 主入口 ---------------------------------------------------------

    def match(
        self,
        target: dict,
        candidates: list[dict],
        *,
        sim_min: float = STRUCT_SIM_MIN,
        limit: int = 20,
    ) -> list[dict]:
        """为 target 指纹在 candidates 里找结构同构、领域不同的匹配。

        target / candidates 都是 ConnectionsStore 行 dict。candidates 应已
        是 list_discoverable() 的结果（L0 不会进来）。

        返回按 combined_score 降序的匹配 dict 列表，每条含可解释字段：
            { fingerprint_id, user_email, problem_summary, domain,
              type_id, universality_class, visibility_level,
              structural_similarity, domain_distance,
              same_universality_class, combined_score }
        """
        t_emb = _decode_embedding(target.get("embedding"))
        t_domain = self._domain_of(target)
        t_class = (target.get("universality_class") or "").strip()
        t_user = target.get("user_email")

        out: list[dict] = []
        for cand in candidates:
            ***REMOVED*** 排除自己（list_discoverable 已能排，这里二次防御）。
            if cand.get("user_email") and cand["user_email"] == t_user:
                continue
            if cand.get("id") == target.get("id"):
                continue

            ***REMOVED*** 结构相似度。
            c_emb = _decode_embedding(cand.get("embedding"))
            if t_emb is None or c_emb is None:
                sim = 0.0
            else:
                sim = self._cosine(t_emb, c_emb)
            if sim < sim_min:
                continue

            ***REMOVED*** 领域距离：必须不同领域（同域匹配无跨域价值）。
            c_domain = self._domain_of(cand)
            domain_distance = (
                1 if (t_domain and c_domain and t_domain != c_domain) else 0
            )
            if domain_distance < 1:
                continue

            ***REMOVED*** 同普适类加成。
            c_class = (cand.get("universality_class") or "").strip()
            same_class = bool(t_class and c_class and t_class == c_class)
            class_factor = SAME_CLASS_BONUS if same_class else 1.0

            combined = sim * domain_distance * class_factor

            out.append({
                "fingerprint_id": cand.get("id"),
                "user_email": cand.get("user_email"),
                "problem_summary": cand.get("problem_summary"),
                "domain": c_domain,
                "type_id": cand.get("type_id"),
                "universality_class": cand.get("universality_class"),
                "visibility_level": cand.get("visibility_level"),
                "structural_similarity": round(sim, 4),
                "domain_distance": domain_distance,
                "same_universality_class": same_class,
                "combined_score": round(combined, 4),
            })

        out.sort(key=lambda m: m["combined_score"], reverse=True)
        return out[:limit]

    def count_structural_neighbors(
        self,
        target: dict,
        candidates: list[dict],
        *,
        sim_min: float = STRUCT_SIM_MIN,
    ) -> int:
        """L1「N 人在解结构相同的问题」——纯计数，不暴露任何身份。

        这是设计 §3.3 L1 级别的核心：零隐私成本就能验证「我不孤独」。
        """
        return len(self.match(target, candidates, sim_min=sim_min, limit=10_000))


__all__ = [
    "ConnectionsMatcher",
    "encode_to_blob",
    "STRUCT_SIM_MIN",
    "SAME_CLASS_BONUS",
]
