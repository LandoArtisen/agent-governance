"""Declarative policy.

The point of separating policy from mechanism: a governance owner who is
not an engineer can define and version the rules in a config file, and the
framework compiles that config into a fail-closed gate cascade. Nothing
about the rules is hard-coded in Python. Load from a dict, JSON, or TOML.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .gates import (BudgetGate, FiniteInputGate, GateCascade, KillSwitchGate,
                    PermissionGate, RateLimitGate, ThresholdGate)


@dataclass
class Policy:
    """A versioned, declarative governance policy for a class of agents."""

    name: str = "default"
    version: int = 1
    allowed_kinds: list[str] = field(default_factory=list)
    # field name -> [lo, hi] (null means unbounded). Includes 'risk' and 'value'.
    finite_fields: dict[str, list] = field(default_factory=dict)
    rate_limit: dict[str, float] | None = None      # {"max_actions": N, "window_seconds": S}
    budget_cap: float | None = None
    thresholds: dict[str, float] = field(default_factory=dict)  # field -> floor
    # review: when risk/value crosses a line, require N approvals.
    review: dict[str, Any] = field(default_factory=dict)        # {"risk_threshold","value_threshold","min_approvals"}

    # --- loaders --------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Policy":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_json(cls, text: str) -> "Policy":
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_file(cls, path: str) -> "Policy":
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        if path.endswith(".toml"):
            import tomllib  # py3.11+
            return cls.from_dict(tomllib.loads(text))
        return cls.from_json(text)

    # --- compile to a cascade ------------------------------------------
    def build_cascade(self) -> GateCascade:
        """Compile the declarative policy into an ordered, fail-closed cascade.

        Order matters. The kill switch is always first. Permission and input
        validity come before the cheaper business rules.
        """
        gates: list = [KillSwitchGate()]
        # Permission: empty allowed_kinds means deny everything (safe default).
        gates.append(PermissionGate(self.allowed_kinds))
        if self.finite_fields:
            bounds = {k: (v[0] if v else None, v[1] if v and len(v) > 1 else None)
                      for k, v in self.finite_fields.items()}
            gates.append(FiniteInputGate(bounds))
        if self.rate_limit:
            gates.append(RateLimitGate(int(self.rate_limit["max_actions"]),
                                       float(self.rate_limit["window_seconds"])))
        if self.budget_cap is not None:
            gates.append(BudgetGate(float(self.budget_cap)))
        for fkey, floor in self.thresholds.items():
            gates.append(ThresholdGate(fkey, float(floor)))
        return GateCascade(gates)
