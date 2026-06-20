"""Hardened reviewer: a deterministic fail-closed gate over a stochastic one.

The cross-model review gate has a hidden weakness. A language model is not a
deterministic function. Ask it the same question twice and it can answer
APPROVE once and DENY the next time. A single call is a coin flip you are
treating as a verdict. You cannot prove a safety property on top of an
instrument that wobbles.

This wraps any `Reviewer` and turns it into one whose decision is safe to gate
on, using the same doctrine the halt engine applies to a metric: if the
instrument is unreliable, you do not trust it, you fail closed.

The mechanism, in one breath:

  1. Sample the inner reviewer N times, independently and concurrently.
  2. Every sample that raises, times out, or returns a malformed result is a
     DENY. A broken sample can never become an approval.
  3. Approve only if at least `min_approvals` of the N samples approve, AND
     the panel agrees with itself at least `stability_floor` of the time.
  4. A panel that is too split to meet `stability_floor` is DENIED as
     unstable, even when the approval count alone would have passed. Quorum is
     necessary but not sufficient: a wavering model is a broken instrument.
  5. The confidence (approvals / samples) is attached to the result so the
     caller can escalate severity when a borderline action only barely cleared.

The default is the strict one: three samples, unanimous approval required, any
split treated as instability. Loosen it deliberately, never by accident.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ..review import Reviewer, ReviewResult
from ..types import Action


def _coerce_deny(out: object, reason: str) -> ReviewResult:
    """Turn anything that is not a valid approving ReviewResult into a DENY."""
    if isinstance(out, ReviewResult):
        return out
    return ReviewResult(False, reason, "hardened")


class HardenedReviewer:
    """Make a non-deterministic reviewer safe to gate on. Fail closed throughout.

    Plugs in anywhere a `Reviewer` is accepted, including inside a
    `ReviewPolicy` panel, so you can stack hardened reviewers over several
    models. The wrapped reviewer is the only thing that touches a model, so
    this class is fully testable with a flaky stub.
    """

    def __init__(self, inner: Reviewer, *,
                 samples: int = 3,
                 min_approvals: Optional[int] = None,
                 stability_floor: float = 1.0,
                 timeout_s: Optional[float] = None,
                 name: str = "hardened"):
        if samples < 1:
            raise ValueError("samples must be >= 1")
        self.inner = inner
        self.samples = samples
        # Default: unanimity. Every sample must approve.
        self.min_approvals = samples if min_approvals is None else min_approvals
        # Self-agreement the panel must reach, as a fraction of samples. 1.0
        # means any dissent at all is treated as instability.
        self.stability_floor = stability_floor
        self.timeout_s = timeout_s
        self.name = name

    def _one_sample(self, action: Action) -> ReviewResult:
        """Run the inner reviewer once. Any failure is a DENY, never a raise."""
        try:
            out = self.inner(action)
        except Exception as exc:  # noqa: BLE001 - a crashing sample denies
            return ReviewResult(False, f"sample_error:{type(exc).__name__}", self.name)
        return _coerce_deny(out, "invalid_sample_result")

    def __call__(self, action: Action) -> ReviewResult:
        results: list[ReviewResult] = []
        # Run the samples concurrently, each under a shared deadline. A sample
        # that does not return in time is a DENY, exactly like a crash.
        deadline = None if self.timeout_s is None else time.monotonic() + self.timeout_s
        with ThreadPoolExecutor(max_workers=self.samples) as pool:
            futures = [pool.submit(self._one_sample, action) for _ in range(self.samples)]
            for fut in futures:
                remaining = None
                if deadline is not None:
                    remaining = max(0.0, deadline - time.monotonic())
                try:
                    results.append(fut.result(timeout=remaining))
                except Exception as exc:  # noqa: BLE001 - TimeoutError and any other
                    fut.cancel()
                    results.append(ReviewResult(
                        False, f"sample_timeout:{type(exc).__name__}", self.name))

        approvals = sum(1 for r in results if r.approved)
        n = self.samples
        confidence = approvals / n
        # How much the panel agrees with itself, regardless of direction.
        agreement = max(approvals, n - approvals) / n
        stable = agreement >= self.stability_floor
        quorum = approvals >= self.min_approvals

        if not stable:
            # The decisive case: the model wavered. Deny even if quorum was met.
            return ReviewResult(
                False, f"reviewer_unstable:{approvals}/{n}", self.name, confidence)
        if not quorum:
            return ReviewResult(
                False, f"insufficient_approvals:{approvals}/{self.min_approvals}",
                self.name, confidence)
        return ReviewResult(
            True, f"approved:{approvals}/{n}", self.name, confidence)
