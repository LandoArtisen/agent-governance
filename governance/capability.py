"""Capability tokens: scoped, signed, revocable authority to act.

The registry answers "is this agent known and what may its class do". That is
static. A capability token answers a sharper question: "was this specific
action authorized, right now, by someone holding the key, and has that grant
been pulled". It is the difference between a name on a list and a key card that
an operator can deactivate in one move.

A token is signed with an HMAC secret only the authority holds, so it cannot be
forged or edited. It is scoped to one agent and a set of action kinds, it can
carry an expiry, and it can be revoked by id. The gate is fail closed: a
missing, malformed, unsigned, expired, revoked, wrong-agent, or out-of-scope
token blocks. Only a token that clears every one of those passes.

This is the runtime form of the delegatable-capability idea: revoke one token
and every pending action under it stops at the gate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .gates import Gate
from .safety import fail_closed, is_finite
from .types import Action, GateResult, Severity


@dataclass
class CapabilityToken:
    """A signed grant: this agent may take these kinds until it expires."""

    token_id: str
    agent_id: str
    kinds: list[str]
    issued_ts: float
    expires_ts: Optional[float] = None
    signature: str = ""

    def signing_payload(self) -> bytes:
        """The exact bytes the signature covers. Order is fixed and canonical."""
        body = {
            "token_id": self.token_id,
            "agent_id": self.agent_id,
            "kinds": sorted(self.kinds),
            "issued_ts": self.issued_ts,
            "expires_ts": self.expires_ts,
        }
        return json.dumps(body, sort_keys=True, default=str).encode("utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "agent_id": self.agent_id,
            "kinds": list(self.kinds),
            "issued_ts": self.issued_ts,
            "expires_ts": self.expires_ts,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CapabilityToken":
        return cls(
            token_id=str(d["token_id"]),
            agent_id=str(d["agent_id"]),
            kinds=list(d.get("kinds", [])),
            issued_ts=float(d["issued_ts"]),
            expires_ts=(float(d["expires_ts"]) if d.get("expires_ts") is not None else None),
            signature=str(d.get("signature", "")),
        )


class CapabilityAuthority:
    """Issues, verifies, and revokes capability tokens. Holds the secret key."""

    def __init__(self, secret: bytes | str):
        self._secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        self._revoked: set[str] = set()
        self._lock = threading.Lock()

    def _sign(self, token: CapabilityToken) -> str:
        return hmac.new(self._secret, token.signing_payload(), hashlib.sha256).hexdigest()

    def issue(self, agent_id: str, kinds: list[str],
              ttl_seconds: Optional[float] = None) -> CapabilityToken:
        """Mint a signed token for an agent and a set of action kinds."""
        now = time.time()
        token = CapabilityToken(
            token_id=uuid.uuid4().hex,
            agent_id=agent_id,
            kinds=list(kinds),
            issued_ts=now,
            expires_ts=(now + ttl_seconds) if ttl_seconds is not None else None,
        )
        token.signature = self._sign(token)
        return token

    def revoke(self, token_id: str) -> None:
        """Pull a token. Every later check against it fails closed."""
        with self._lock:
            self._revoked.add(token_id)

    def is_revoked(self, token_id: str) -> bool:
        return token_id in self._revoked

    def verify(self, token: CapabilityToken, action: Action,
               now: Optional[float] = None) -> tuple[bool, str]:
        """Return (ok, reason). Anything off blocks; only a clean token passes."""
        now = now if is_finite(now) else time.time()
        # Signature first: an unsigned or edited token is not ours, full stop.
        expected = self._sign(token)
        if not token.signature or not hmac.compare_digest(token.signature, expected):
            return False, "bad_signature"
        if self.is_revoked(token.token_id):
            return False, "revoked"
        if token.expires_ts is not None and now >= token.expires_ts:
            return False, "expired"
        if token.agent_id != action.agent_id:
            return False, "agent_mismatch"
        if action.kind not in set(token.kinds):
            return False, "kind_not_granted"
        return True, "ok"


class CapabilityGate(Gate):
    """Require a valid capability token in the action payload.

    Reads the token from `action.payload[payload_key]` (a dict produced by
    `CapabilityToken.to_dict()`). No token, or any token that does not verify,
    is a block. Slots into a cascade like any other gate.
    """

    name = "capability"

    def __init__(self, authority: CapabilityAuthority, payload_key: str = "capability"):
        self.authority = authority
        self.payload_key = payload_key

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        raw = action.payload.get(self.payload_key)
        if not isinstance(raw, dict):
            return self._block("missing_capability", self.payload_key, Severity.HIGH)
        try:
            token = CapabilityToken.from_dict(raw)
        except Exception:  # noqa: BLE001 - a malformed token is no token
            return self._block("malformed_capability", "", Severity.HIGH)
        ok, reason = self.authority.verify(token, action)
        if ok:
            return self._allow()
        return self._block(f"capability_{reason}", token.token_id, Severity.HIGH)
