"""The Governor.

The single choke point every consequential agent action passes through. It
composes the registry, the halt engine, the policy cascade, the review gate,
and the audit trail into one call: govern(action) -> Verdict.

The whole object is wrapped so that any unexpected failure resolves to BLOCK.
There is no path that throws its way to an ALLOW.
"""
from __future__ import annotations

from typing import Any, Optional

from .audit import AuditTrail
from .gates import GateCascade
from .halt import HaltEngine
from .policy import Policy
from .registry import AgentRegistry
from .review import ReviewPolicy
from .types import Action, Decision, GateResult, Severity, Verdict, max_severity


class Governor:
    """Govern actions against a policy, a halt engine, review, and audit."""

    def __init__(self,
                 policy: Optional[Policy] = None,
                 cascade: Optional[GateCascade] = None,
                 registry: Optional[AgentRegistry] = None,
                 halt: Optional[HaltEngine] = None,
                 review: Optional[ReviewPolicy] = None,
                 audit: Optional[AuditTrail] = None,
                 require_registration: bool = True,
                 capability_authority: Any = None):
        if cascade is None:
            policy = policy or Policy()
            cascade = policy.build_cascade(capability_authority=capability_authority)
        self.policy = policy
        self.cascade = cascade
        self.registry = registry or AgentRegistry()
        self.halt = halt or HaltEngine()
        self.review = review or ReviewPolicy()
        self.audit = audit or AuditTrail()
        self.require_registration = require_registration

    def govern(self, action: Action, context: dict[str, Any] | None = None) -> Verdict:
        """Return an audited Verdict. Fail closed on any internal error."""
        try:
            return self._govern(action, context or {})
        except Exception as exc:  # noqa: BLE001 - the outer fail-closed backstop
            verdict = Verdict(
                action_id=getattr(action, "action_id", "unknown"),
                decision=Decision.BLOCK,
                severity=Severity.CRITICAL,
                gate_results=[GateResult("governor", Decision.BLOCK,
                                         "governor_error",
                                         f"{type(exc).__name__}: {exc}",
                                         Severity.CRITICAL)],
            )
            try:
                rec = self.audit.record(action, verdict, note="governor exception")
                verdict.audit_id = rec.audit_id
            except Exception:
                pass
            return verdict

    def _govern(self, action: Action, context: dict[str, Any]) -> Verdict:
        # 1. Global kill switch wins over everything.
        if self.halt.is_engaged():
            return self._finalize(action, Verdict(
                action.action_id, Decision.BLOCK, Severity.CRITICAL,
                [GateResult("halt_engine", Decision.BLOCK, "system_halted",
                            ",".join(self.halt.state.reasons), Severity.CRITICAL)]))

        # 2. Deny by default for unknown or benched agents.
        if self.require_registration and not self.registry.is_known(action.agent_id):
            return self._finalize(action, Verdict(
                action.action_id, Decision.BLOCK, Severity.HIGH,
                [GateResult("registry", Decision.BLOCK, "unknown_agent",
                            action.agent_id, Severity.HIGH)]))
        if self.registry.is_halted(action.agent_id):
            return self._finalize(action, Verdict(
                action.action_id, Decision.BLOCK, Severity.CRITICAL,
                [GateResult("registry", Decision.BLOCK, "agent_halted",
                            action.agent_id, Severity.CRITICAL)]))

        # 3. Run the policy cascade with halt context.
        ctx = dict(context)
        ctx.setdefault("halted", self.halt.is_engaged())
        ctx.setdefault("halted_agents", self.registry.halted_agents())
        verdict = self.cascade.evaluate(action, ctx)

        # 4. If the cascade allowed, apply review where required.
        if verdict.allowed and self.review.required(action):
            verdict.review_required = True
            approved, results = self.review.run(action)
            verdict.review_approved = approved
            if not approved:
                why = next((r.reason for r in results if not r.approved), "review_denied")
                verdict.decision = Decision.BLOCK
                verdict.severity = max_severity(verdict.severity, Severity.HIGH)
                verdict.gate_results.append(
                    GateResult("review", Decision.BLOCK, why, "", Severity.HIGH))

        return self._finalize(action, verdict)

    def _finalize(self, action: Action, verdict: Verdict) -> Verdict:
        rec = self.audit.record(action, verdict)
        verdict.audit_id = rec.audit_id
        return verdict
