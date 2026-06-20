"""Fail-closed primitives.

This is the lesson the original ConBot gatekeeper learned the hard way.
A non-finite value (NaN, +Inf, -Inf) is neither <= 0 nor > 0, so it can
slip past naive magnitude checks and pass a gate that was meant to block
it. The fix, ported here, is to screen for finiteness FIRST, before any
comparison, and to treat anything non-finite as a hard block.

A real, legitimate quantity is always a finite number.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any


def is_finite(x: Any) -> bool:
    """True only if x is a real, finite number. Everything else is False.

    None, NaN, +/-Inf, booleans, strings, and unparseable values all
    return False so the caller can fail closed on them.
    """
    if x is None or isinstance(x, bool):
        return False
    if isinstance(x, Decimal):
        return x.is_finite()
    if isinstance(x, (int, float)):
        return math.isfinite(x)
    return False


def finite_or_none(x: Any) -> float | None:
    """Return x as a finite float, or None if it is not finite."""
    return float(x) if is_finite(x) else None


def in_bounds(x: Any, lo: float | None = None, hi: float | None = None) -> bool:
    """Finite AND within [lo, hi]. Non-finite always fails."""
    if not is_finite(x):
        return False
    v = float(x)
    if lo is not None and v < lo:
        return False
    if hi is not None and v > hi:
        return False
    return True


def fail_closed(fn):
    """Decorator: any exception inside a gate becomes a BLOCK, never a pass.

    A gate that crashes must not silently let the action through. We import
    the types lazily to avoid a circular import.
    """
    from functools import wraps
    from .types import GateResult, Decision, Severity

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - intentional catch-all, fail closed
            name = getattr(self, "name", fn.__qualname__)
            return GateResult(
                gate=name,
                decision=Decision.BLOCK,
                reason="gate_error",
                detail=f"{type(exc).__name__}: {exc}",
                severity=Severity.HIGH,
            )

    return wrapper
