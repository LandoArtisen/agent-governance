"""The LLM reviewer adapter must be fail-closed.

No network here: we drive LLMReviewer with stub completion functions and the
real ReviewPolicy, and assert that only an explicit APPROVE lets an action
through. A crash, a refusal, a malformed reply, or anything ambiguous denies.
"""
import unittest

from governance import Action, LLMReviewer, ReviewPolicy
from governance.reviewers.llm import _parse


def approve(system, user):
    return "VERDICT: APPROVE\nREASON: looks fine"


def deny(system, user):
    return "VERDICT: DENY\nREASON: too risky"


def crash(system, user):
    raise RuntimeError("model unreachable")


class TestLLMReviewer(unittest.TestCase):
    def _action(self):
        return Action("agent-1", "send_money", value=900.0, risk=0.9)

    def test_explicit_approve_passes(self):
        r = LLMReviewer("t", approve)(self._action())
        self.assertTrue(r.approved)

    def test_explicit_deny_blocks(self):
        r = LLMReviewer("t", deny)(self._action())
        self.assertFalse(r.approved)

    def test_crash_blocks(self):
        r = LLMReviewer("t", crash)(self._action())
        self.assertFalse(r.approved)
        self.assertTrue(r.reason.startswith("reviewer_error:"))

    def test_garbage_blocks(self):
        for bad in ["", "yes", "sure thing", "VERDICT:", "VERDICT: maybe",
                    "I approve of this", "APPROVE", "{}", "\n\n"]:
            r = LLMReviewer("t", lambda s, u, b=bad: b)(self._action())
            self.assertFalse(r.approved, f"{bad!r} must not approve")

    def test_parse_is_case_insensitive(self):
        self.assertTrue(_parse("verdict: approve\nreason: ok", "t").approved)
        self.assertFalse(_parse("Verdict: Deny", "t").approved)

    def test_drops_into_review_policy_fail_closed(self):
        # A crashing live reviewer inside the real policy still blocks.
        policy = ReviewPolicy([LLMReviewer("t", crash)], risk_threshold=0.5)
        approved, results = policy.run(self._action())
        self.assertFalse(approved)
        self.assertTrue(all(not r.approved for r in results))


if __name__ == "__main__":
    unittest.main()
