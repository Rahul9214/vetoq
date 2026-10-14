import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { RunDetail } from "@/lib/contracts";
import { RunView } from "./run-view";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

const source = {
  id: "source-1",
  origin: "pasted-email",
  supplier: "user",
  digest: "b".repeat(64),
  trust: "untrusted" as const,
  complete: true,
  expires_at: "2026-10-10T00:00:00Z",
  declared_media_type: null,
  representation_kind: null,
  charset: null,
  byte_size: null,
  parser_id: null,
  parser_version: null,
};

const detail: RunDetail = {
  id: "run-1",
  state: "BLOCKED",
  goal: "Create one ticket",
  workspace_id: "00000000-0000-4000-8000-00000000000a",
  created_at: "2026-10-09T00:00:00Z",
  expires_at: "2026-10-09T00:30:00Z",
  failure: null,
  goal_lock: {
    goal: "Create one ticket",
    tool: "tickets.create",
    destination: "local-ticket-store",
    max_writes: 1,
    policy_revision: "support-triage/1",
  },
  analysis: {
    summary: "Injected instruction found.",
    provider: "groq",
    model: "openai/gpt-oss-120b",
    elapsed_ms: 42,
  },
  findings: [
    {
      id: "finding-1",
      origin: "model",
      family: "Tool Abuse",
      explanation: "Requested another workspace.",
      node_id: "source-1",
      start_offset: 0,
      end_offset: 10,
    },
  ],
  action: {
    id: "action-1",
    proposal: {
      tool: "tickets.create",
      arguments: {
        workspace_id: "00000000-0000-4000-8000-00000000000b",
        title: "Blocked",
        body: "No write",
      },
    },
    digest: "a".repeat(64),
    verdict: "BLOCK",
    reasons: ["GOAL_SCOPE_MISMATCH"],
  },
  review: null,
  ticket: null,
  sources: [source],
  edges: [],
};

function mockRun(run: RunDetail, content = '<img src=x onerror="alert(1)">') {
  vi.mocked(api).mockImplementation(async (path: string) => {
    if (path.includes("/events")) return { items: [] };
    if (path.includes("/content/")) return { content };
    return run;
  });
}

describe("run evidence", () => {
  beforeEach(() => {
    mockRun(detail);
  });

  it("hides approval controls from the requesting principal", async () => {
    mockRun({
      ...detail,
      state: "AWAITING_REVIEW",
      action: {
        ...detail.action!,
        verdict: "REVIEW",
        reasons: ["MATERIAL_UNCERTAINTY"],
      },
      review: {
        id: "review-1",
        digest: "c".repeat(64),
        expires_at: "2099-10-09T00:10:00Z",
        decision: null,
        consumed: false,
        eligible: false,
      },
    });
    render(<RunView runId="run-1" />);
    expect(
      await screen.findByText(/different active reviewer is required/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve exact action" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open verified ticket" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/Execution has not occurred/).length,
    ).toBeGreaterThan(0);
  });

  it("shows approval controls only when the backend marks the reviewer eligible", async () => {
    mockRun({
      ...detail,
      state: "AWAITING_REVIEW",
      goal_lock: {
        ...detail.goal_lock,
        tool_version: 1,
        destination: "local-ticket-store",
      },
      action: {
        ...detail.action!,
        verdict: "REVIEW",
        reasons: ["MATERIAL_UNCERTAINTY"],
        proposal: {
          tool: "tickets.create",
          arguments: {
            workspace_id: "00000000-0000-4000-8000-00000000000a",
            title: "Exact support ticket",
            body: "One in-scope ticket",
          },
        },
      },
      review: {
        id: "review-1",
        digest: "c".repeat(64),
        expires_at: "2099-10-09T00:10:00Z",
        decision: null,
        consumed: false,
        eligible: true,
      },
      ticket: null,
    });
    render(<RunView runId="run-1" />);
    expect(await screen.findByText("MATERIAL_UNCERTAINTY")).toBeInTheDocument();
    expect(screen.getAllByText("Exact support ticket").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("local-ticket-store").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Approve exact action" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open verified ticket" }),
    ).not.toBeInTheDocument();
  });

  it("shows the deterministic wrong-workspace veto", async () => {
    render(<RunView runId="run-1" />);
    expect(await screen.findByText("GOAL_SCOPE_MISMATCH")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The proposed target did not match the authority granted for this run.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("BLOCK").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/Blocked before the prohibited side effect/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByRole("link", { name: "Open ticket" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Verified execution")).not.toBeInTheDocument();
  });

  it("keeps goal, authority, proposal, and guard in causal order", async () => {
    render(<RunView runId="run-1" />);
    await screen.findByRole("heading", { name: "Confirmed goal" });
    const stageNames = [
      "Confirmed goal",
      "Granted authority",
      "Evidence",
      "Security findings",
      "Proposed action",
      "Guard decision",
      "What happened",
    ];
    for (let index = 1; index < stageNames.length; index += 1) {
      const previous = screen.getByRole("heading", {
        name: stageNames[index - 1]!,
      });
      const current = screen.getByRole("heading", { name: stageNames[index]! });
      expect(
        previous.compareDocumentPosition(current) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
    const authority = screen.getByRole("region", { name: "Granted authority" });
    const proposal = screen.getByRole("region", { name: "Proposed action" });
    expect(within(authority).queryByText("Blocked")).not.toBeInTheDocument();
    expect(within(proposal).getByText("Blocked")).toBeInTheDocument();
  });

  it("renders a legacy run without inventing ingestion metadata", async () => {
    render(<RunView runId="run-1" />);
    expect(await screen.findByText("Legacy evidence")).toBeInTheDocument();
    expect(screen.getByText(/Representation not recorded/)).toBeInTheDocument();
    expect(screen.getAllByText("Not recorded").length).toBeGreaterThan(0);
    expect(screen.queryByText("Original")).not.toBeInTheDocument();
  });

  it("renders stored source text inertly", async () => {
    render(<RunView runId="run-1" />);
    const button = await screen.findByRole("button", {
      name: "View protected text",
    });
    button.click();
    await waitFor(() =>
      expect(
        screen.getByText('<img src=x onerror="alert(1)">'),
      ).toBeInTheDocument(),
    );
    expect(document.querySelector("img")).toBeNull();
  });

  it("shows an original and its derived child with one JSON step", async () => {
    mockRun({
      ...detail,
      sources: [
        {
          ...source,
          declared_media_type: "application/json",
          representation_kind: "original",
          parser_id: null,
          parser_version: null,
        },
        {
          ...source,
          id: "child-1",
          declared_media_type: "application/json",
          representation_kind: "canonical_text",
          parser_id: "json_structured",
          parser_version: "1",
        },
      ],
      edges: [
        {
          parent_id: "source-1",
          child_id: "child-1",
          transform: "json-canonical",
          version: "1",
          lossy: false,
          transform_steps: [{ transform: "json-canonical", version: "1" }],
        },
      ],
    });
    render(<RunView runId="run-1" />);
    expect(await screen.findByText("Original")).toBeInTheDocument();
    expect(screen.getByText("Canonical text")).toBeInTheDocument();
    expect(screen.getAllByText("JSON canonicalization").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("json-canonical/1").length).toBeGreaterThan(0);
    const ordered = document.querySelector(".step-list");
    expect(ordered?.textContent).toContain("JSON canonicalization");
    expect(ordered?.children).toHaveLength(1);
    const child = document.getElementById("evidence-child-1");
    expect(child).not.toBeNull();
    fireEvent.click(
      within(child as HTMLElement).getByRole("button", {
        name: "Technical details",
      }),
    );
    expect(screen.getByText("json_structured / 1")).toBeInTheDocument();
  });

  it("shows a two-step email chain separately from its summary", async () => {
    mockRun({
      ...detail,
      findings: [],
      sources: [
        {
          ...source,
          declared_media_type: "message/rfc822",
          representation_kind: "original",
        },
        {
          ...source,
          id: "child-1",
          declared_media_type: "application/json",
          representation_kind: "canonical_text",
        },
      ],
      edges: [
        {
          parent_id: "source-1",
          child_id: "child-1",
          transform: "email-part-json",
          version: "1",
          lossy: true,
          transform_steps: [
            { transform: "email-part-decode", version: "1" },
            { transform: "json-canonical", version: "1" },
          ],
        },
      ],
    });
    render(<RunView runId="run-1" />);
    expect(await screen.findByText("Email JSON part")).toBeInTheDocument();
    const steps = document.querySelector(".step-list");
    const items = [...(steps?.children ?? [])].map((item) => item.textContent);
    expect(items[0]).toContain("MIME part decode");
    expect(items[1]).toContain("JSON canonicalization");
    expect(screen.getByText(/email-part-json\/1/)).toBeInTheDocument();
  });

  it("labels active content from the persisted representation kind", async () => {
    mockRun({
      ...detail,
      findings: [],
      sources: [
        {
          ...source,
          declared_media_type: "text/html",
          representation_kind: "active_content",
        },
      ],
      edges: [],
    });
    render(<RunView runId="run-1" />);
    expect(await screen.findByText("Active content")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "HTML" })).toBeInTheDocument();
  });

  it("does not invent steps when transform history is null", async () => {
    mockRun({
      ...detail,
      findings: [],
      sources: [
        { ...source, representation_kind: "original" },
        {
          ...source,
          id: "child-1",
          representation_kind: "decoded_text",
        },
      ],
      edges: [
        {
          parent_id: "source-1",
          child_id: "child-1",
          transform: "base64",
          version: "1",
          lossy: true,
          transform_steps: null,
        },
      ],
    });
    render(<RunView runId="run-1" />);
    expect(await screen.findByText("Base64 decode")).toBeInTheDocument();
    expect(
      screen.getByText("Transform history not recorded"),
    ).toBeInTheDocument();
    expect(screen.getByText("Decoded text")).toBeInTheDocument();
    expect(document.querySelector(".step-list")).toBeNull();
  });

  it("associates a finding with the recorded evidence item", async () => {
    render(<RunView runId="run-1" />);
    const link = await screen.findByRole("link", { name: /Evidence source-/ });
    expect(link).toHaveAttribute("href", "#evidence-source-1");
    expect(screen.getByText("Tool Abuse")).toBeInTheDocument();
  });

  it("explains an allow decision without calling the content safe", async () => {
    mockRun({
      ...detail,
      state: "COMPLETED",
      findings: [],
      action: {
        ...detail.action!,
        verdict: "ALLOW",
        reasons: ["WITHIN_CONFIRMED_AUTHORITY"],
      },
      ticket: {
        id: "ticket-1",
        title: "Created ticket",
        created_at: "2026-10-09T00:05:00Z",
        verified_at: "2026-10-09T00:06:00Z",
      },
    });
    render(<RunView runId="run-1" />);
    expect(
      await screen.findByText(
        "The deterministic guard allowed this exact proposed action.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("WITHIN_CONFIRMED_AUTHORITY")).toBeInTheDocument();
    expect(screen.getAllByText("Verified execution").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: "Open verified ticket" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/safe|sanitized|malware-free/i),
    ).not.toBeInTheDocument();
  });

  it("does not say verified when verification is absent", async () => {
    mockRun({
      ...detail,
      state: "COMPLETED",
      findings: [],
      action: {
        ...detail.action!,
        verdict: "ALLOW",
        reasons: ["WITHIN_CONFIRMED_AUTHORITY"],
      },
      ticket: {
        id: "ticket-1",
        title: "Created ticket",
        created_at: "2026-10-09T00:05:00Z",
        verified_at: null,
      },
    });
    render(<RunView runId="run-1" />);
    expect(
      await screen.findByText("Executed, verification not recorded"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Verified execution")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open committed ticket" }),
    ).toBeInTheDocument();
  });

  it("explains no action without treating it as a failure", async () => {
    mockRun({
      ...detail,
      state: "NO_ACTION",
      findings: [],
      action: null,
      analysis: detail.analysis,
    });
    render(<RunView runId="run-1" />);
    expect(
      await screen.findByRole("heading", { name: "No action required" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "The workflow completed without a business-side effect.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("explains an ingestion failure without reflecting source text", async () => {
    mockRun({
      ...detail,
      state: "FAILED",
      failure: "parser_limit_exceeded",
      findings: [],
      action: null,
      analysis: null,
    });
    render(<RunView runId="run-1" />);
    expect(
      (
        await screen.findAllByText(
          "The content exceeded a recorded processing limit.",
        )
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("parser_limit_exceeded")).toBeInTheDocument();
    expect(
      screen.getAllByText("No execution is recorded for this run.").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Verified execution")).not.toBeInTheDocument();
  });

  it("renders a long identifier as text", async () => {
    const marker = "<img src=x onerror=alert(1)>";
    mockRun({
      ...detail,
      workspace_id: marker,
    });
    render(<RunView runId="run-1" />);
    expect(await screen.findByText(marker)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
