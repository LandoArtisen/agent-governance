# governance

A small, dependency-free, **fail-closed control layer for autonomous AI agents**.

Put one choke point in front of everything an agent does. Allow the safe
actions, block the dangerous ones with a reason, and keep an audit record of
every decision. Deny by default, fail closed, prove it afterward.

```python
from governance import Governor, Policy, Action, AgentCard

policy = Policy(
    name="support-agent",
    allowed_kinds=["search", "send_email", "send_money"],
    finite_fields={"value": [0.0, None]},     # money must be finite and >= 0
    budget_cap=250.0,                          # per-agent spend cap
    review={"risk_threshold": 0.6, "value_threshold": 100.0},
)

gov = Governor(policy=policy)
gov.registry.register(AgentCard("support-bot", allowed_kinds=policy.allowed_kinds))

verdict = gov.govern(Action("support-bot", "send_money", value=900.0, risk=0.8))
if verdict.allowed:
    issue_refund()          # only runs if every gate and the reviewer agreed
else:
    print(verdict.summary())  # BLOCK <id> [high] review_denied
```

## Why

Autonomous agents now take consequential actions at machine speed. Most teams
cannot **see**, **gate**, or **audit** what their agents do before a bad action
lands. This library is the layer that does those three things, with two
non-negotiable properties baked in:

- **Deny by default.** An action is allowed only if every gate explicitly
  allows it. Anything unknown, malformed, or ambiguous is blocked.
- **Fail closed.** A gate that crashes, a reviewer that is unreachable, a
  metric that reads `NaN`, a governor that hits an unexpected error: every one
  of these resolves to BLOCK. There is no path that throws its way to an ALLOW.

## What is in the box

| Component | What it does |
|---|---|
| `Governor` | The single choke point. `govern(action) -> Verdict`. |
| `GateCascade` + `Gate`s | Ordered, fail-closed policy checks (kill switch, permission, finite-input, rate limit, budget, threshold, custom predicate). |
| `HaltEngine` | Latching kill switch and metric tripwires. A bad or missing metric halts. |
| `ReviewPolicy` | Cross-model / independent review. A second reviewer must approve high-risk actions; an unreachable reviewer rejects. |
| `AuditTrail` | Append-only, queryable record of every decision, exportable as JSONL. |
| `AgentRegistry` + `AgentCard` | Who each agent is, what it may do, its data sources, and its reliability. Unknown agent means denied. |
| `Policy` | Declarative config that compiles into a cascade. Policy lives in data, not code. |

## Run it

```bash
python examples/demo_agent.py     # govern a generic tool-calling agent
python -m pytest -q               # or: python -m unittest discover -s tests
```

The demo governs a customer-support agent: it allows a search and a small
refund, blocks an unpermitted action, an unregistered agent, and a malformed
`infinity` value, sends a large transfer to review, and shows the kill switch
benching everything. The test suite includes a fuzz pass that throws thousands
of malformed inputs at the gates and asserts they never ALLOW.

## Console (web UI)

A dependency-free operator console ships with the library: the agent
registry, a live feed of every decision, the kill switch, and a form to
submit a test action and watch it pass or get blocked.

```bash
python examples/run_console.py     # then open http://127.0.0.1:8900
```

It is built on the Python standard library (no framework), and it exposes a
small JSON API (`/api/state`, `/api/action`, `/api/halt`, `/api/resume`) so
any front end can drive it. A React dashboard built on that same API lives in
[`dashboard/`](dashboard).

## Provenance

This is the governance spine of a real, high-stakes autonomous system,
extracted and generalized with every domain assumption removed. The original
governed a fleet of trading agents where mistakes cost real money. In
production that layer caught a silently losing agent (frozen by the audit trail
and kill switch), a $97K phantom-gain reporting artifact (exposed by adversarial
re-testing and cross-model review), and a fail-open hole in a gate itself (a
non-finite value slipping past a magnitude check, now the reason
`FiniteInputGate` screens for finiteness first). Those scars are the design.

## License

MIT.
