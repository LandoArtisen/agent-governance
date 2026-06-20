"""Audit trail.

Every governed action produces one append-only record: what was attempted,
who attempted it, the decision, the reason codes, the review outcome, and a
digest of the payload so the trail is queryable without storing raw secrets.
This is the trace-level evidence layer. If you cannot prove afterward what an
agent did and why it was allowed or blocked, you are not governing it.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .types import Action, Verdict


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

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class AuditTrail:
    """In-memory append-only log with optional JSONL file sink."""

    def __init__(self, sink_path: str | None = None):
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()
        self.sink_path = sink_path

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
        with self._lock:
            self._records.append(rec)
            if self.sink_path:
                with open(self.sink_path, "a", encoding="utf-8") as fh:
                    fh.write(rec.to_json() + "\n")
        return rec

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
