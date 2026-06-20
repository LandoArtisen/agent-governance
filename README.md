# governance

[![CI](https://github.com/LandoArtisen/agent-governance/actions/workflows/ci.yml/badge.svg)](https://github.com/LandoArtisen/agent-governance/actions/workflows/ci.yml)

A small, dependency-free, **fail-closed control layer for autonomous AI agents**.

> **New here? The 30-second version.** AI agents now take real actions on their
> own: calling tools, spending money, writing to systems. This is the layer
> that sits in front of an agent and decides, in real time, whether each action
> is allowed. Safe actions pass. Dangerous, malformed, or over-budget ones are
> blocked with a reason, and every decision is logged so you can prove what
> happened. It defaults to *block* and it fails to *block*, so a bug or an
> outage makes it safer, not riskier. It comes with a live operator dashboard, a
> 30-test suite that proves the block-by-default behavior holds under malformed
> and hostile input, and it was extracted from a production system that governed
> real-money trading agents, where it caught a silently losing agent, a fake
> $97K "profit" reporting bug, and a hole in a safety gate itself. Start with
> **[USAGE.md](USAGE.md)** to run it.

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
| `HardenedReviewer` | Turns a non-deterministic model into a verdict you can gate on: samples it N times, requires quorum **and** self-agreement, denies a wavering panel, and can sample across cosmetic perturbations so an order-biased verdict fails closed too. A wobbly model is a broken instrument. |
| `AuditTrail` | Hash-chained, tamper-evident record of every decision, exportable as JSONL. Hashes use RFC 8785 JCS so they verify identically across implementations; `verify_chain()` catches any mutated or deleted record. |
| `CapabilityAuthority` + `CapabilityToken` | Signed, scoped, revocable grants. Revoke one token and every pending action under it stops at the gate. |
| `AgentRegistry` + `AgentCard` | Who each agent is, what it may do, its data sources, and its reliability. Unknown agent means denied. |
| `Policy` | Declarative config that compiles into a cascade. Policy lives in data, not code. |

### Hardening a stochastic reviewer

A single model call is a coin flip you are treating as a verdict. `HardenedReviewer`
makes it safe to gate on, with the same doctrine the halt engine applies to a metric:
an unreliable instrument fails closed.

```python
from governance import (ReviewPolicy, HardenedReviewer, anthropic_reviewer,
                        reorder_payload)

# Four samples, unanimous approval, any split treated as instability. Sampling
# across reorder_payload means an order-biased flip is caught too: the model is
# graded on the same action spelled two ways and must agree with itself. (Note:
# a stronger reviewer model is not a fairer one, so pick for fairness, not size.)
reviewer = HardenedReviewer(anthropic_reviewer(), samples=4, timeout_s=10.0,
                            perturbations=[reorder_payload])
gov = Governor(policy=policy, review=ReviewPolicy([reviewer], risk_threshold=0.7))
```

### Capability tokens

```python
from governance import Governor, Policy, Action, CapabilityAuthority

auth = CapabilityAuthority(secret=os.environ["GOV_CAP_SECRET"])
gov = Governor(policy=Policy(allowed_kinds=["send_money"]),
               capability_authority=auth, require_registration=False)

tok = auth.issue("agent-1", ["send_money"], ttl_seconds=300)
gov.govern(Action("agent-1", "send_money", value=10.0,
                  payload={"capability": tok.to_dict()}))   # allowed
auth.revoke(tok.token_id)                                    # every later use blocks
```

## What this is not (and how to plug it in)

This is the decision spine, deliberately small. Two things it does not do, by design,
because dedicated tools already do them well. Both are clean seams, not gaps.

- **It does not sandbox execution.** It decides; it does not contain. Wrap the executor
  in your own sandbox (or Microsoft's Agent Hypervisor) and call `gov.govern(...)` before
  you run the tool.
- **It does not detect prompt injection or PII.** That is a content-scanning arms race
  owned by tools like LlamaFirewall. Plug one in as a `PredicateGate` or as a `Reviewer`,
  and its verdict flows through the same fail-closed cascade and audit trail.

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

## Live second-model review

The review gate takes any callable, so in production it can be a real,
independent model with a skeptical prompt. A ready-made adapter ships with the
library:

```bash
pip install -e ".[anthropic]"          # or ".[openai]" for a GPT reviewer
export ANTHROPIC_API_KEY=...
python examples/llm_reviewer_demo.py    # runs a live Claude reviewer if the key is set
```

```python
from governance import Governor, ReviewPolicy, anthropic_reviewer

gov = Governor(
    policy=policy,
    review=ReviewPolicy([anthropic_reviewer(model="claude-haiku-4-5")],
                        risk_threshold=0.7),
)
```

It defaults to Claude Haiku 4.5, the cheap fast tier, which is the right pick
for a check that runs on every risky action. The adapter is fail-closed: the
model must answer with an explicit APPROVE, and a crash, a timeout, a refusal,
or any unparseable reply resolves to DENY. With no API key the demo falls back
to an offline stub so it still runs anywhere.

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

PolyForm Noncommercial 1.0.0. Free for personal, research, and noncommercial
use. Commercial use requires a separate license from the author. See
[LICENSE](LICENSE), and [USAGE.md](USAGE.md) for how to run and integrate it.
