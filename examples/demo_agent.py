"""Demo: govern a generic tool-calling agent.

No trading, no API keys, no real LLM required. This shows the governance
layer wrapping an autonomous agent's tool calls. Every action the agent
proposes passes through one choke point, the Governor, which allows the
safe ones and blocks the dangerous ones with a reason and an audit record.

Run:  python examples/demo_agent.py
"""
import os
import sys

# Make the package importable when run from the repo without installing it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from governance import (Action, AgentCard, CallableReviewer, Governor, Policy,
                        ReviewPolicy, ReviewResult)


def skeptical_reviewer(action: Action) -> ReviewResult:
    """Stand-in for a second, independent model reviewing a risky action.

    In production this is a different LLM with a prompt that tries to refute
    the action. Here it approves a small refund and refuses a large transfer.
    """
    if action.kind == "send_money" and action.value > 100:
        return ReviewResult(False, "transfer_too_large_for_auto_approve", "reviewer-2")
    return ReviewResult(True, "looks_routine", "reviewer-2")


def build_governor() -> Governor:
    # Declarative policy. A governance owner could keep this in a JSON file.
    policy = Policy(
        name="support-agent",
        version=1,
        allowed_kinds=["search", "read_doc", "send_email", "send_money"],
        finite_fields={"value": [0.0, None]},   # money/cost must be finite and >= 0
        rate_limit={"max_actions": 50, "window_seconds": 60},
        budget_cap=2000.0,                       # total spend per agent
        review={"risk_threshold": 0.6, "value_threshold": 100.0},
    )
    review = ReviewPolicy(
        reviewers=[CallableReviewer("reviewer-2", skeptical_reviewer)],
        risk_threshold=0.6, value_threshold=100.0,
    )
    gov = Governor(policy=policy, review=review)
    gov.registry.register(AgentCard(
        agent_id="support-bot",
        purpose="Answer customer tickets and issue small refunds",
        allowed_kinds=policy.allowed_kinds,
        data_sources=["zendesk", "billing_readonly"],
        policy=policy.name,
        calibration=0.82,
    ))
    return gov


def show(gov: Governor, action: Action, label: str):
    v = gov.govern(action)
    mark = "ALLOW " if v.allowed else "BLOCK "
    why = "" if v.allowed else "  ->  " + ", ".join(v.reasons)
    extra = "  (reviewed)" if v.review_required else ""
    print(f"  {mark}{label:<34}{extra}{why}")


def main():
    gov = build_governor()
    print("\nGoverning a customer-support agent. One choke point, deny by default.\n")

    show(gov, Action("support-bot", "search", value=0.0), "search the knowledge base")
    show(gov, Action("support-bot", "send_email", value=0.0), "email the customer")
    show(gov, Action("support-bot", "send_money", value=15.0, risk=0.3), "refund $15 (routine)")
    show(gov, Action("support-bot", "send_money", value=60.0, risk=0.7), "pay vendor $60 (review approves)")
    show(gov, Action("support-bot", "send_money", value=900.0, risk=0.8), "transfer $900 (review rejects)")
    show(gov, Action("support-bot", "delete_account", value=0.0), "delete the account (not permitted)")
    show(gov, Action("support-bot", "send_money", value=float("inf")), "refund of infinity (malformed)")
    show(gov, Action("ghost-bot", "search", value=0.0), "action from an unregistered agent")

    print("\n  Operator trips the kill switch...\n")
    gov.halt.engage("operator_kill")
    show(gov, Action("support-bot", "search", value=0.0), "search after kill switch")

    print("\nAudit trail (every decision is recorded and queryable):")
    for r in gov.audit.records():
        print(f"  {r.ts:.0f}  {r.action_kind:<16} {r.decision:<6} {','.join(r.reasons) or 'ok'}")
    print(f"\n  {len(gov.audit.query(decision='block'))} blocked, "
          f"{len(gov.audit.query(decision='allow'))} allowed, "
          f"{len(gov.audit.records())} total.\n")


if __name__ == "__main__":
    main()
