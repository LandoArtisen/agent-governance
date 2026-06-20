"""governance: a domain-agnostic, fail-closed control layer for autonomous agents.

Extracted and generalized from the ConBot trading platform's governance
spine (the Penrose Governor gate cascade, the TradingHaltEngine kill switch,
the fail-closed gatekeeper, the cross-model review gate, and the decision
audit trail), with every trading assumption removed.

Quick start:

    from governance import Governor, Policy, Action, AgentCard

    policy = Policy(name="agent", allowed_kinds=["search", "read_file"],
                    budget_cap=10.0, review={"risk_threshold": 0.7})
    gov = Governor(policy=policy)
    gov.registry.register(AgentCard("agent-1", allowed_kinds=policy.allowed_kinds))

    verdict = gov.govern(Action(agent_id="agent-1", kind="search", value=1.0))
    if verdict.allowed:
        ...  # execute the tool call
"""
from __future__ import annotations

from .audit import AuditRecord, AuditTrail
from .gates import (BudgetGate, FiniteInputGate, Gate, GateCascade,
                    KillSwitchGate, PermissionGate, PredicateGate,
                    RateLimitGate, ThresholdGate)
from .governor import Governor
from .halt import HaltEngine, HaltState
from .policy import Policy
from .registry import AgentCard, AgentRegistry, AgentStatus
from .review import (CallableReviewer, Reviewer, ReviewPolicy, ReviewResult)
from .reviewers import LLMReviewer, anthropic_reviewer, openai_reviewer
from .safety import in_bounds, is_finite
from .types import (Action, Decision, GateResult, Severity, Verdict)

__version__ = "0.1.0"

__all__ = [
    "Governor", "Policy", "Action", "Verdict", "Decision", "Severity",
    "GateResult", "Gate", "GateCascade", "KillSwitchGate", "PermissionGate",
    "FiniteInputGate", "RateLimitGate", "BudgetGate", "ThresholdGate",
    "PredicateGate", "HaltEngine", "HaltState", "AuditTrail", "AuditRecord",
    "AgentRegistry", "AgentCard", "AgentStatus", "ReviewPolicy", "Reviewer",
    "ReviewResult", "CallableReviewer", "LLMReviewer", "anthropic_reviewer",
    "openai_reviewer", "is_finite", "in_bounds", "__version__",
]
