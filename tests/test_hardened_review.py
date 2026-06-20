"""The hardened reviewer must turn a wobbly model into a fail-closed verdict.

No network: we drive HardenedReviewer with deterministic and deliberately
flaky stub reviewers, and assert that instability, crashes, timeouts, and
malformed samples all resolve to DENY, while only a coherent, sufficient panel
approves.
"""
import time
import unittest

from governance import Action, ReviewPolicy
from governance.review import ReviewResult
from governance.reviewers import HardenedReviewer


def _action():
    return Action("agent-1", "send_money", value=900.0, risk=0.9)


def always_approve(action):
    return ReviewResult(True, "ok", "stub")


def always_deny(action):
    return ReviewResult(False, "no", "stub")


class _Flaky:
    """Approves and denies on an alternating, fully controllable schedule."""

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.i = 0

    def __call__(self, action):
        v = self.verdicts[self.i % len(self.verdicts)]
        self.i += 1
        return ReviewResult(v, "ok" if v else "no", "flaky")


class TestHardenedReviewer(unittest.TestCase):
    def test_unanimous_approve_passes(self):
        r = HardenedReviewer(always_approve, samples=3)(_action())
        self.assertTrue(r.approved)
        self.assertEqual(r.confidence, 1.0)

    def test_unanimous_deny_blocks(self):
        r = HardenedReviewer(always_deny, samples=3)(_action())
        self.assertFalse(r.approved)
        self.assertEqual(r.confidence, 0.0)

    def test_split_panel_is_unstable_and_blocks(self):
        # Two approve, one deny. Quorum of 2 would pass, but the default
        # stability_floor of 1.0 treats any split as a broken instrument.
        flaky = _Flaky([True, True, False])
        r = HardenedReviewer(flaky, samples=3, min_approvals=2)(_action())
        self.assertFalse(r.approved)
        self.assertTrue(r.reason.startswith("reviewer_unstable"))

    def test_quorum_with_relaxed_stability_can_pass(self):
        # Explicitly allow a 2/3 majority by lowering the stability floor.
        flaky = _Flaky([True, True, False])
        r = HardenedReviewer(flaky, samples=3, min_approvals=2,
                             stability_floor=0.6)(_action())
        self.assertTrue(r.approved)

    def test_crashing_sample_denies(self):
        def crash(action):
            raise RuntimeError("model down")
        r = HardenedReviewer(crash, samples=3)(_action())
        self.assertFalse(r.approved)

    def test_malformed_sample_denies(self):
        r = HardenedReviewer(lambda a: "yes", samples=3)(_action())
        self.assertFalse(r.approved)

    def test_timeout_denies(self):
        def slow(action):
            time.sleep(0.5)
            return ReviewResult(True, "ok", "slow")
        r = HardenedReviewer(slow, samples=2, timeout_s=0.05)(_action())
        self.assertFalse(r.approved)

    def test_drops_into_review_policy(self):
        hardened = HardenedReviewer(_Flaky([True, False]), samples=3,
                                    min_approvals=3)
        policy = ReviewPolicy([hardened], risk_threshold=0.5)
        approved, results = policy.run(_action())
        self.assertFalse(approved)


if __name__ == "__main__":
    unittest.main()
