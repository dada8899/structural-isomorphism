"""GET /api/flags — return resolved flags + experiment variants for current user.

Session #10 W15-E. Lightweight, no DB hit, just reads from in-process cache.

User identity resolution (in order):
  1. session/auth — if request has authenticated user, use their stable id
  2. anon hash from `X-Anon-Id` header (frontend sets a cookie/localStorage UUID)
  3. fallback: bucket 0 (anon = 'control' for all experiments)

The current tier (free/pro/team/admin) is already populated into the
`CURRENT_TIER` ContextVar by the rate-limit middleware (see
`middleware/rate_limit.py`). Segment-rollout flags read that.

Returns:
    {
      "flags": {"new_pricing_layout": true, "dark_mode_default": false, ...},
      "experiments": {"hero_cta_text_v2": "control"},
      "variants": {"hero_cta_text_v2": "Browse signals"}  // resolved content
    }
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, Request

from flags import (
    get_all_experiments,
    get_all_flags,
    _load_config,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["flags"])


def _resolve_user_id(request: Request, x_anon_id: Optional[str]) -> Optional[str]:
    """Return the stable id to bucket by.

    Priority: authenticated user > X-Anon-Id header > None.
    """
    # 1. Authenticated user (if auth middleware set request.state.user_id).
    user = getattr(request.state, "user_id", None)
    if user:
        return str(user)

    # 2. Anonymous header (frontend sets a stable cookie/localStorage UUID).
    if x_anon_id:
        return x_anon_id.strip() or None

    return None


@router.get("/flags")
async def get_flags(
    request: Request,
    x_anon_id: Optional[str] = Header(default=None, alias="X-Anon-Id"),
) -> dict:
    """Return resolved flags + experiment variants for current user."""
    user_id = _resolve_user_id(request, x_anon_id)

    flags = get_all_flags(user_id)
    experiments = get_all_experiments(user_id)

    # Also return resolved variant content (so frontend doesn't need to
    # know the mapping).
    cfg = _load_config()
    exp_cfg = cfg.get("experiments", {})
    variants: dict[str, str] = {}
    for exp_name, variant_name in experiments.items():
        exp_entry = exp_cfg.get(exp_name, {})
        content = exp_entry.get("variants", {}).get(variant_name)
        if content is not None:
            variants[exp_name] = str(content)

    return {
        "flags": flags,
        "experiments": experiments,
        "variants": variants,
    }
