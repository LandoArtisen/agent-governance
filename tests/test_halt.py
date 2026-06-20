import unittest

from governance import HaltEngine, Severity


class TestHaltEngine(unittest.TestCase):
    def test_trips_on_limit(self):
        h = HaltEngine({"drawdown": 0.10})
        st = h.evaluate({"drawdown": 0.12})
        self.assertTrue(st.engaged)
        self.assertIn("drawdown_limit", st.reasons)

    def test_fail_closed_on_unreadable_metric(self):
        for bad in [float("nan"), float("inf"), None]:
            h = HaltEngine({"exposure": 1.0})
            st = h.evaluate({"exposure": bad})
            self.assertTrue(st.engaged, f"{bad!r} must halt")
            self.assertIn("exposure_unreadable", st.reasons)

    def test_fail_closed_on_missing_metric(self):
        h = HaltEngine({"exposure": 1.0})
        st = h.evaluate({})  # metric absent
        self.assertTrue(st.engaged)

    def test_negative_metric_halts(self):
        h = HaltEngine({"exposure": 1.0})
        st = h.evaluate({"exposure": -0.01})
        self.assertTrue(st.engaged)
        self.assertIn("exposure_negative", st.reasons)

    def test_latches_after_good_reading(self):
        h = HaltEngine({"drawdown": 0.10})
        h.evaluate({"drawdown": 0.5})        # trip
        st = h.evaluate({"drawdown": 0.0})   # now fine
        self.assertTrue(st.engaged, "halt must latch, not self-clear")

    def test_manual_engage_and_reset(self):
        h = HaltEngine()
        self.assertFalse(h.is_engaged())
        h.engage("operator_kill")
        self.assertTrue(h.is_engaged())
        self.assertEqual(h.state.severity, Severity.CRITICAL)
        h.reset()
        self.assertFalse(h.is_engaged())


if __name__ == "__main__":
    unittest.main()
