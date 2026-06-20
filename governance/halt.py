"""Halt engine and kill switch.

Generalized from the ConBot TradingHaltEngine. It holds latched state, a
manual kill switch, and a set of metric tripwires. Two rules carry over:

  1. Fail closed on bad metrics. A missing, NaN, infinite, or negative
     metric does not get skipped, it halts. You cannot prove you are safe
     with a broken instrument.
  2. Latching. Once tripped, it stays engaged until an operator explicitly
     resets it. Halts do not silently clear themselves.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .safety import is_finite
from .types import Severity


@dataclass
class HaltState:
    engaged: bool = False
    reasons: list[str] = field(default_factory=list)
    severity: Severity = Severity.NONE
    since: float | None = None

    def as_dict(self) -> dict:
        return {"engaged": self.engaged, "reasons": list(self.reasons),
                "severity": self.severity.value, "since": self.since}


class HaltEngine:
    """Circuit breaker. Evaluate metrics against limits; latch on trip.

    `limits` maps a metric name to an upper bound. The canonical ConBot
    tripwires were drawdown_limit, gross_exposure_limit, and
    unrealized_drawdown_limit; here they are just named limits so the same
    engine governs error rates, spend, or anything else.
    """

    def __init__(self, limits: dict[str, float] | None = None):
        self.limits = dict(limits or {"drawdown": 0.10})
        self._state = HaltState()
        self._lock = threading.Lock()

    # --- manual control -------------------------------------------------
    def engage(self, reason: str = "manual_halt", severity: Severity = Severity.CRITICAL) -> None:
        with self._lock:
            self._state.engaged = True
            if reason not in self._state.reasons:
                self._state.reasons.append(reason)
            self._state.severity = severity
            self._state.since = self._state.since or time.time()

    def reset(self) -> None:
        """Operator-only. Clear the latch."""
        with self._lock:
            self._state = HaltState()

    def is_engaged(self) -> bool:
        return self._state.engaged

    @property
    def state(self) -> HaltState:
        return self._state

    # --- automatic tripwires -------------------------------------------
    def evaluate(self, metrics: dict[str, float]) -> HaltState:
        """Check metrics against limits. Latches; never un-trips itself."""
        reasons: list[str] = []
        severity = Severity.NONE
        for name, limit in self.limits.items():
            val = metrics.get(name, None)
            # Fail closed: a metric we cannot read is an automatic halt.
            if not is_finite(val):
                reasons.append(f"{name}_unreadable")
                severity = Severity.CRITICAL
                continue
            if float(val) < 0:
                reasons.append(f"{name}_negative")
                severity = Severity.CRITICAL
                continue
            if float(val) >= limit:
                reasons.append(f"{name}_limit")
                severity = Severity.CRITICAL if severity is Severity.NONE else severity
        with self._lock:
            if reasons:
                self._state.engaged = True
                for r in reasons:
                    if r not in self._state.reasons:
                        self._state.reasons.append(r)
                self._state.severity = severity
                self._state.since = self._state.since or time.time()
            return HaltState(self._state.engaged, list(self._state.reasons),
                             self._state.severity, self._state.since)
