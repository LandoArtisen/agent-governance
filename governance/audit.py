"""Audit trail.

Every governed action produces one append-only record: what was attempted,
who attempted it, the decision, the reason codes, the review outcome, and a
digest of the payload so the trail is queryable without storing raw secrets.
This is the trace-level evidence layer. If you cannot prove afterward what an
agent did and why it was allowed or blocked, you are not governing it.

The records are hash-chained. Each one carries the hash of the record before it
and a hash of its own contents, so the trail is tamper-evident: change a field
or delete a record from the middle and `verify_chain()` reports exactly where
the chain broke. An append-only list alone cannot prove that nothing was
quietly removed; the chain can.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .canonical import canonical_hash
from .types import Action, Verdict

# The hash that precedes the very first record. A fixed, well-known anchor so
# the genesis link is verifiable and not just "whatever was there first".
GENESIS_HASH = "0" * 64


def _digest(payload: dict[str, Any]) -> str:
    """Stable short hash of the payload. Provenance without exposure."""
    try:
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        blob = repr(payload).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


@dataclass
class AuditRecord:
    audit_id: str
    ts: float
    agent_id: str
    action_id: str
    action_kind: str
    decision: str
    severity: str
    reasons: list[str]
    review_required: bool
    review_approved: Optional[bool]
    payload_digest: str
    note: str = ""
    prev_hash: str = GENESIS_HASH
    entry_hash: str = ""

    def content_hash(self) -> str:
        """SHA-256 of every field except entry_hash itself, including prev_hash.

        Recomputing this and comparing to the stored entry_hash is how a
        mutated record is caught; including prev_hash is what binds each record
        to its predecessor so a deletion cannot be hidden. The body is
        serialized with RFC 8785 JCS, so the digest is identical no matter which
        implementation or language computed it.
        """
        body = {k: v for k, v in asdict(self).items() if k != "entry_hash"}
        return canonical_hash(body)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class AuditTrail:
    """In-memory append-only log with optional JSONL file sink."""

    def __init__(self, sink_path: str | None = None):
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()
        self.sink_path = sink_path
        self._last_hash = GENESIS_HASH

    def record(self, action: Action, verdict: Verdict, note: str = "") -> AuditRecord:
        rec = AuditRecord(
            audit_id=uuid.uuid4().hex[:16],
            ts=time.time(),
            agent_id=action.agent_id,
            action_id=action.action_id,
            action_kind=action.kind,
            decision=verdict.decision.value,
            severity=verdict.severity.value,
            reasons=list(verdict.reasons),
            review_required=verdict.review_required,
            review_approved=verdict.review_approved,
            payload_digest=_digest(action.payload),
            note=note,
        )
        # Chain it: link to the prior record, then seal this record's contents.
        # Both happen under the lock so concurrent records cannot interleave and
        # fork the chain.
        with self._lock:
            rec.prev_hash = self._last_hash
            rec.entry_hash = rec.content_hash()
            self._last_hash = rec.entry_hash
            self._records.append(rec)
            if self.sink_path:
                with open(self.sink_path, "a", encoding="utf-8") as fh:
                    fh.write(rec.to_json() + "\n")
        return rec

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Re-walk the chain and report any tampering. (ok, problems).

        Catches three things an append-only list cannot: a mutated field (the
        record no longer hashes to its sealed entry_hash), a deleted or
        reordered record (a prev_hash that does not point at the record before
        it), and a broken genesis link. An empty trail is trivially valid.
        """
        problems: list[str] = []
        expected_prev = GENESIS_HASH
        with self._lock:
            records = list(self._records)
        for i, rec in enumerate(records):
            if rec.content_hash() != rec.entry_hash:
                problems.append(f"record {i} ({rec.audit_id}): content altered")
            if rec.prev_hash != expected_prev:
                problems.append(
                    f"record {i} ({rec.audit_id}): broken link, "
                    f"expected prev {expected_prev[:12]} got {rec.prev_hash[:12]}")
            expected_prev = rec.entry_hash
        return (not problems), problems

    def records(self) -> list[AuditRecord]:
        return list(self._records)

    def export_jsonl(self) -> str:
        return "\n".join(r.to_json() for r in self._records)

    def query(self, agent_id: str | None = None, decision: str | None = None) -> list[AuditRecord]:
        out = self._records
        if agent_id is not None:
            out = [r for r in out if r.agent_id == agent_id]
        if decision is not None:
            out = [r for r in out if r.decision == decision]
        return list(out)
