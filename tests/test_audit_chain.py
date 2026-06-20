"""The audit trail must be tamper-evident, not just append-only.

We govern a few actions, confirm the chain verifies, then mutate and delete
records out from under it and assert verify_chain() catches each one and points
at the right spot.
"""
import unittest

from governance import Action, Governor, Policy
from governance.audit import GENESIS_HASH


def _gov():
    policy = Policy(allowed_kinds=["search", "send_money"], budget_cap=1000.0)
    gov = Governor(policy=policy, require_registration=False)
    return gov


class TestAuditChain(unittest.TestCase):
    def _populate(self, gov):
        gov.govern(Action("a1", "search", value=1.0))
        gov.govern(Action("a1", "send_money", value=50.0))
        gov.govern(Action("a1", "search", value=1.0))

    def test_clean_chain_verifies(self):
        gov = _gov()
        self._populate(gov)
        ok, problems = gov.audit.verify_chain()
        self.assertTrue(ok, problems)
        self.assertEqual(problems, [])

    def test_empty_chain_is_valid(self):
        ok, problems = _gov().audit.verify_chain()
        self.assertTrue(ok)

    def test_first_record_links_to_genesis(self):
        gov = _gov()
        self._populate(gov)
        self.assertEqual(gov.audit.records()[0].prev_hash, GENESIS_HASH)

    def test_each_link_points_at_prior_entry(self):
        gov = _gov()
        self._populate(gov)
        recs = gov.audit.records()
        for prev, cur in zip(recs, recs[1:]):
            self.assertEqual(cur.prev_hash, prev.entry_hash)

    def test_mutated_field_is_detected(self):
        gov = _gov()
        self._populate(gov)
        # Reach in and forge a decision after the fact (was "allow").
        gov.audit._records[1].decision = "block"
        ok, problems = gov.audit.verify_chain()
        self.assertFalse(ok)
        self.assertTrue(any("content altered" in p for p in problems))

    def test_deleted_record_breaks_the_chain(self):
        gov = _gov()
        self._populate(gov)
        del gov.audit._records[1]
        ok, problems = gov.audit.verify_chain()
        self.assertFalse(ok)
        self.assertTrue(any("broken link" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
