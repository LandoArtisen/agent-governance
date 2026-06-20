"""Launch the governance console with a pre-registered demo agent.

    python examples/run_console.py
    open http://127.0.0.1:8900

Serves both the built-in HTML console and the JSON API that the React
dashboard (in ./dashboard) also consumes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from governance import AgentCard, CallableReviewer, Governor, Policy, ReviewPolicy, ReviewResult
from governance.console import Console


def reviewer(action):
    # A stand-in for a second, independent model. Refuses large transfers.
    if action.kind == "send_money" and action.value > 100:
        return ReviewResult(False, "transfer_too_large_for_auto_approve", "reviewer-2")
    return ReviewResult(True, "looks_routine", "reviewer-2")


def build() -> Governor:
    policy = Policy(
        name="support-agent",
        allowed_kinds=["search", "read_doc", "send_email", "send_money"],
        finite_fields={"value": [0.0, None]},
        rate_limit={"max_actions": 100, "window_seconds": 60},
        budget_cap=2000.0,
        review={"risk_threshold": 0.6, "value_threshold": 100.0},
    )
    gov = Governor(
        policy=policy,
        review=ReviewPolicy([CallableReviewer("reviewer-2", reviewer)],
                            risk_threshold=0.6, value_threshold=100.0),
    )
    gov.registry.register(AgentCard(
        "support-bot", purpose="Answer tickets and issue small refunds",
        allowed_kinds=policy.allowed_kinds,
        data_sources=["zendesk", "billing_readonly"], policy=policy.name, calibration=0.82))
    gov.registry.register(AgentCard(
        "ops-bot", purpose="Run scheduled maintenance jobs",
        allowed_kinds=["search", "read_doc"], policy=policy.name, calibration=0.6))
    return gov


if __name__ == "__main__":
    Console(build()).serve(port=8900)
