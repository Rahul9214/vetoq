import { describe, expect, it } from "vitest";
import type { RunDetail } from "@/lib/contracts";
import {
  findingsStage,
  goalLockStage,
  proposalStage,
  sourceStage,
} from "@/lib/run-state";

const run = {
  id: "run-1",
  state: "AUTHORIZING",
  goal: "Create one ticket",
  created_at: "2026-10-12T00:00:00Z",
  failure: null,
  workspace_id: "00000000-0000-4000-8000-00000000000a",
  expires_at: "2026-10-12T00:30:00Z",
  goal_lock: { goal: "Create one ticket" },
  analysis: {
    summary: "Ready",
    provider: "groq",
    model: "openai/gpt-oss-120b",
    elapsed_ms: 1,
  },
  findings: [],
  action: {
    id: "action-1",
    proposal: {
      tool: "tickets.create",
      arguments: { workspace_id: "a", title: "Ticket", body: "Body" },
    },
    digest: "a".repeat(64),
    verdict: null,
    reasons: [],
  },
  review: null,
  ticket: null,
  sources: [
    {
      id: "source-1",
      origin: "pasted-email",
      supplier: "user",
      digest: "b".repeat(64),
      trust: "untrusted" as const,
      complete: true,
      expires_at: "2026-10-13T00:00:00Z",
      declared_media_type: null,
      representation_kind: null,
      charset: null,
      byte_size: null,
      parser_id: null,
      parser_version: null,
    },
  ],
  edges: [],
} satisfies RunDetail;

describe("persisted run stage labels", () => {
  it("does not call a persisted proposal pending", () => {
    expect(proposalStage(run)).toBe("PROPOSED");
    expect(goalLockStage(run)).toBe("SEALED");
    expect(sourceStage(run)).toBe("RECORDED");
    expect(findingsStage(run)).toBe("NONE");
  });
});
