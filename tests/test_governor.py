import unittest

from governance import (Action, AgentCard, Decision, Governor, Policy,
                        ReviewPolicy, ReviewResult, CallableReviewer)


def make_gov(review=None):
    policy = Policy(
        name="t", allowed_kinds=["search", "spend"],
        finite_fields={"value": [0.0, None]},
        budget_cap=10.0,
        review={"risk_threshold": 0.7},
    )
    gov = Governor(policy=policy, review=review or ReviewPolicy())
    gov.registry.register(AgentCard("a1", allowed_kinds=policy.allowed_kinds))
    return gov


class TestGovernor(unittest.TestCase):
    def test_allows_permitted_action(self):
        gov = make_gov()
        v = gov.govern(Action("a1", "search", value=1.0))
        self.assertTrue(v.allowed, v.summary())
        self.assertIsNotNone(v.audit_id)

    def test_unknown_agent_blocked(self):
        gov = make_gov()
        v = gov.govern(Action("ghost", "search", value=1.0))
        self.assertTrue(v.blocked)
        self.assertIn("unknown_agent", v.reasons)

    def test_unpermitted_kind_blocked(self):
        gov = make_gov()
        v = gov.govern(Action("a1", "delete", value=1.0))
        self.assertTrue(v.blocked)
        self.assertIn("kind_not_permitted", v.reasons)

    def test_budget_exceeded_blocked(self):
        gov = make_gov()
        self.assertTrue(gov.govern(Action("a1", "spend", value=8.0)).allowed)
        v = gov.govern(Action("a1", "spend", value=8.0))  # cumulative 16 > 10
        self.assertTrue(v.blocked)
        self.assertIn("budget_exceeded", v.reasons)

    def test_nonfinite_value_blocked(self):
        gov = make_gov()
        v = gov.govern(Action("a1", "spend", value=float("inf")))
        self.assertTrue(v.blocked)

    def test_review_required_and_rejected(self):
        rejecter = ReviewPolicy([CallableReviewer("skeptic", lambda a: False)],
                                risk_threshold=0.7)
        gov = make_gov(review=rejecter)
        v = gov.govern(Action("a1", "spend", value=1.0, risk=0.9))
        self.assertTrue(v.review_required)
        self.assertFalse(v.review_approved)
        self.assertTrue(v.blocked)

    def test_review_required_no_reviewer_fails_closed(self):
        gov = make_gov(review=ReviewPolicy([], risk_threshold=0.7))
        v = gov.govern(Action("a1", "spend", value=1.0, risk=0.95))
        self.assertTrue(v.blocked)
        self.assertIn("no_reviewer_available", v.reasons)

    def test_review_required_and_approved(self):
        ok = ReviewPolicy([CallableReviewer("ok", lambda a: ReviewResult(True))],
                          risk_threshold=0.7)
        gov = make_gov(review=ok)
        v = gov.govern(Action("a1", "spend", value=1.0, risk=0.9))
        self.assertTrue(v.review_approved)
        self.assertTrue(v.allowed)

    def test_crashing_reviewer_rejects(self):
        def boom(a):
            raise ValueError("nope")
        gov = make_gov(review=ReviewPolicy([CallableReviewer("x", boom)], risk_threshold=0.7))
        v = gov.govern(Action("a1", "spend", value=1.0, risk=0.9))
        self.assertTrue(v.blocked)

    def test_global_halt_blocks_all(self):
        gov = make_gov()
        gov.halt.engage("operator_kill")
        v = gov.govern(Action("a1", "search", value=1.0))
        self.assertTrue(v.blocked)
        self.assertIn("system_halted", v.reasons)

    def test_per_agent_halt(self):
        gov = make_gov()
        gov.registry.halt("a1")
        v = gov.govern(Action("a1", "search", value=1.0))
        self.assertTrue(v.blocked)
        self.assertIn("agent_halted", v.reasons)

    def test_governor_never_raises(self):
        gov = make_gov()
        # An action with a hostile payload must not crash the governor.
        bad = Action("a1", "search", payload={"x": object()}, value=float("nan"))
        v = gov.govern(bad)
        self.assertIs(v.decision, Decision.BLOCK)

    def test_audit_trail_records(self):
        gov = make_gov()
        gov.govern(Action("a1", "search", value=1.0))
        gov.govern(Action("a1", "delete", value=1.0))
        self.assertEqual(len(gov.audit.records()), 2)
        blocked = gov.audit.query(decision="block")
        self.assertEqual(len(blocked), 1)


if __name__ == "__main__":
    unittest.main()
