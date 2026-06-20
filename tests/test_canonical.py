"""RFC 8785 JCS canonicalization must be stable and order-independent.

We check the spec-mandated shapes (sorted keys, compact output, ECMAScript
number formatting) and the property the audit chain depends on: two equal
records serialize and hash identically regardless of key insertion order.
"""
import unittest

from governance import canonical_hash, canonicalize


class TestCanonical(unittest.TestCase):
    def test_keys_are_sorted_and_output_is_compact(self):
        self.assertEqual(canonicalize({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_key_order_does_not_change_the_hash(self):
        a = {"x": 1, "y": [1, 2], "z": {"m": 1, "n": 2}}
        b = {"z": {"n": 2, "m": 1}, "y": [1, 2], "x": 1}
        self.assertEqual(canonical_hash(a), canonical_hash(b))

    def test_scalars(self):
        self.assertEqual(canonicalize(True), "true")
        self.assertEqual(canonicalize(False), "false")
        self.assertEqual(canonicalize(None), "null")
        self.assertEqual(canonicalize("hi"), '"hi"')

    def test_number_formatting_matches_ecmascript(self):
        self.assertEqual(canonicalize(1), "1")
        self.assertEqual(canonicalize(1.0), "1")          # trailing .0 dropped
        self.assertEqual(canonicalize(-0.0), "0")         # negative zero collapses
        self.assertEqual(canonicalize(1.5), "1.5")
        self.assertEqual(canonicalize(1000), "1000")

    def test_non_finite_is_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                canonicalize(bad)

    def test_nested_and_lists(self):
        self.assertEqual(canonicalize({"a": [1, {"c": 3, "b": 2}]}),
                         '{"a":[1,{"b":2,"c":3}]}')


if __name__ == "__main__":
    unittest.main()
