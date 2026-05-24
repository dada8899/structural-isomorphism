"""POST/GET /api/connections/* — G 方向「按问题结构连接人」(P1+P2)。

Session #19 G-MVP。设计依据：docs/sessions/SESSION-18-G-connect-people-design.md。

落地范围（设计 §4 的分阶段路径）：
  * P1  指纹抽取与存储 —— 用户把一份 analyze 报告「升级成可连接的指纹」
  * P2  匹配引擎 + L1 可发现 —— 「N 人在解结构相同的问题」纯计数，不暴露身份
  本 MVP **不做** P3（双向同意 match 流程 / 引荐 / 消息）—— 见 OUTCOME 报告。

端点：
    POST   /api/connections/fingerprints          登记指纹（需登录）
    GET    /api/connections/fingerprints          列出我的指纹（需登录）
    PATCH  /api/connections/fingerprints/{id}     改可见性（需登录, owner）
    DELETE /api/connections/fingerprints/{id}     删指纹（需登录, owner）
    GET    /api/connections/fingerprints/{id}/neighbors
                                                  匹配结果（需登录, owner）

鉴权：复用 api/auth.py 的 magic-link JWT session cookie（phase_session）。
无有效 session → 401。所有指纹操作强制 owner 隔离。

隐私（设计 §3.3）：指纹默认 L0（私密）。neighbors 端点：
  * 指纹自身是 L0 → 仍可看「N 人结构相同」计数（这是我自己的问题，纯统计）
  * 候选只取别人的 L1/L2 指纹，且 neighbor 列表里**不返回 user_email**
    —— MVP 不暴露任何身份，符合 L1「纯数字」语义。L2 身份交换属 P3。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.connections_store import (
    ConnectionsStore,
    VISIBILITY_LEVELS,
)
from services.connections_match import ConnectionsMatcher, encode_to_blob

logger = logging.getLogger("structural.connections.api")
router = APIRouter(tags=["connections"], prefix="/connections")

_store: Optional[ConnectionsStore] = None


def _get_store() -> ConnectionsStore:
    """共享 ConnectionsStore（与 reports 同一 history.db）。

    模块全局，测试可 monkeypatch 成 tmp-path store（同 api/report.py 模式）。
    """
    global _store
    if _store is None:
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _store = ConnectionsStore(db_path)
    return _store


# ---------------- 鉴权 helper ---------------------------------------- #


def _current_user_email(request: Request) -> Optional[str]:
    """从 magic-link session cookie 解出当前用户 email，无效返回 None。

    复用 api/auth.py 的 cookie 名 + JWT 校验 + jti 吊销检查，避免在两处
    各写一份 JWT 逻辑（单一权威源）。
    """
    from api.auth import _COOKIE_NAME, _decode_jwt, _is_jti_revoked

    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        return None
    claims = _decode_jwt(cookie)
    if not claims:
        return None
    if _is_jti_revoked(claims.get("jti", "")):
        return None
    email = claims.get("sub")
    return email if email else None


def _require_login(request: Request):
    """返回 (email, None) 或 (None, 401-JSONResponse)。"""
    email = _current_user_email(request)
    if not email:
        return None, JSONResponse(
            {"ok": False, "error": "login required"}, status_code=401
        )
    return email, None


# ---------------- 请求 / 响应 schema --------------------------------- #


class CreateFingerprintBody(BaseModel):
    # 指纹可来自一份 analyze 报告（推荐），也可纯手动登记。
    source_report_id: Optional[str] = Field(None, max_length=64)
    problem_summary: str = Field(..., min_length=4, max_length=500)
    b_id: Optional[str] = Field(None, max_length=64)
    domain: Optional[str] = Field(None, max_length=80)
    type_id: Optional[str] = Field(None, max_length=40)
    universality_class: Optional[str] = Field(None, max_length=80)
    # 可见性默认 L0；前端 opt-in 开关可直接传 L1。
    visibility_level: str = Field("L0")


class SetVisibilityBody(BaseModel):
    visibility_level: str = Field(...)


# ---------------- 指纹向量抽取 --------------------------------------- #


def _encode_problem(text: str) -> Optional[bytes]:
    """problem_summary 文本 → embedding BLOB。

    复用 app_state['search'].encode_query()，与 search/analyze 同一向量
    空间，匹配口径一致。search 未就绪 → 返回 None（指纹仍可存，只是
    暂不可被结构匹配，neighbors 会返回 0——优雅降级）。
    """
    try:
        from main import app_state
        search = app_state.get("search")
        if search is None:
            return None
        vec = search.encode_query(text)
        return encode_to_blob(vec)
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("connections: encode_problem failed: %s", e)
        return None


def _get_matcher() -> ConnectionsMatcher:
    """构造匹配引擎，注入 SearchService（可能为 None）。"""
    search = None
    try:
        from main import app_state
        search = app_state.get("search")
    except Exception:  # pragma: no cover
        pass
    return ConnectionsMatcher(search_service=search)


def _public_fingerprint(row: dict) -> dict:
    """对外暴露的指纹视图——去掉 embedding BLOB（不可序列化、无意义）。"""
    return {
        "id": row.get("id"),
        "source_report_id": row.get("source_report_id"),
        "b_id": row.get("b_id"),
        "domain": row.get("domain"),
        "type_id": row.get("type_id"),
        "universality_class": row.get("universality_class"),
        "problem_summary": row.get("problem_summary"),
        "visibility_level": row.get("visibility_level"),
        "has_embedding": bool(row.get("embedding")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ---------------- 端点 ----------------------------------------------- #


@router.post("/fingerprints", summary="登记一个问题结构指纹")
async def create_fingerprint(body: CreateFingerprintBody, request: Request):
    """把用户「正在解的问题」登记成一个结构指纹。需登录。

    可见性默认 L0（私密）；非法值由 store 降级为 L0。
    """
    email, err = _require_login(request)
    if err:
        return err

    if body.visibility_level not in VISIBILITY_LEVELS:
        return JSONResponse(
            {"ok": False, "error": "invalid visibility_level"},
            status_code=400,
        )

    embedding = _encode_problem(body.problem_summary)
    store = _get_store()
    fid = store.create_fingerprint(
        user_email=email,
        problem_summary=body.problem_summary.strip(),
        embedding=embedding,
        source_report_id=body.source_report_id,
        b_id=body.b_id,
        domain=body.domain,
        type_id=body.type_id,
        universality_class=body.universality_class,
        visibility_level=body.visibility_level,
    )
    row = store.get_fingerprint(fid)
    return JSONResponse({"ok": True, "fingerprint": _public_fingerprint(row)})


@router.get("/fingerprints", summary="列出我的全部指纹")
async def list_fingerprints(request: Request):
    """返回当前用户的所有指纹（含各自可见性）。需登录。"""
    email, err = _require_login(request)
    if err:
        return err
    rows = _get_store().list_by_user(email)
    return JSONResponse({
        "ok": True,
        "fingerprints": [_public_fingerprint(r) for r in rows],
    })


@router.patch("/fingerprints/{fid}", summary="修改指纹可见性")
async def update_visibility(fid: str, body: SetVisibilityBody, request: Request):
    """改某指纹的可见性级别（L0/L1/L2）。需登录且为 owner。

    这是用户的显式 opt-in / opt-out 动作——非法 level 拒绝，不静默降级。
    """
    email, err = _require_login(request)
    if err:
        return err
    if body.visibility_level not in VISIBILITY_LEVELS:
        return JSONResponse(
            {"ok": False, "error": "invalid visibility_level"},
            status_code=400,
        )
    ok = _get_store().set_visibility(fid, email, body.visibility_level)
    if not ok:
        # 不区分「不存在」vs「非 owner」——避免泄露指纹是否存在。
        return JSONResponse(
            {"ok": False, "error": "fingerprint not found"}, status_code=404
        )
    row = _get_store().get_fingerprint(fid)
    return JSONResponse({"ok": True, "fingerprint": _public_fingerprint(row)})


@router.delete("/fingerprints/{fid}", summary="删除一个指纹")
async def delete_fingerprint(fid: str, request: Request):
    """删除指纹。需登录且为 owner。"""
    email, err = _require_login(request)
    if err:
        return err
    ok = _get_store().delete_fingerprint(fid, email)
    if not ok:
        return JSONResponse(
            {"ok": False, "error": "fingerprint not found"}, status_code=404
        )
    return JSONResponse({"ok": True})


@router.get(
    "/fingerprints/{fid}/neighbors",
    summary="结构邻居（N 人在解结构相同的问题）",
)
async def neighbors(fid: str, request: Request):
    """对一个指纹做匹配：结构同构但领域不同的其他用户指纹。

    需登录且为指纹 owner。返回：
      * neighbor_count —— L1 级别的「N 人结构相同」纯数字
      * neighbors      —— 匹配明细，**不含 user_email**（MVP 不暴露身份）

    候选只取别人的 L1/L2 指纹；自己的指纹是 L0 也能查（看自己的统计）。
    """
    email, err = _require_login(request)
    if err:
        return err
    store = _get_store()
    target = store.get_fingerprint(fid)
    if not target or target.get("user_email") != email:
        return JSONResponse(
            {"ok": False, "error": "fingerprint not found"}, status_code=404
        )

    candidates = store.list_discoverable(exclude_user=email)
    matcher = _get_matcher()
    matches = matcher.match(target, candidates, limit=20)

    # MVP 隐私边界：剥掉 user_email + fingerprint_id —— L1 只给「N 人 + 结构
    # 描述」，不给任何能定位到人的标识。身份交换是 P3 的双向同意流程。
    safe = [
        {
            "problem_summary": m["problem_summary"],
            "domain": m["domain"],
            "universality_class": m["universality_class"],
            "structural_similarity": m["structural_similarity"],
            "same_universality_class": m["same_universality_class"],
            "combined_score": m["combined_score"],
        }
        for m in matches
    ]
    return JSONResponse({
        "ok": True,
        "fingerprint": _public_fingerprint(target),
        "neighbor_count": len(matches),
        "neighbors": safe,
    })


# ---------------- 测试 helper ---------------------------------------- #


def _override_store_for_tests(store: ConnectionsStore) -> None:
    """把模块全局 store 换成测试 tmp-path 实例。"""
    global _store
    _store = store


__all__ = ["router"]
