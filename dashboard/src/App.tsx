import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { AgentCard, AuditRecord, State, Verdict } from "./types";

const POLL_MS = 1500;

export default function App() {
  const [state, setState] = useState<State | null>(null);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setState(await api.state());
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <div className="shell">
      <Masthead policy={state?.policy} apiBase={api.base} />
      {offline && <Offline base={api.base} />}
      <Beacon halt={state?.halt} onChange={refresh} />
      <Readouts stats={state?.stats} />
      <div className="grid">
        <section className="panel registry">
          <PanelHead title="Registered agents" hint="who may act, and what they may do" />
          <Registry agents={state?.agents ?? []} />
        </section>
        <section className="panel tape">
          <PanelHead title="Decision tape" hint="every action, allowed or blocked, in order" />
          <Tape audit={state?.audit ?? []} />
        </section>
      </div>
      <section className="panel probe">
        <PanelHead title="Probe" hint="submit an action and watch the gates decide" />
        <Probe onResult={refresh} />
      </section>
      <footer className="foot">
        Fail closed by default. Extracted from the ConBot trading platform governance spine.
      </footer>
    </div>
  );
}

function Masthead({ policy, apiBase }: { policy?: string; apiBase: string }) {
  return (
    <header className="masthead">
      <div className="brand">
        <span className="dot" />
        GOVERNANCE <span className="thin">CONTROL PLANE</span>
      </div>
      <div className="meta">
        policy <b>{policy ?? "—"}</b> <span className="sep">/</span> {apiBase.replace(/^https?:\/\//, "")}
      </div>
    </header>
  );
}

function Offline({ base }: { base: string }) {
  return (
    <div className="offline">
      Control console unreachable at {base}. Start it with
      <code> python examples/run_console.py</code>.
    </div>
  );
}

function Beacon({ halt, onChange }: { halt?: State["halt"]; onChange: () => void }) {
  const engaged = halt?.engaged ?? false;
  return (
    <div className={"beacon " + (engaged ? "is-halted" : "is-live")}>
      <div className="beacon-state">
        <span className="ring" />
        <div>
          <div className="word">{engaged ? "HALTED" : "LIVE"}</div>
          <div className="why">
            {engaged ? (halt?.reasons?.join(" / ") || "system halted") : "all gates armed, deny by default"}
          </div>
        </div>
      </div>
      <div className="beacon-controls">
        {engaged ? (
          <button className="btn reset" onClick={async () => { await api.resume(); onChange(); }}>
            Reset
          </button>
        ) : (
          <button className="btn kill" onClick={async () => { await api.halt(); onChange(); }}>
            Engage kill switch
          </button>
        )}
      </div>
    </div>
  );
}

function Readouts({ stats }: { stats?: State["stats"] }) {
  const items: [string, number, string][] = [
    ["allowed", stats?.allowed ?? 0, "ok"],
    ["blocked", stats?.blocked ?? 0, "no"],
    ["total", stats?.total ?? 0, "n"],
  ];
  return (
    <div className="readouts">
      {items.map(([label, val, cls]) => (
        <div key={label} className={"readout r-" + cls}>
          <div className="num">{val}</div>
          <div className="lab">{label}</div>
        </div>
      ))}
    </div>
  );
}

function PanelHead({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="phead">
      <span className="ptick" aria-hidden />
      <span className="ptitle">{title}</span>
      <span className="phint">{hint}</span>
    </div>
  );
}

function Registry({ agents }: { agents: AgentCard[] }) {
  if (!agents.length) return <div className="empty">No agents registered. Unknown agents are denied.</div>;
  return (
    <div className="agents">
      {agents.map((a) => (
        <div key={a.agent_id} className="agent">
          <div className="agent-top">
            <span className="agent-id">{a.agent_id}</span>
            <span className={"status s-" + a.status}>{a.status.replace("_", " ")}</span>
          </div>
          <div className="agent-purpose">{a.purpose || "no stated purpose"}</div>
          <div className="agent-kinds">{a.allowed_kinds.map((k) => <span key={k} className="kind">{k}</span>)}</div>
          <div className="agent-cal">
            calibration
            <span className="bar"><span style={{ width: `${Math.round((a.calibration || 0) * 100)}%` }} /></span>
            {(a.calibration || 0).toFixed(2)}
          </div>
        </div>
      ))}
    </div>
  );
}

function Tape({ audit }: { audit: AuditRecord[] }) {
  if (!audit.length) return <div className="empty">No decisions yet. Submit an action below.</div>;
  return (
    <div className="rows">
      {audit.map((r) => (
        <div key={r.audit_id} className={"row d-" + r.decision}>
          <span className="t">{new Date(r.ts * 1000).toLocaleTimeString()}</span>
          <span className="mark">{r.decision === "allow" ? "ALLOW" : "BLOCK"}</span>
          <span className="who">{r.agent_id}</span>
          <span className="kind2">{r.action_kind}</span>
          <span className="reasons">
            {r.review_required && <em>reviewed </em>}
            {r.reasons.join(", ") || "all gates passed"}
          </span>
        </div>
      ))}
    </div>
  );
}

const KINDS = ["search", "read_doc", "send_email", "send_money", "delete_account"];

function Probe({ onResult }: { onResult: () => void }) {
  const [agent, setAgent] = useState("support-bot");
  const [kind, setKind] = useState("send_money");
  const [value, setValue] = useState("900");
  const [risk, setRisk] = useState("0.8");
  const [verdict, setVerdict] = useState<Verdict | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const v = await api.govern({
        agent_id: agent,
        kind,
        value: parseFloat(value) || 0,
        risk: parseFloat(risk) || 0,
      });
      setVerdict(v);
      onResult();
    } catch {
      setVerdict(null);
    }
  };

  return (
    <form className="probe-form" onSubmit={submit}>
      <Field label="agent id"><input value={agent} onChange={(e) => setAgent(e.target.value)} /></Field>
      <Field label="action kind">
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => <option key={k}>{k}</option>)}
        </select>
      </Field>
      <Field label="value"><input type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} /></Field>
      <Field label="risk 0..1"><input type="number" step="any" min="0" max="1" value={risk} onChange={(e) => setRisk(e.target.value)} /></Field>
      <button className="btn govern" type="submit">Govern action</button>
      {verdict && (
        <div className={"verdict v-" + verdict.decision}>
          <span className="mark">{verdict.decision === "allow" ? "ALLOW" : "BLOCK"}</span>
          {verdict.review_required && <span className="rev">reviewed</span>}
          <span className="vreasons">{verdict.reasons.join(", ") || "all gates passed"}</span>
        </div>
      )}
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
