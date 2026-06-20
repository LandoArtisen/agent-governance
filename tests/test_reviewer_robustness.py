"""Order/framing bias must surface as instability and fail closed.

A reviewer whose verdict depends on payload key order is order-biased. Sampling
across reorder_payload makes that flip show up in the same stability tripwire,
while an order-invariant reviewer is unaffected.
"""
import unittest

from governance import Action, HardenedReviewer, reorder_payload
from governance.review import ReviewResult


def order_biased(action):
    # Approves only when the first payload key is "a": a pure order artifact.
    keys = list(action.payload.keys())
    return ReviewResult(bool(keys) and keys[0] == "a", "ok", "biased")


def always_approve(action):
    return ReviewResult(True, "ok", "stub")


def _action():
    return Action("agent-1", "send_money", value=10.0, payload={"a": 1, "b": 2})


class TestReorderPayload(unittest.TestCase):
    def test_reverses_keys_and_lists_preserving_id(self):
        a = Action("x", "k", payload={"a": 1, "b": [1, 2, 3]})
        r = reorder_payload(a)
        self.assertEqual(list(r.payload.keys()), ["b", "a"])
        self.assertEqual(r.payload["b"], [3, 2, 1])
        self.assertEqual(r.action_id, a.action_id)


class TestPositionConsistency(unittest.TestCase):
    def test_order_bias_is_invisible_without_perturbation(self):
        r = HardenedReviewer(order_biased, samples=2)(_action())
        self.assertTrue(r.approved)

    def test_order_bias_is_caught_as_instability(self):
        r = HardenedReviewer(order_biased, samples=2,
                             perturbations=[reorder_payload])(_action())
        self.assertFalse(r.approved)
        self.assertTrue(r.reason.startswith("reviewer_unstable"))

    def test_invariant_reviewer_still_approves_with_perturbation(self):
        r = HardenedReviewer(always_approve, samples=2,
                             perturbations=[reorder_payload])(_action())
        self.assertTrue(r.approved)

    def test_broken_perturbation_fails_closed(self):
        def boom(action):
            raise RuntimeError("bad perturbation")
        r = HardenedReviewer(always_approve, samples=2,
                             perturbations=[boom])(_action())
        self.assertFalse(r.approved)
        self.assertTrue(r.reason.startswith("perturbation_error"))


if __name__ == "__main__":
    unittest.main()
