"""POST/GET /api/connections/* — G 方向「按问题结构连接人」(P1+P2+P3)。

Session #19 G-MVP（P1+P2）+ Session #22 G-P3（双向同意 match / 引荐 / 消息）。
设计依据：docs/sessions/SESSION-18-G-connect-people-design.md。

落地范围（设计 §4 的分阶段路径）：
  * P1  指纹抽取与存储 —— 用户把一份 analyze 报告「升级成可连接的指纹」
  * P2  匹配引擎 + L1 可发现 —— 「N 人在解结构相同的问题」纯计数，不暴露身份
  * P3  L2 + 双向同意 match + 引荐 + 异步消息信箱 —— 真正的人际连接

端点（P1+P2，沿用）：
    POST   /api/connections/fingerprints          登记指纹（需登录）
    GET    /api/connections/fingerprints          列出我的指纹（需登录）
    PATCH  /api/connections/fingerprints/{id}     改可见性（需登录, owner）
    DELETE /api/connections/fingerprints/{id}     删指纹（需登录, owner）
    GET    /api/connections/fingerprints/{id}/neighbors
                                                  匹配结果（需登录, owner）

端点（P3，本次新增）：
    POST   /api/connections/match-request                 发起 match
    GET    /api/connections/match-requests/pending        我收到的待处理
    GET    /api/connections/match-requests/sent           我发出的全部
    POST   /api/connections/match-requests/{id}/accept    接受
    POST   /api/connections/match-requests/{id}/decline   拒绝
    GET    /api/connections/match-requests/accepted       已 match 列表
    POST   /api/connections/referral                      发起引荐
    GET    /api/connections/referrals                     我相关的全部引荐
    POST   /api/connections/referrals/{id}/accept         接受（必须是 A 或 B）
    POST   /api/connections/referrals/{id}/decline        拒绝
    POST   /api/connections/messages                      给已 match 的人发消息
    GET    /api/connections/messages/inbox                收件箱
    POST   /api/connections/messages/{id}/read            标记已读
    GET    /api/connections/prefs                         我的偏好（block/mute/msg_open）
    PATCH  /api/connections/prefs                         更新偏好

鉴权：复用 api/auth.py 的 magic-link JWT session cookie（phase_session）。
无有效 session → 401。所有指纹操作强制 owner 隔离。所有 P3 端点统一 fail-closed
（看不见 / 没权限一律 404 不区分，避免泄露存在性）。

隐私（设计 §3.3）：
  * 指纹默认 L0（私密）。neighbors 端点只给「N 人」纯计数，不返回 user_email。
  * P3 match-request 目标必须是 L2 指纹（L0/L1 拒绝——L1 是「N 人」语义，
    打破要先 opt-in 升 L2）。
  * 接受 match 之前，对方身份不解锁（A 只能看到「有人对你 X 问题感兴趣」）。
  * Messages 仅在双方 already-matched + 双方都没 block / 没关消息开关时放行。
  * 全部 P3 数据进 /api/privacy/{export,delete} 范围（SESSION-21 §6 模式）。
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
from services.connections_p3_store import (
    ConnectionsP3Store,
    detect_pii_leak,
)

logger = logging.getLogger("structural.connections.api")
router = APIRouter(tags=["connections"], prefix="/connections")

_store: Optional[ConnectionsStore] = None
_p3_store: Optional[ConnectionsP3Store] = None


def _get_store() -> ConnectionsStore:
    """共享 ConnectionsStore（与 reports 同一 history.db）。

    模块全局，测试可 monkeypatch 成 tmp-path store（同 api/report.py 模式）。
    """
    global _store
    if _store is None:
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _store = ConnectionsStore(db_path)
    return _store


def _get_p3_store() -> ConnectionsP3Store:
    """共享 ConnectionsP3Store（同一 history.db，P3 四张表）。"""
    global _p3_store
    if _p3_store is None:
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _p3_store = ConnectionsP3Store(db_path)
    return _p3_store


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


# ==================================================================== #
# P3 — mutual-consent match + referrals + messages
# ==================================================================== #


# ---------------- 请求 / 响应 schema (P3) ---------------------------- #


class MatchRequestBody(BaseModel):
    # 注意：from_user 不在 body 里——由 session cookie 唯一确定（防伪造）。
    to_fingerprint_id: str = Field(..., max_length=64)
    note: Optional[str] = Field(None, max_length=280)


class ReferralBody(BaseModel):
    referee_a_email: str = Field(..., max_length=200)
    referee_b_email: str = Field(..., max_length=200)
    reason: Optional[str] = Field(None, max_length=500)


class MessageBody(BaseModel):
    to_email: str = Field(..., max_length=200)
    body: str = Field(..., min_length=1, max_length=500)


class PrefsBody(BaseModel):
    mute_referrals: Optional[bool] = None
    messages_open: Optional[bool] = None
    block_email: Optional[str] = Field(None, max_length=200)
    unblock_email: Optional[str] = Field(None, max_length=200)


# ---------------- helper：脱敏视图 ----------------------------------- #


def _public_match_request(
    row: dict, *, viewer_email: str, hide_from_identity: bool = False
) -> dict:
    """对外暴露的 match-request 视图。

    hide_from_identity=True → 隐藏 from_user_email（pending 状态下，接收方
    还没接受时不该看到发起人是谁；这是设计 §3.3 的「A 先匿名表示兴趣」语义）。
    """
    out = {
        "id": row.get("id"),
        "to_fingerprint_id": row.get("to_fingerprint_id"),
        "note": row.get("note"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "responded_at": row.get("responded_at"),
    }
    # 视角字段
    if row.get("from_user_email") == viewer_email:
        out["direction"] = "sent"
        out["other_email"] = row.get("to_user_email")
    else:
        out["direction"] = "received"
        out["other_email"] = (
            "(anonymous)"
            if hide_from_identity
            else row.get("from_user_email")
        )
    return out


def _public_referral(row: dict, *, viewer_email: str) -> dict:
    role = row.get("role")
    if role is None:
        # fallback: 计算 role
        if row.get("referrer_email") == viewer_email:
            role = "referrer"
        elif row.get("referee_a_email") == viewer_email:
            role = "referee_a"
        elif row.get("referee_b_email") == viewer_email:
            role = "referee_b"
    return {
        "id": row.get("id"),
        "role": role,
        "referrer_email": row.get("referrer_email"),
        "referee_a_email": row.get("referee_a_email"),
        "referee_b_email": row.get("referee_b_email"),
        "reason": row.get("reason"),
        "status_a": row.get("status_a"),
        "status_b": row.get("status_b"),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
    }


def _public_message(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "from_email": row.get("from_email"),
        "to_email": row.get("to_email"),
        "body": row.get("body"),
        "sent_at": row.get("sent_at"),
        "read_at": row.get("read_at"),
    }


# ---------------- match-request 端点 --------------------------------- #


@router.post("/match-request", summary="发起一次双向同意 match")
async def post_match_request(body: MatchRequestBody, request: Request):
    """A 看到结构邻居 B，想认识 → 发 match request。

    校验：
      * 目标指纹存在
      * 目标指纹是别人的（不能跟自己 match）
      * 目标指纹必须是 L2（L0/L1 还没 opt-in 进入 match 流程）
      * 接收方没 block 我（fail-closed —— 返回与「不存在」相同的 404，不泄露 block 状态）
      * 同 (from, to, fp) 没有 pending（去重；唯一索引兜底）
    """
    email, err = _require_login(request)
    if err:
        return err
    store = _get_store()
    p3 = _get_p3_store()

    target_fp = store.get_fingerprint(body.to_fingerprint_id)
    if not target_fp:
        return JSONResponse(
            {"ok": False, "error": "fingerprint not found"}, status_code=404
        )
    target_email = target_fp.get("user_email")
    if not target_email or target_email == email:
        return JSONResponse(
            {"ok": False, "error": "cannot match own fingerprint"},
            status_code=400,
        )
    # 必须是 L2（明确 opt-in 进入 match 流程）。L0/L1 → 404（不泄露指纹存在）。
    if target_fp.get("visibility_level") != "L2":
        return JSONResponse(
            {"ok": False, "error": "fingerprint not found"}, status_code=404
        )
    # 对方 block 了我？fail-closed — 一样 404。
    if p3.is_blocked(target_email, email):
        return JSONResponse(
            {"ok": False, "error": "fingerprint not found"}, status_code=404
        )

    rid = p3.create_match_request(
        from_user_email=email,
        to_user_email=target_email,
        to_fingerprint_id=body.to_fingerprint_id,
        note=body.note,
    )
    if rid is None:
        return JSONResponse(
            {"ok": False, "error": "duplicate pending request"},
            status_code=409,
        )
    row = p3.get_match_request(rid)
    return JSONResponse({
        "ok": True,
        "match_request": _public_match_request(row, viewer_email=email),
    })


@router.get(
    "/match-requests/pending", summary="我收到的待处理 match requests"
)
async def list_pending_match_requests(request: Request):
    email, err = _require_login(request)
    if err:
        return err
    rows = _get_p3_store().list_pending_for_user(email)
    return JSONResponse({
        "ok": True,
        "match_requests": [
            # pending 状态隐藏发起人身份——「A 匿名表示兴趣」语义。
            _public_match_request(r, viewer_email=email, hide_from_identity=True)
            for r in rows
        ],
    })


@router.get(
    "/match-requests/sent", summary="我发出的全部 match requests"
)
async def list_sent_match_requests(request: Request):
    email, err = _require_login(request)
    if err:
        return err
    rows = _get_p3_store().list_sent_for_user(email)
    return JSONResponse({
        "ok": True,
        "match_requests": [
            _public_match_request(r, viewer_email=email) for r in rows
        ],
    })


@router.post(
    "/match-requests/{rid}/accept", summary="接受一个 match request"
)
async def accept_match_request(rid: str, request: Request):
    email, err = _require_login(request)
    if err:
        return err
    p3 = _get_p3_store()
    ok = p3.respond_match_request(rid, email, accept=True)
    if not ok:
        # 不存在 / 非接收方 / 已响应过 —— 统一 404（fail-closed）
        return JSONResponse(
            {"ok": False, "error": "match request not found"},
            status_code=404,
        )
    row = p3.get_match_request(rid)
    return JSONResponse({
        "ok": True,
        "match_request": _public_match_request(row, viewer_email=email),
    })


@router.post(
    "/match-requests/{rid}/decline", summary="拒绝一个 match request"
)
async def decline_match_request(rid: str, request: Request):
    email, err = _require_login(request)
    if err:
        return err
    p3 = _get_p3_store()
    ok = p3.respond_match_request(rid, email, accept=False)
    if not ok:
        return JSONResponse(
            {"ok": False, "error": "match request not found"},
            status_code=404,
        )
    row = p3.get_match_request(rid)
    return JSONResponse({
        "ok": True,
        "match_request": _public_match_request(row, viewer_email=email),
    })


@router.get(
    "/match-requests/accepted", summary="我已 match 的人（双向身份互见）"
)
async def list_accepted_matches(request: Request):
    email, err = _require_login(request)
    if err:
        return err
    rows = _get_p3_store().list_accepted_matches(email)
    # accepted 状态双方身份已互见——other_email 真实暴露。
    return JSONResponse({
        "ok": True,
        "matches": [
            {
                "id": r.get("id"),
                "other_email": r.get("other_email"),
                "direction": r.get("direction"),
                "to_fingerprint_id": r.get("to_fingerprint_id"),
                "note": r.get("note"),
                "created_at": r.get("created_at"),
                "responded_at": r.get("responded_at"),
            }
            for r in rows
        ],
    })


# ---------------- referral 端点 -------------------------------------- #


@router.post("/referral", summary="发起一次引荐（X 撮合 A 和 B）")
async def post_referral(body: ReferralBody, request: Request):
    """X 看到 A 和 B 结构相似，撮合二人。

    校验：
      * 三方互不相同（X != A, X != B, A != B）
      * A、B 均未 mute_referrals（mute → 不创建，401 不区分用户存在性 → 200/ok 但 a/b 标 muted）
        我们这里采取「写入但显示 muted」策略——referrer 知道发出去了，
        但当事人收件箱不会看到。简化版直接看是否双方都 mute，至少一方未 mute 才写。
      * A 或 B 不能是 referrer 自己（前一条已覆盖）
    """
    email, err = _require_login(request)
    if err:
        return err
    p3 = _get_p3_store()

    # mute 校验（双方都 mute 则连写都不写——节省存储 + 信号清晰）
    prefs_a = p3.get_user_prefs(body.referee_a_email)
    prefs_b = p3.get_user_prefs(body.referee_b_email)
    if prefs_a["mute_referrals"] and prefs_b["mute_referrals"]:
        return JSONResponse(
            {"ok": False, "error": "both parties muted referrals"},
            status_code=403,
        )

    rid = p3.create_referral(
        referrer_email=email,
        referee_a_email=body.referee_a_email,
        referee_b_email=body.referee_b_email,
        reason=body.reason,
    )
    if rid is None:
        return JSONResponse(
            {"ok": False, "error": "referrer/referees must be three distinct emails"},
            status_code=400,
        )
    row = p3.get_referral(rid)
    return JSONResponse({
        "ok": True,
        "referral": _public_referral(row, viewer_email=email),
    })


@router.get("/referrals", summary="我相关的全部 referrals（任一角色）")
async def list_referrals(request: Request):
    email, err = _require_login(request)
    if err:
        return err
    rows = _get_p3_store().list_referrals_for_user(email)
    # mute 的人作为 referee 时，不展示给他自己（信号噪音）
    prefs = _get_p3_store().get_user_prefs(email)
    if prefs["mute_referrals"]:
        rows = [
            r for r in rows
            if r.get("role") == "referrer"  # 作为 referrer 的引荐自己仍可见
        ]
    return JSONResponse({
        "ok": True,
        "referrals": [_public_referral(r, viewer_email=email) for r in rows],
    })


@router.post(
    "/referrals/{rid}/accept", summary="作为 A 或 B 接受引荐"
)
async def accept_referral(rid: str, request: Request):
    email, err = _require_login(request)
    if err:
        return err
    ok, row = _get_p3_store().respond_referral(rid, email, accept=True)
    if not ok:
        return JSONResponse(
            {"ok": False, "error": "referral not found or not actionable"},
            status_code=404,
        )
    return JSONResponse({
        "ok": True,
        "referral": _public_referral(row, viewer_email=email),
        "completed": bool(row.get("completed_at")),
    })


@router.post(
    "/referrals/{rid}/decline", summary="作为 A 或 B 拒绝引荐"
)
async def decline_referral(rid: str, request: Request):
    email, err = _require_login(request)
    if err:
        return err
    ok, row = _get_p3_store().respond_referral(rid, email, accept=False)
    if not ok:
        return JSONResponse(
            {"ok": False, "error": "referral not found or not actionable"},
            status_code=404,
        )
    return JSONResponse({
        "ok": True,
        "referral": _public_referral(row, viewer_email=email),
    })


# ---------------- message 端点 --------------------------------------- #


@router.post("/messages", summary="给已 match 的人发一条消息")
async def post_message(body: MessageBody, request: Request):
    """给已 matched 的对方发消息。

    校验链（按 fail-fast 顺序）：
      1. 不是自己发给自己
      2. 双方 already-matched（accepted match request 存在）
      3. 接收方没 block 发送方
      4. 接收方 messages_open == True
      5. 发送方 24h 内 < 10 条（rate limit）
      6. body 通过 PII 过滤（无 URL / phone / email / handle）
    """
    email, err = _require_login(request)
    if err:
        return err
    if body.to_email == email:
        return JSONResponse(
            {"ok": False, "error": "cannot message self"}, status_code=400
        )
    p3 = _get_p3_store()
    if not p3.are_matched(email, body.to_email):
        # fail-closed —— 不区分「未 match」vs「对方不存在」
        return JSONResponse(
            {"ok": False, "error": "not matched"}, status_code=403
        )
    if p3.is_blocked(body.to_email, email):
        return JSONResponse(
            {"ok": False, "error": "not matched"}, status_code=403
        )
    prefs = p3.get_user_prefs(body.to_email)
    if not prefs["messages_open"]:
        return JSONResponse(
            {"ok": False, "error": "recipient closed messages"},
            status_code=403,
        )
    sent_today = p3.count_messages_sent_today(email)
    if sent_today >= p3.MESSAGE_DAILY_LIMIT:
        return JSONResponse(
            {
                "ok": False,
                "error": "daily message limit reached",
                "limit": p3.MESSAGE_DAILY_LIMIT,
            },
            status_code=429,
        )
    # 内容过滤
    leak = detect_pii_leak(body.body)
    if leak is not None:
        return JSONResponse(
            {
                "ok": False,
                "error": "message rejected by content filter",
                "category": leak,
            },
            status_code=400,
        )
    mid = p3.create_message(
        from_email=email, to_email=body.to_email, body=body.body
    )
    row = p3.get_message(mid)
    return JSONResponse({"ok": True, "message": _public_message(row)})


@router.get("/messages/inbox", summary="我的收件箱")
async def list_inbox(request: Request):
    email, err = _require_login(request)
    if err:
        return err
    rows = _get_p3_store().list_inbox(email)
    return JSONResponse({
        "ok": True,
        "messages": [_public_message(r) for r in rows],
    })


@router.post(
    "/messages/{mid}/read", summary="把一条消息标为已读"
)
async def mark_message_read(mid: str, request: Request):
    email, err = _require_login(request)
    if err:
        return err
    ok = _get_p3_store().mark_read(mid, email)
    if not ok:
        return JSONResponse(
            {"ok": False, "error": "message not found"}, status_code=404
        )
    return JSONResponse({"ok": True})


# ---------------- prefs 端点（block / mute / messages_open） --------- #


@router.get("/prefs", summary="我的偏好（block / mute / messages_open）")
async def get_prefs(request: Request):
    email, err = _require_login(request)
    if err:
        return err
    return JSONResponse({"ok": True, "prefs": _get_p3_store().get_user_prefs(email)})


@router.patch("/prefs", summary="更新偏好")
async def patch_prefs(body: PrefsBody, request: Request):
    email, err = _require_login(request)
    if err:
        return err
    p3 = _get_p3_store()
    if body.block_email:
        if body.block_email == email:
            return JSONResponse(
                {"ok": False, "error": "cannot block self"}, status_code=400
            )
        p3.set_block(email, body.block_email, True)
    if body.unblock_email:
        p3.set_block(email, body.unblock_email, False)
    if body.mute_referrals is not None or body.messages_open is not None:
        p3.set_user_prefs(
            email,
            mute_referrals=body.mute_referrals,
            messages_open=body.messages_open,
        )
    return JSONResponse({"ok": True, "prefs": p3.get_user_prefs(email)})


# ---------------- 测试 helper ---------------------------------------- #


def _override_store_for_tests(store: ConnectionsStore) -> None:
    """把模块全局 store 换成测试 tmp-path 实例。"""
    global _store
    _store = store


def _override_p3_store_for_tests(store: ConnectionsP3Store) -> None:
    """把模块全局 P3 store 换成测试 tmp-path 实例。"""
    global _p3_store
    _p3_store = store


__all__ = ["router"]
