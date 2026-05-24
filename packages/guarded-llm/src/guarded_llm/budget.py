"""Budget tracking and enforcement for guarded-llm.

Public types::

    Budget(usd_total: float, usd_per_call: float = inf)
        .consume(usd: float) -> None    # raises BudgetExceeded if either cap hit
        .spent_usd -> float
        .remaining_usd -> float

`BudgetExceeded` is a re-export of the existing `BudgetExceededError` so the
public name in docs matches the more common spelling while keeping the existing
exception hierarchy intact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .exceptions import BudgetExceededError


# Public alias — matches the name used in README/quickstart.
BudgetExceeded = BudgetExceededError


@dataclass
class Budget:
    """Track and cap LLM spend across one or more `GuardedLLM.call(...)` runs.

    Args:
        usd_total: total budget cap in USD across the lifetime of this Budget.
        usd_per_call: max spend allowed for any single `.consume(...)` call.
            Defaults to infinity (no per-call cap).

    Example::

        b = Budget(usd_total=0.50, usd_per_call=0.10)
        b.consume(0.03)            # OK
        b.consume(0.50)            # raises BudgetExceeded (over per-call cap)
        b.spent_usd                # 0.03
        b.remaining_usd            # 0.47
    """

    usd_total: float
    usd_per_call: float = math.inf
    spent_usd: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.usd_total, (int, float)) or isinstance(self.usd_total, bool):
            raise TypeError("usd_total must be a number")
        if self.usd_total < 0:
            raise ValueError("usd_total must be >= 0")
        if not isinstance(self.usd_per_call, (int, float)) or isinstance(self.usd_per_call, bool):
            raise TypeError("usd_per_call must be a number")
        if self.usd_per_call < 0:
            raise ValueError("usd_per_call must be >= 0")

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.usd_total - self.spent_usd)

    def consume(self, usd: float) -> None:
        """Record a charge. Raise `BudgetExceeded` if it would exceed any cap.

        The charge is NOT recorded when an exception is raised — so a caller
        can catch `BudgetExceeded` and the Budget state stays consistent.
        """
        if not isinstance(usd, (int, float)) or isinstance(usd, bool):
            raise TypeError("usd must be a number")
        if usd < 0:
            raise ValueError("usd must be >= 0")
        if usd > self.usd_per_call:
            raise BudgetExceeded(
                f"single call cost ${usd:.4f} > per-call cap ${self.usd_per_call:.4f}",
                spent_usd=self.spent_usd,
                cap_usd=self.usd_per_call,
            )
        if self.spent_usd + usd > self.usd_total:
            raise BudgetExceeded(
                f"cumulative cost ${self.spent_usd + usd:.4f} "
                f"> total cap ${self.usd_total:.4f}",
                spent_usd=self.spent_usd + usd,
                cap_usd=self.usd_total,
            )
        self.spent_usd += usd

    def reset(self) -> None:
        """Zero out the spent-so-far counter (kept caps unchanged)."""
        self.spent_usd = 0.0


__all__ = ["Budget", "BudgetExceeded"]
