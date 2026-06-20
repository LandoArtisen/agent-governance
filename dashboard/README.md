# Governance Dashboard (React)

A mission-control front end for the governance control plane. It reads the
same JSON API the built-in Python console serves, so the dashboard is just a
nicer face on the same governor.

## Run

Two processes. First the control plane (the Python console, which serves the
API), then this dashboard.

```bash
# 1. from the repo root, start the governance console (serves the JSON API)
python examples/run_console.py        # http://127.0.0.1:8900

# 2. in this folder, start the dashboard
cd dashboard
npm install
npm run dev                           # http://127.0.0.1:5173
```

Point the dashboard at a different control plane with an env var:

```bash
VITE_API=http://your-host:8900 npm run dev
```

## What you see

- A live status beacon, LIVE or HALTED, with the kill switch.
- Allowed / blocked / total readouts.
- The agent registry: who may act and what each agent may do.
- The decision tape: every governed action, allowed or blocked, with reasons.
- A probe form to submit a test action and watch the gates decide in real time.

## Design

Built with the `frontend-design` guidance toward a deliberate instrument-panel
look rather than a templated dashboard: a deep ink base, a calm teal pass and
amber caution signal palette (vermilion reserved for a halted system), Space
Grotesk paired with IBM Plex Mono, and a signature decision tape printed on
bone paper like a control-room printout.

Stack: Vite, React, TypeScript. No UI framework.
