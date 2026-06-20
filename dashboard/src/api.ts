import type { State, Verdict } from "./types";

// Point this at the Python governance console (governance/console.py).
const BASE = (import.meta.env.VITE_API as string) || "http://127.0.0.1:8900";

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  base: BASE,
  state: () => jget<State>("/api/state"),
  govern: (a: { agent_id: string; kind: string; value: number; risk: number }) =>
    jpost<Verdict>("/api/action", a),
  halt: () => jpost<{ ok: boolean }>("/api/halt"),
  resume: () => jpost<{ ok: boolean }>("/api/resume"),
};
