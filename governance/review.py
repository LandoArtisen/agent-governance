"""Cross-model / independent review gate.

Generalized from the ConBot rule that a second, independent model had to
approve a consequential change before it shipped. The pattern that caught
real bugs: one model proposes, another must sign off, and if the reviewer
is unavailable or errors, the action is blocked, not waved through.

A Reviewer is any callable that takes an Action and returns a ReviewResult.
In production it is a second LLM with a skeptical prompt. Here it is a
plug-in, so the framework stays domain and vendor agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .types import Action


@dataclass
class ReviewResult:
    approved: bool
    reason: str = ""
    reviewer: str = "reviewer"


class Reviewer(Protocol):
    def __call__(self, action: Action) -> ReviewResult:  # pragma: no cover
        ...


class CallableReviewer:
    """Wrap a plain function as a Reviewer with a stable name."""

    def __init__(self, name: str, fn: Callable[[Action], bool | ReviewResult]):
        self.name = name
        self.fn = fn

    def __call__(self, action: Action) -> ReviewResult:
        out = self.fn(action)
        if isinstance(out, ReviewResult):
            return out
        return ReviewResult(approved=bool(out), reviewer=self.name)


class ReviewPolicy:
    """Decide when review is required and run it fail-closed.

    Review is required when the action's risk or value crosses a threshold.
    A quorum of reviewers must approve. Any reviewer that raises counts as a
    rejection, so a broken or unreachable reviewer can never approve by
    accident. Default approvals required is the full panel.
    """

    def __init__(self, reviewers: list[Reviewer] | None = None,
                 risk_threshold: float = 0.5, value_threshold: float | None = None,
                 min_approvals: int | None = None):
        self.reviewers = list(reviewers or [])
        self.risk_threshold = risk_threshold
        self.value_threshold = value_threshold
        self.min_approvals = (len(self.reviewers) if min_approvals is None else min_approvals)

    def required(self, action: Action) -> bool:
        if action.risk >= self.risk_threshold:
            return True
        if self.value_threshold is not None and action.value >= self.value_threshold:
            return True
        return False

    def run(self, action: Action) -> tuple[bool, list[ReviewResult]]:
        """Return (approved, results). Fail closed: no reviewers means no approval."""
        if not self.reviewers:
            return False, [ReviewResult(False, "no_reviewer_available", "panel")]
        results: list[ReviewResult] = []
        approvals = 0
        for r in self.reviewers:
            try:
                res = r(action)
                if not isinstance(res, ReviewResult):
                    res = ReviewResult(False, "invalid_review_result", "panel")
            except Exception as exc:  # noqa: BLE001 - a crashing reviewer rejects
                res = ReviewResult(False, f"reviewer_error:{type(exc).__name__}", "panel")
            results.append(res)
            if res.approved:
                approvals += 1
        return approvals >= self.min_approvals, results
