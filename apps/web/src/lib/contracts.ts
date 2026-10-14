export type Workspace = {
  id: string;
  name: string;
  role: "operator" | "reviewer";
  policy_revision: string;
};

export const TERMINAL_STATES = [
  "COMPLETED",
  "NO_ACTION",
  "BLOCKED",
  "FAILED",
  "CANCELLED",
  "EXPIRED",
] as const;

export type Ticket = {
  id: string;
  workspace_id?: string;
  run_id: string;
  title: string;
  body: string;
  created_at: string;
  verified_at: string | null;
};

export type Me = {
  principal: string;
  access: "active" | "not_provisioned";
  workspaces: Workspace[];
  template: {
    id: "support-triage/1";
    tool: "tickets.create";
    destination: "local-ticket-store";
    max_writes: 1;
    expires_minutes: 30;
  };
};

export type RunSummary = {
  id: string;
  state: string;
  goal: string;
  created_at: string;
  failure: string | null;
};

export type RunDetail = RunSummary & {
  workspace_id: string;
  expires_at: string;
  goal_lock: Record<string, unknown>;
  analysis: null | {
    summary: string;
    provider: string;
    model: string;
    elapsed_ms: number;
  };
  findings: Array<{
    id: string;
    origin: "deterministic" | "model";
    family: string;
    explanation: string;
    node_id: string;
    start_offset: number;
    end_offset: number;
  }>;
  action: null | {
    id: string;
    proposal: {
      tool: string;
      arguments: { workspace_id: string; title: string; body: string };
      evidence_ids?: string[];
    };
    digest: string;
    verdict: "ALLOW" | "BLOCK" | "REVIEW" | null;
    reasons: string[];
  };
  review: null | {
    id: string;
    digest: string;
    expires_at: string;
    decision: "approve" | "reject" | null;
    consumed: boolean;
    eligible: boolean;
  };
  ticket: null | {
    id: string;
    title: string;
    created_at: string;
    verified_at: string | null;
  };
  sources: Array<{
    id: string;
    origin: string;
    supplier: string;
    digest: string;
    trust: "untrusted";
    complete: boolean;
    expires_at: string;
    declared_media_type: string | null;
    representation_kind: string | null;
    charset: string | null;
    byte_size: number | null;
    parser_id: string | null;
    parser_version: string | null;
  }>;
  edges: Array<{
    parent_id: string;
    child_id: string;
    transform: string;
    version: string;
    lossy: boolean;
    transform_steps: Array<{ transform: string; version: string }> | null;
  }>;
};

export type AuditEvent = {
  sequence: number;
  actor: string;
  type: string;
  detail: Record<string, unknown>;
  created_at: string;
};
