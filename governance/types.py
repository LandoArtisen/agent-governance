"""Core domain-agnostic types for the governance layer.

These types replace the trading-specific objects in the original ConBot
system (a "trade") with a generic "Action" that any autonomous agent can
emit. Everything downstream, the gates, the halt engine, the review gate,
and the audit trail, operates on these types and knows nothing about the
domain.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Decision(str, Enum):
    """The only two outcomes. Default is BLOCK, never ALLOW.

    Deny by default is the core safety stance. Any path that does not
    explicitly and successfully produce ALLOW resolves to BLOCK.
    """

    ALLOW = "allow"
    BLOCK = "block"


class Severity(str, Enum):
    """How serious a block is. Mirrors the ConBot halt-engine escalation."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_SEV_ORDER = {
    Severity.NONE: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def max_severity(a: Severity, b: Severity) -> Severity:
    """Return the more severe of two severities."""
    return a if _SEV_ORDER[a] >= _SEV_ORDER[b] else b


@dataclass
class Action:
    """A single consequential thing an agent wants to do.

    The payload is opaque to the framework. Numeric fields that must be
    validated are named in the policy, not hard-coded here, so the same
    Action type covers a tool call, an API write, a message, or a trade.
    """

    agent_id: str
    kind: str                      # e.g. "tool_call", "send_email", "delete", "trade"
    payload: dict[str, Any] = field(default_factory=dict)
    risk: float = 0.0              # caller's own risk estimate, 0..1
    value: float = 0.0            # magnitude: cost, exposure, blast radius
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    ts: float = field(default_factory=time.time)


@dataclass
class GateResult:
    """The verdict from one gate."""

    gate: str
    decision: Decision
    reason: str = "ok"             # a stable machine-readable reason code
    detail: str = ""
    severity: Severity = Severity.NONE

    @property
    def blocked(self) -> bool:
        return self.decision is Decision.BLOCK


@dataclass
class Verdict:
    """The final, audited outcome of governing one action."""

    action_id: str
    decision: Decision
    severity: Severity = Severity.NONE
    gate_results: list[GateResult] = field(default_factory=list)
    review_required: bool = False
    review_approved: Optional[bool] = None
    audit_id: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def blocked(self) -> bool:
        return self.decision is Decision.BLOCK

    @property
    def reasons(self) -> list[str]:
        """Every blocking reason code, in order. The audit answer to 'why'."""
        return [g.reason for g in self.gate_results if g.blocked]

    def summary(self) -> str:
        if self.allowed:
            return f"ALLOW {self.action_id}"
        return f"BLOCK {self.action_id} [{self.severity.value}] {', '.join(self.reasons) or 'denied'}"
