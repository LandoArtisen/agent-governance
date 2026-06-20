# Usage

How to run the governance layer and put it in front of your own agent.

## 1. See it work (no setup)

```bash
cd governance
python3 examples/demo_agent.py          # the command-line demo
python3 -m unittest discover -s tests   # the 30 fail-closed tests
```

The demo governs a support agent: it allows a search and a small refund,
sends a large transfer to review and gets it rejected, blocks an unpermitted
action and a malformed value, denies an unregistered agent, and shows the
kill switch freezing everything.

## 2. Run the consoles

The built-in operator console (zero dependencies):

```bash
python3 examples/run_console.py         # then open http://127.0.0.1:8900
```

The polished React dashboard. Keep the console running (it serves the API),
then in a second terminal:

```bash
cd dashboard
npm install
npm run dev                             # then open http://127.0.0.1:5173
```

Point the dashboard at a different control plane with `VITE_API=http://host:8900 npm run dev`.

## 3. Use it in your own code

This is the real purpose. Install the package once, then put the governor in
front of anything consequential your agent does.

```bash
pip install -e .        # from the repo root
```

```python
from governance import Governor, Policy, Action, AgentCard

# Define the rules once, in plain config.
policy = Policy(
    allowed_kinds=["search", "read_file"],   # what the agent may do
    budget_cap=10.0,                          # spend ceiling per agent
    review={"risk_threshold": 0.7},           # risky actions need a second opinion
)
gov = Governor(policy=policy)
gov.registry.register(AgentCard("my-agent", allowed_kinds=policy.allowed_kinds))

# Then, before your agent actually executes anything:
verdict = gov.govern(Action("my-agent", kind="search", value=1.0))
if verdict.allowed:
    run_the_tool()                       # only runs if every gate agreed
else:
    print("blocked:", verdict.reasons)   # already recorded in the audit trail
```

## 4. The mental model

- `govern(action)` is the one choke point. Everything passes through it.
- It returns ALLOW or BLOCK. BLOCK is the default. Anything unknown or
  malformed is blocked.
- The gates check permission, valid inputs, rate, budget, and thresholds.
- The halt engine is the kill switch. `gov.halt.engage()` stops everything;
  `gov.halt.reset()` clears it.
- The review gate sends risky actions to a second model. An unreachable or
  crashing reviewer rejects.
- The audit trail records every decision. `gov.audit.export_jsonl()` dumps it.

## 5. Wiring it to a real agent

The pattern is always the same. Wherever your agent is about to call a tool,
send money, write a file, or hit an API, build an `Action` that describes it,
call `gov.govern(...)`, and only proceed if `verdict.allowed`. The agent
proposes, the governor disposes.

```python
def run_tool(agent_id, tool_name, args, cost=0.0, risk=0.0):
    v = gov.govern(Action(agent_id, kind=tool_name, value=cost, risk=risk,
                          payload=args))
    if not v.allowed:
        return {"refused": v.reasons}    # blocked, and audited
    return execute(tool_name, args)      # safe to run
```

## 6. Plugging in a real second-model reviewer

The review gate takes any callable. In production it is a second LLM with a
skeptical prompt. A ready-made adapter ships with the library, so you usually
do not have to write the call yourself:

```bash
pip install -e ".[anthropic]"     # or ".[openai]" for a GPT reviewer
export ANTHROPIC_API_KEY=...
```

```python
from governance import Governor, ReviewPolicy, anthropic_reviewer

gov = Governor(policy=policy,
               review=ReviewPolicy([anthropic_reviewer(model="claude-haiku-4-5")],
                                   risk_threshold=0.7))
```

`anthropic_reviewer` (Claude) and `openai_reviewer` (GPT) default to the cheap
fast tier, send the action to the model with a skeptical prompt, and parse its
verdict. They are fail-closed: the model must reply with an explicit APPROVE,
and a crash, timeout, refusal, or unparseable answer denies. Run
`python3 examples/llm_reviewer_demo.py` to see it (it uses a live reviewer if a
key is set, an offline stub otherwise).

If you want full control, plug in your own function instead:

```python
from governance import ReviewPolicy, CallableReviewer, ReviewResult

def my_reviewer(action):
    approved, why = ask_other_model(action)   # your code
    return ReviewResult(approved, why, "reviewer-2")

gov = Governor(policy=policy,
               review=ReviewPolicy([CallableReviewer("reviewer-2", my_reviewer)],
                                   risk_threshold=0.7))
```

## License

PolyForm Noncommercial 1.0.0. Free for personal, research, and noncommercial
use. Commercial use requires a separate license from the author. See `LICENSE`.
