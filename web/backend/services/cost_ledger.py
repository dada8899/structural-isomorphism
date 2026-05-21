"""Daily LLM cost / call budget ledger (launch P0-2).

The expensive endpoints (/api/ask/stream, /api/analyze/stream) each trigger
real paid OpenRouter calls. Before this module nothing capped daily spend —
`errors.BudgetExceeded` was defined but never raised, so an anonymous user
or a runaway script could burn the LLM budget unbounded.

This is a deliberately small, dependency-free circuit breaker:

  * One process-wide counter, bucketed by UTC date.
  * Each LLM-backed request calls `charge()` once before the pipeline runs.
  * When the day's count exceeds the cap, `charge()` raises `BudgetExceeded`
    (RFC 7807, status 429) — the endpoint translates that into a friendly
    response, not a 500.

Scope / non-goals (v1):
  * Process-local, not Redis-backed — a multi-process deploy gets one cap
    per worker. For a single-worker beta that is the intended behaviour;
    a shared store is a follow-up if/when we scale out.
  * Counts *calls*, not token spend. A coarse call cap is enough to stop
    the realistic failure mode (a loop hammering the endpoint). Token-level
    accounting would need usage data the LLM layer doesn't surface yet.
  * The OpenRouter account-side hard spend limit is still the ultimate
    backstop; this is the application-layer early warning.

Config (env, all optional — sane defaults built in):
  STRUCTURAL_LLM_DAILY_CALL_CAP   int, default 500. Total LLM-backed
                                  requests allowed per UTC day. <= 0
                                  disables the cap (NOT recommended in prod).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import threading

logger = logging.getLogger("structural.cost_ledger")

_DEFAULT_DAILY_CALL_CAP = 500


def _today_utc() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")


def _resolve_cap() -> int:
    """Read the daily cap from env each call so an operator can retune it
    without a process restart (env is re-read; cheap)."""
    raw = os.getenv("STRUCTURAL_LLM_DAILY_CALL_CAP", "")
    if not raw.strip():
        return _DEFAULT_DAILY_CALL_CAP
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(
            "cost_ledger: bad STRUCTURAL_LLM_DAILY_CALL_CAP=%r — using default %d",
            raw, _DEFAULT_DAILY_CALL_CAP,
        )
        return _DEFAULT_DAILY_CALL_CAP


class _DailyCallLedger:
    """Thread-safe per-UTC-day call counter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._date = _today_utc()
        self._count = 0

    def _roll_if_new_day(self) -> None:
        today = _today_utc()
        if today != self._date:
            self._date = today
            self._count = 0

    def charge(self, endpoint: str = "") -> None:
        """Record one LLM-backed request. Raise BudgetExceeded if over cap.

        Called once per request, BEFORE the LLM pipeline runs, so an
        over-budget request is rejected without ever paying the API cost.
        """
        ***REMOVED*** Local import: errors.py imports nothing from services, but keep
        ***REMOVED*** the dependency direction one-way and avoid any import-time cycle.
        from errors import BudgetExceeded

        cap = _resolve_cap()
        with self._lock:
            self._roll_if_new_day()
            if cap > 0 and self._count >= cap:
                used = self._count
                logger.warning(
                    "cost_ledger: daily LLM call cap hit (%d/%d) on %s endpoint=%s",
                    used, cap, self._date, endpoint or "?",
                )
                raise BudgetExceeded(
                    detail=(
                        "Daily request limit reached. The service caps how "
                        "many AI analyses it runs each day to control cost — "
                        "please try again tomorrow."
                    ),
                    ***REMOVED*** RFC 7807 extension fields (purely informational).
                    tier="all",
                    limit=cap,
                    remaining=0,
                )
            self._count += 1

    def snapshot(self) -> dict:
        """Return current usage (for /api/health or admin). Never raises."""
        with self._lock:
            self._roll_if_new_day()
            cap = _resolve_cap()
            return {
                "date": self._date,
                "used": self._count,
                "cap": cap,
                "remaining": max(0, cap - self._count) if cap > 0 else None,
            }

    def reset(self) -> None:
        """Test helper — clear the counter."""
        with self._lock:
            self._date = _today_utc()
            self._count = 0


***REMOVED*** Process-wide singleton. Import this and call `.charge()`.
ledger = _DailyCallLedger()


__all__ = ["ledger", "_DailyCallLedger"]
