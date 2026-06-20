"""Gates and the fail-closed cascade.

A gate inspects one action and returns a GateResult. The cascade runs a
list of gates and aggregates them with two invariants ported straight from
the ConBot Penrose Governor:

  1. Deny by default. The action is ALLOW only if every gate explicitly
     allows it. Any block, any unknown verdict, blocks.
  2. Fail closed. A gate that raises, or returns something that is not a
     valid GateResult, is treated as a block, not a pass.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Any, Callable, Iterable

from .safety import fail_closed, in_bounds, is_finite
from .types import Action, Decision, GateResult, Severity, Verdict, max_severity


class Gate(ABC):
    """Base gate. Subclasses implement check(); the cascade wraps it."""

    name: str = "gate"

    @abstractmethod
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:  # pragma: no cover
        ...

    def _allow(self) -> GateResult:
        return GateResult(self.name, Decision.ALLOW)

    def _block(self, reason: str, detail: str = "", severity: Severity = Severity.MEDIUM) -> GateResult:
        return GateResult(self.name, Decision.BLOCK, reason, detail, severity)


class KillSwitchGate(Gate):
    """Hard block when the kill switch is engaged. The highest authority gate.

    Reads `context['halted']` (global) and a per-agent halt set. Critical.
    """

    name = "kill_switch"

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        if context.get("halted"):
            return self._block("kill_switch_engaged", "global halt active", Severity.CRITICAL)
        halted_agents = context.get("halted_agents") or set()
        if action.agent_id in halted_agents:
            return self._block("agent_halted", action.agent_id, Severity.CRITICAL)
        return self._allow()


class PermissionGate(Gate):
    """Deny by default on capability. The agent may only do allowed kinds.

    `allowed_kinds` empty means nothing is permitted (the safe default).
    """

    name = "permission"

    def __init__(self, allowed_kinds: Iterable[str]):
        self.allowed_kinds = set(allowed_kinds)

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        if action.kind in self.allowed_kinds:
            return self._allow()
        return self._block("kind_not_permitted", action.kind, Severity.MEDIUM)


class FiniteInputGate(Gate):
    """Block non-finite or out-of-bounds numeric inputs, screened first.

    `fields` maps a payload key (plus the synthetic keys 'risk' and 'value')
    to an optional (lo, hi) bound. Missing required fields block.
    """

    name = "finite_input"

    def __init__(self, fields: dict[str, tuple[float | None, float | None]]):
        self.fields = fields

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        for key, (lo, hi) in self.fields.items():
            if key == "risk":
                val = action.risk
            elif key == "value":
                val = action.value
            elif key in action.payload:
                val = action.payload[key]
            else:
                return self._block("missing_field", key, Severity.HIGH)
            if not is_finite(val):
                return self._block("non_finite", f"{key}={val!r}", Severity.HIGH)
            if not in_bounds(val, lo, hi):
                return self._block("out_of_bounds", f"{key}={val} not in [{lo},{hi}]", Severity.MEDIUM)
        return self._allow()


class RateLimitGate(Gate):
    """Block an agent that exceeds max_actions within window_seconds."""

    name = "rate_limit"

    def __init__(self, max_actions: int, window_seconds: float):
        self.max_actions = max_actions
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        now = action.ts or time.time()
        q = self._hits[action.agent_id]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_actions:
            return self._block("rate_limited", f"{len(q)}/{self.max_actions} in {self.window}s", Severity.MEDIUM)
        q.append(now)
        return self._allow()


class BudgetGate(Gate):
    """Block when cumulative action.value for an agent exceeds a cap.

    Generalizes the ConBot per-model daily fee budget and exposure caps.
    """

    name = "budget"

    def __init__(self, cap: float):
        self.cap = cap
        self._spent: dict[str, float] = defaultdict(float)

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        if not is_finite(action.value):
            return self._block("non_finite_value", repr(action.value), Severity.HIGH)
        projected = self._spent[action.agent_id] + max(0.0, float(action.value))
        if projected > self.cap:
            return self._block("budget_exceeded", f"{projected:.4g} > {self.cap:.4g}", Severity.MEDIUM)
        self._spent[action.agent_id] = projected
        return self._allow()


class ThresholdGate(Gate):
    """Require a context confidence/score at or above a floor.

    The generic form of the ConBot edge_gate: do not act on a weak signal.
    """

    name = "threshold"

    def __init__(self, field_key: str, floor: float):
        self.field_key = field_key
        self.floor = floor

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        val = action.payload.get(self.field_key, context.get(self.field_key))
        if not is_finite(val):
            return self._block("non_finite_score", f"{self.field_key}={val!r}", Severity.HIGH)
        if float(val) < self.floor:
            return self._block("below_threshold", f"{val} < {self.floor}", Severity.LOW)
        return self._allow()


class PredicateGate(Gate):
    """Escape hatch: a custom rule as a callable returning (allow, reason).

    The callable is wrapped fail-closed, so a crashing predicate blocks.
    """

    def __init__(self, name: str, predicate: Callable[[Action, dict], tuple[bool, str]],
                 severity: Severity = Severity.MEDIUM):
        self.name = name
        self.predicate = predicate
        self.severity = severity

    @fail_closed
    def check(self, action: Action, context: dict[str, Any]) -> GateResult:
        ok, reason = self.predicate(action, context)
        return self._allow() if ok else self._block(reason or "predicate_denied", severity=self.severity)


class GateCascade:
    """Run gates in order, deny by default, fail closed, aggregate reasons."""

    def __init__(self, gates: list[Gate], stop_on_critical: bool = True):
        self.gates = list(gates)
        self.stop_on_critical = stop_on_critical

    def evaluate(self, action: Action, context: dict[str, Any] | None = None) -> Verdict:
        context = context or {}
        results: list[GateResult] = []
        severity = Severity.NONE
        decision = Decision.ALLOW  # provisional; any block flips it
        for gate in self.gates:
            gate_name = getattr(gate, "name", "unknown")
            # Fail closed at the cascade level too: a gate that raises, even an
            # undecorated custom one, becomes a block, never an uncaught crash.
            try:
                res = gate.check(action, context)
            except Exception as exc:  # noqa: BLE001 - intentional, fail closed
                res = GateResult(gate_name, Decision.BLOCK, "gate_exception",
                                 f"{type(exc).__name__}: {exc}", Severity.HIGH)
            # Deny by default: an invalid return type is a block.
            if not isinstance(res, GateResult):
                res = GateResult(getattr(gate, "name", "unknown"),
                                 Decision.BLOCK, "invalid_gate_result",
                                 repr(res), Severity.HIGH)
            results.append(res)
            if res.blocked:
                decision = Decision.BLOCK
                severity = max_severity(severity, res.severity)
                if self.stop_on_critical and res.severity is Severity.CRITICAL:
                    break
        return Verdict(action_id=action.action_id, decision=decision,
                       severity=severity, gate_results=results)
