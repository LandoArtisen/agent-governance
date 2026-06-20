"""Capability tokens must be unforgeable, scoped, expiring, and revocable.

The gate is fail closed: a missing, forged, expired, revoked, wrong-agent, or
out-of-scope token blocks. Only a clean token from the authority passes.
"""
import time
import unittest

from governance import (Action, CapabilityAuthority, CapabilityGate,
                        CapabilityToken, Governor, Policy)


def _action_with(token, agent_id="a1", kind="send_money"):
    payload = {"capability": token.to_dict()} if token else {}
    return Action(agent_id, kind, value=10.0, payload=payload)


class TestCapability(unittest.TestCase):
    def setUp(self):
        self.auth = CapabilityAuthority("super-secret-key")
        self.gate = CapabilityGate(self.auth)

    def _ok(self, action):
        return self.gate.check(action, {}).decision.value == "allow"

    def test_valid_token_passes(self):
        tok = self.auth.issue("a1", ["send_money"])
        self.assertTrue(self._ok(_action_with(tok)))

    def test_missing_token_blocks(self):
        self.assertFalse(self._ok(_action_with(None)))

    def test_forged_signature_blocks(self):
        tok = self.auth.issue("a1", ["send_money"])
        tok.signature = "deadbeef" * 8
        self.assertFalse(self._ok(_action_with(tok)))

    def test_edited_scope_blocks(self):
        # Widen the grant after signing: the signature no longer matches.
        tok = self.auth.issue("a1", ["search"])
        tok.kinds = ["search", "send_money"]
        self.assertFalse(self._ok(_action_with(tok)))

    def test_wrong_agent_blocks(self):
        tok = self.auth.issue("a1", ["send_money"])
        self.assertFalse(self._ok(_action_with(tok, agent_id="a2")))

    def test_out_of_scope_kind_blocks(self):
        tok = self.auth.issue("a1", ["search"])
        self.assertFalse(self._ok(_action_with(tok, kind="send_money")))

    def test_expired_token_blocks(self):
        tok = self.auth.issue("a1", ["send_money"], ttl_seconds=-1.0)
        self.assertFalse(self._ok(_action_with(tok)))

    def test_revoked_token_blocks(self):
        tok = self.auth.issue("a1", ["send_money"])
        self.assertTrue(self._ok(_action_with(tok)))
        self.auth.revoke(tok.token_id)
        self.assertFalse(self._ok(_action_with(tok)))

    def test_wires_into_governor(self):
        policy = Policy(allowed_kinds=["send_money"])
        gov = Governor(policy=policy, require_registration=False,
                       capability_authority=self.auth)
        tok = self.auth.issue("a1", ["send_money"])
        self.assertTrue(gov.govern(_action_with(tok)).allowed)
        # No token, blocked even though permission allows the kind.
        self.assertFalse(gov.govern(_action_with(None)).allowed)
        # Revoke mid-flight: every later action under it stops.
        self.auth.revoke(tok.token_id)
        self.assertFalse(gov.govern(_action_with(tok)).allowed)


if __name__ == "__main__":
    unittest.main()
