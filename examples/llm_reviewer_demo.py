"""Run the review gate against a REAL second model.

If ANTHROPIC_API_KEY is set, this governs a risky action with a live Claude
Haiku reviewer (the cheap, fast tier). If no key is present, it falls back to
a built-in stub reviewer so the demo still runs offline and in CI.

    export ANTHROPIC_API_KEY=...        # optional; uses a live Claude reviewer
    python3 examples/llm_reviewer_demo.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from governance import (Action, AgentCard, Governor, Policy, ReviewPolicy,  # noqa: E402
                        LLMReviewer)


def build_reviewer():
    """A live Claude reviewer if a key is present, else a fail-closed stub."""
    if os.getenv("ANTHROPIC_API_KEY"):
        from governance import anthropic_reviewer
        print("Reviewer: live Claude Haiku 4.5\n")
        return anthropic_reviewer(model="claude-haiku-4-5")

    print("Reviewer: offline stub (set ANTHROPIC_API_KEY for a live Claude reviewer)\n")

    def fake_model(system: str, user: str) -> str:
        # Stand in for the model: approve small refunds, deny big transfers.
        if "send_money" in user and "value (cost / blast radius): 9" in user:
            return "VERDICT: DENY\nREASON: transfer too large to auto-approve"
        return "VERDICT: APPROVE\nREASON: small and in scope"

    return LLMReviewer("stub", fake_model)


def main() -> None:
    policy = Policy(
        name="support-agent",
        allowed_kinds=["search", "send_money"],
        budget_cap=10_000.0,
        review={"risk_threshold": 0.6, "value_threshold": 100.0},
    )
    gov = Governor(policy=policy,
                   review=ReviewPolicy([build_reviewer()],
                                       risk_threshold=0.6, value_threshold=100.0))
    gov.registry.register(AgentCard("support-bot", allowed_kinds=policy.allowed_kinds))

    actions = [
        Action("support-bot", "send_money", value=25.0, risk=0.2,
               payload={"reason": "duplicate charge refund"}),
        Action("support-bot", "send_money", value=900.0, risk=0.8,
               payload={"reason": "manual transfer", "to": "external"}),
    ]
    for a in actions:
        v = gov.govern(a)
        print(f"${a.value:>7.2f}  ->  {v.summary()}")


if __name__ == "__main__":
    main()
