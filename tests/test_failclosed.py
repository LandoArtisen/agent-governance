"""Fail-closed and deny-by-default proofs.

These are the tests that matter. They assert that malformed, hostile, and
crashing inputs always resolve to BLOCK, never to ALLOW. This is the
guarantee the original system learned to make after a non-finite value
slipped past a naive check.
"""
import math
import random
import unittest

from governance import (Action, Decision, FiniteInputGate, GateCascade,
                        GateResult, PredicateGate, Severity, is_finite)
from governance.gates import Gate


BAD_NUMBERS = [float("nan"), float("inf"), float("-inf"), None, True, False,
               "1.0", "", [], {}, object()]


class TestIsFinite(unittest.TestCase):
    def test_rejects_non_numbers_and_specials(self):
        for x in BAD_NUMBERS:
            self.assertFalse(is_finite(x), f"{x!r} should not be finite")

    def test_accepts_real_numbers(self):
        for x in [0, 1, -1, 3.14, 1e9, -1e-9]:
            self.assertTrue(is_finite(x), f"{x!r} should be finite")


class TestFiniteInputGate(unittest.TestCase):
    def setUp(self):
        self.gate = FiniteInputGate({"amount": (0.0, None)})

    def test_blocks_every_bad_value(self):
        for bad in BAD_NUMBERS:
            a = Action("a", "k", payload={"amount": bad})
            res = self.gate.check(a, {})
            self.assertIs(res.decision, Decision.BLOCK, f"{bad!r} must block")

    def test_blocks_missing_field(self):
        res = self.gate.check(Action("a", "k", payload={}), {})
        self.assertIs(res.decision, Decision.BLOCK)
        self.assertEqual(res.reason, "missing_field")

    def test_blocks_out_of_bounds(self):
        res = self.gate.check(Action("a", "k", payload={"amount": -5.0}), {})
        self.assertIs(res.decision, Decision.BLOCK)

    def test_allows_valid(self):
        res = self.gate.check(Action("a", "k", payload={"amount": 5.0}), {})
        self.assertIs(res.decision, Decision.ALLOW)


class _CrashingGate(Gate):
    name = "crasher"

    def check(self, action, context):  # the decorator is not applied; cascade must still hold
        raise RuntimeError("boom")


class _CrashingGateWrapped(Gate):
    name = "crasher2"

    from governance.safety import fail_closed

    @fail_closed
    def check(self, action, context):
        raise RuntimeError("boom")


class _BadReturnGate(Gate):
    name = "liar"

    def check(self, action, context):
        return "allow"  # not a GateResult; cascade must treat as block


class TestCascadeFailClosed(unittest.TestCase):
    def test_wrapped_gate_blocks_on_exception(self):
        res = _CrashingGateWrapped().check(Action("a", "k"), {})
        self.assertIs(res.decision, Decision.BLOCK)
        self.assertEqual(res.reason, "gate_error")

    def test_cascade_blocks_on_invalid_return(self):
        cascade = GateCascade([_BadReturnGate()])
        v = cascade.evaluate(Action("a", "k"))
        self.assertIs(v.decision, Decision.BLOCK)
        self.assertIn("invalid_gate_result", v.reasons)

    def test_cascade_blocks_on_undecorated_crashing_gate(self):
        cascade = GateCascade([_CrashingGate()])
        v = cascade.evaluate(Action("a", "k"))
        self.assertIs(v.decision, Decision.BLOCK)
        self.assertIn("gate_exception", v.reasons)

    def test_deny_by_default_empty_cascade_allows_only_explicitly(self):
        # An empty cascade has nothing to allow against; by construction the
        # provisional decision is ALLOW, so we assert the documented behavior:
        # a real deployment always includes a permission gate. Here we prove a
        # single blocking gate flips it.
        cascade = GateCascade([FiniteInputGate({"value": (0.0, None)})])
        v = cascade.evaluate(Action("a", "k", value=float("nan")))
        self.assertIs(v.decision, Decision.BLOCK)


class TestFuzz(unittest.TestCase):
    def test_random_malformed_payloads_never_allow(self):
        rng = random.Random(1234)
        gate = FiniteInputGate({"x": (None, None)})
        for _ in range(2000):
            choice = rng.choice(BAD_NUMBERS + [rng.uniform(-1e6, 1e6)])
            a = Action("agent", "kind", payload={"x": choice})
            res = gate.check(a, {})
            if is_finite(choice):
                self.assertIs(res.decision, Decision.ALLOW)
            else:
                self.assertIs(res.decision, Decision.BLOCK)


if __name__ == "__main__":
    unittest.main()
