"""A minimal, dependency-free web console for the governance layer.

This is the operator view: the agent registry, a live feed of every
decision, the kill switch, and a form to submit a test action and watch it
pass or get blocked in real time. It wraps a Governor and serves a single
HTML page plus a small JSON API, using only the Python standard library.

    from governance import Governor, Policy
    from governance.console import Console
    Console(Governor(policy=Policy(...))).serve(port=8900)
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .governor import Governor
from .registry import AgentCard
from .types import Action


def _verdict_dict(v) -> dict:
    return {
        "action_id": v.action_id,
        "decision": v.decision.value,
        "severity": v.severity.value,
        "reasons": v.reasons,
        "review_required": v.review_required,
        "review_approved": v.review_approved,
        "audit_id": v.audit_id,
        "gates": [{"gate": g.gate, "decision": g.decision.value,
                   "reason": g.reason, "severity": g.severity.value}
                  for g in v.gate_results],
    }


class Console:
    def __init__(self, governor: Governor):
        self.gov = governor

    # --- state for the UI ----------------------------------------------
    def state(self) -> dict[str, Any]:
        recs = self.gov.audit.records()[-50:][::-1]
        allowed = len(self.gov.audit.query(decision="allow"))
        blocked = len(self.gov.audit.query(decision="block"))
        return {
            "halt": self.gov.halt.state.as_dict(),
            "agents": [asdict(c) | {"status": c.status.value} for c in self.gov.registry.list()],
            "audit": [asdict(r) for r in recs],
            "stats": {"allowed": allowed, "blocked": blocked, "total": allowed + blocked},
            "policy": getattr(self.gov.policy, "name", "custom"),
        }

    # --- server --------------------------------------------------------
    def serve(self, host: str = "127.0.0.1", port: int = 8900) -> None:
        console = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def do_OPTIONS(self):
                # CORS preflight, so a separate React dev server can call the API.
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def _json_body(self) -> dict:
                n = int(self.headers.get("Content-Length", 0) or 0)
                if not n:
                    return {}
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return {}

            def do_GET(self):
                if self.path == "/" or self.path.startswith("/index"):
                    self._send(200, _PAGE, "text/html; charset=utf-8")
                elif self.path.startswith("/api/state"):
                    self._send(200, json.dumps(console.state(), default=str))
                else:
                    self._send(404, json.dumps({"error": "not_found"}))

            def do_POST(self):
                body = self._json_body()
                if self.path.startswith("/api/action"):
                    a = Action(
                        agent_id=str(body.get("agent_id", "")),
                        kind=str(body.get("kind", "")),
                        value=float(body.get("value", 0) or 0),
                        risk=float(body.get("risk", 0) or 0),
                        payload=body.get("payload") or {},
                    )
                    v = console.gov.govern(a)
                    self._send(200, json.dumps(_verdict_dict(v), default=str))
                elif self.path.startswith("/api/halt"):
                    console.gov.halt.engage("operator_console")
                    self._send(200, json.dumps({"ok": True}))
                elif self.path.startswith("/api/resume"):
                    console.gov.halt.reset()
                    self._send(200, json.dumps({"ok": True}))
                elif self.path.startswith("/api/register"):
                    console.gov.registry.register(AgentCard(
                        agent_id=str(body.get("agent_id", "")),
                        purpose=str(body.get("purpose", "")),
                        allowed_kinds=list(body.get("allowed_kinds") or []),
                    ))
                    self._send(200, json.dumps({"ok": True}))
                else:
                    self._send(404, json.dumps({"error": "not_found"}))

        srv = ThreadingHTTPServer((host, port), Handler)
        print(f"governance console on http://{host}:{port}  (Ctrl-C to stop)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopping.")
            srv.shutdown()


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Governance Console</title><style>
:root{--navy:#16314f;--bg:#0f1722;--card:#172230;--line:#26384a;--ok:#2ecc71;--bad:#e74c3c;--mut:#8aa0b6}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Helvetica,Arial,sans-serif;background:var(--bg);color:#e7eef6}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background:var(--navy);border-bottom:1px solid var(--line)}
header h1{font-size:16px;margin:0;letter-spacing:.5px}
.kill{display:flex;gap:8px;align-items:center}
.badge{padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700}
.live{background:#143d27;color:var(--ok)}.halted{background:#43181a;color:var(--bad)}
button{background:#21405f;color:#fff;border:1px solid var(--line);border-radius:6px;padding:6px 12px;cursor:pointer;font-size:13px}
button.danger{background:#5b1f23}button:hover{filter:brightness(1.15)}
main{display:grid;grid-template-columns:280px 1fr;gap:16px;padding:16px 20px}
.col{display:flex;flex-direction:column;gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card h2{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:.7px;color:var(--mut)}
.agent{border:1px solid var(--line);border-radius:8px;padding:9px;margin-bottom:8px}
.agent .nm{font-weight:700}.agent .meta{color:var(--mut);font-size:12px;margin-top:3px}
.stat{display:flex;gap:18px}.stat div{font-size:13px}.stat b{font-size:20px;display:block}
form{display:grid;grid-template-columns:1fr 1fr;gap:8px}form label{font-size:11px;color:var(--mut);display:block;margin-bottom:2px}
input,select{width:100%;background:#0e1620;border:1px solid var(--line);color:#e7eef6;border-radius:6px;padding:6px;font-size:13px}
.full{grid-column:1/3}
table{width:100%;border-collapse:collapse;font-size:12.5px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600;text-transform:uppercase;font-size:10.5px;letter-spacing:.5px}
.tag{padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700}
.allow{background:#143d27;color:var(--ok)}.block{background:#43181a;color:var(--bad)}
.reasons{color:var(--mut);font-size:11.5px}.verdict{margin-top:8px;font-size:13px}
.mono{font-family:ui-monospace,Menlo,monospace}
</style></head><body>
<header><h1>GOVERNANCE CONSOLE</h1>
<div class="kill"><span id="halt" class="badge live">LIVE</span>
<button onclick="halt()" class="danger">Engage kill switch</button>
<button onclick="resume()">Reset</button></div></header>
<main>
<div class="col">
 <div class="card"><h2>Stats</h2><div class="stat">
   <div><b id="s_allow">0</b>allowed</div><div><b id="s_block">0</b>blocked</div><div><b id="s_total">0</b>total</div></div></div>
 <div class="card"><h2>Agent registry</h2><div id="agents"></div></div>
 <div class="card"><h2>Submit a test action</h2>
   <form onsubmit="submitAction(event)">
     <div class="full"><label>agent id</label><input id="f_agent" value="support-bot"></div>
     <div><label>kind</label><input id="f_kind" value="send_money"></div>
     <div><label>value</label><input id="f_value" value="900" type="number" step="any"></div>
     <div><label>risk 0..1</label><input id="f_risk" value="0.8" type="number" step="any" min="0" max="1"></div>
     <div style="display:flex;align-items:flex-end"><button class="full" type="submit">Govern action</button></div>
   </form>
   <div id="verdict" class="verdict"></div></div>
</div>
<div class="col"><div class="card"><h2>Live decision feed</h2>
 <table><thead><tr><th>time</th><th>agent</th><th>kind</th><th>decision</th><th>reasons</th></tr></thead>
 <tbody id="feed"></tbody></table></div></div>
</main>
<script>
async function jget(u){return (await fetch(u)).json()}
async function jpost(u,b){return (await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})})).json()}
function tag(d){return '<span class="tag '+(d=='allow'?'allow':'block')+'">'+d.toUpperCase()+'</span>'}
async function refresh(){
 const s=await jget('/api/state');
 document.getElementById('s_allow').textContent=s.stats.allowed;
 document.getElementById('s_block').textContent=s.stats.blocked;
 document.getElementById('s_total').textContent=s.stats.total;
 const h=document.getElementById('halt');
 if(s.halt.engaged){h.className='badge halted';h.textContent='HALTED: '+(s.halt.reasons||[]).join(',')}
 else{h.className='badge live';h.textContent='LIVE'}
 document.getElementById('agents').innerHTML=s.agents.map(a=>
   '<div class="agent"><div class="nm">'+a.agent_id+'</div><div class="meta">'+(a.purpose||'')+'</div>'+
   '<div class="meta">may: '+(a.allowed_kinds||[]).join(', ')+'</div>'+
   '<div class="meta">status: '+a.status+' &middot; calibration '+(a.calibration||0)+'</div></div>').join('')||'<div class="meta">none registered</div>';
 document.getElementById('feed').innerHTML=s.audit.map(r=>{
   const t=new Date(r.ts*1000).toLocaleTimeString();
   return '<tr><td class="mono">'+t+'</td><td>'+r.agent_id+'</td><td>'+r.action_kind+'</td><td>'+tag(r.decision)+'</td><td class="reasons">'+((r.reasons||[]).join(', ')||'ok')+'</td></tr>'}).join('');
}
async function submitAction(e){e.preventDefault();
 const b={agent_id:f_agent.value,kind:f_kind.value,value:parseFloat(f_value.value)||0,risk:parseFloat(f_risk.value)||0};
 const v=await jpost('/api/action',b);
 document.getElementById('verdict').innerHTML=tag(v.decision)+' '+(v.review_required?'(reviewed) ':'')+
   '<span class="reasons">'+((v.reasons||[]).join(', ')||'all gates passed')+'</span>';
 refresh();
}
async function halt(){await jpost('/api/halt');refresh()}
async function resume(){await jpost('/api/resume');refresh()}
refresh();setInterval(refresh,1500);
</script></body></html>"""
