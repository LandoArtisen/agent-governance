export interface HaltState {
  engaged: boolean;
  reasons: string[];
  severity: string;
  since: number | null;
}

export interface AgentCard {
  agent_id: string;
  purpose: string;
  allowed_kinds: string[];
  data_sources: string[];
  policy: string;
  status: string;
  calibration: number;
  created_ts: number;
}

export interface AuditRecord {
  audit_id: string;
  ts: number;
  agent_id: string;
  action_id: string;
  action_kind: string;
  decision: "allow" | "block";
  severity: string;
  reasons: string[];
  review_required: boolean;
  review_approved: boolean | null;
}

export interface State {
  halt: HaltState;
  agents: AgentCard[];
  audit: AuditRecord[];
  stats: { allowed: number; blocked: number; total: number };
  policy: string;
}

export interface Verdict {
  action_id: string;
  decision: "allow" | "block";
  severity: string;
  reasons: string[];
  review_required: boolean;
  review_approved: boolean | null;
  gates: { gate: string; decision: string; reason: string; severity: string }[];
}
