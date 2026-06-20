"""The per-dimension forced-choice reviewer must bind, not decorate.

All dimensions SAFE plus APPROVE passes. Any UNSAFE dimension overrides an
APPROVE (a self-contradiction fails closed). Old two-line replies still parse,
so the change is backward compatible.
"""
import unittest

from governance import Action, LLMReviewer
from governance.reviewers.llm import _parse

_FULL_SAFE = (
    "REVERSIBILITY: SAFE\nSCOPE: SAFE\nPROPORTIONALITY: SAFE\n"
    "SUFFICIENCY: SAFE\nVERDICT: APPROVE\nREASON: all clear"
)
_ONE_UNSAFE = (
    "REVERSIBILITY: SAFE\nSCOPE: UNSAFE\nPROPORTIONALITY: SAFE\n"
    "SUFFICIENCY: SAFE\nVERDICT: APPROVE\nREASON: model contradicts itself"
)


class TestDimensionParse(unittest.TestCase):
    def test_all_safe_and_approve_passes(self):
        self.assertTrue(_parse(_FULL_SAFE, "t").approved)

    def test_unsafe_dimension_overrides_approve(self):
        r = _parse(_ONE_UNSAFE, "t")
        self.assertFalse(r.approved)
        self.assertTrue(r.reason.startswith("unsafe_dimension:scope"))

    def test_explicit_deny_still_denies(self):
        self.assertFalse(_parse(_FULL_SAFE.replace("APPROVE", "DENY"), "t").approved)

    def test_legacy_two_line_reply_still_parses(self):
        self.assertTrue(_parse("VERDICT: APPROVE\nREASON: ok", "t").approved)

    def test_through_llmreviewer(self):
        action = Action("a1", "send_money", value=900.0, risk=0.9)
        approve = LLMReviewer("t", lambda s, u: _FULL_SAFE)(action)
        contradict = LLMReviewer("t", lambda s, u: _ONE_UNSAFE)(action)
        self.assertTrue(approve.approved)
        self.assertFalse(contradict.approved)


if __name__ == "__main__":
    unittest.main()
