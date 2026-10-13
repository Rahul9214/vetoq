import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { RunDetail } from "@/lib/contracts";
import { RunView } from "./run-view";

vi.mock("@/lib/api", () => ({ api: vi.fn() }));

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
  sources: [
    {
      id: "source-1",
      origin: "pasted-email",
      supplier: "user",
      digest: "b".repeat(64),
      trust: "untrusted",
      complete: true,
      expires_at: "2026-10-10T00:00:00Z",
    },
  ],
};

describe("run evidence", () => {
  beforeEach(() => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.includes("/events")) return { items: [] };
      if (path.includes("/content/")) {
        return { content: '<img src=x onerror="alert(1)">' };
      }
      return detail;
    });
  });

  it("hides approval controls from the requesting principal", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.includes("/events")) return { items: [] };
      return {
        ...detail,
        state: "AWAITING_REVIEW",
        action: {
          ...detail.action,
          verdict: "REVIEW",
          reasons: ["MATERIAL_UNCERTAINTY"],
        },
        review: {
          id: "review-1",
          digest: "c".repeat(64),
          expires_at: "2026-10-09T00:10:00Z",
          decision: null,
          consumed: false,
          eligible: false,
        },
      };
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
  });

  it("shows approval controls only when the backend marks the reviewer eligible", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path.includes("/events")) return { items: [] };
      return {
        ...detail,
        state: "AWAITING_REVIEW",
        goal_lock: {
          ...detail.goal_lock,
          tool_version: 1,
          destination: "local-ticket-store",
        },
        action: {
          ...detail.action,
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
          expires_at: "2026-10-09T00:10:00Z",
          decision: null,
          consumed: false,
          eligible: true,
        },
        ticket: null,
      };
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
    expect(screen.getAllByText("BLOCK").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", { name: "No privileged write occurred" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open ticket" }),
    ).not.toBeInTheDocument();
  });

  it("presents the security evidence in the required causal order", async () => {
    render(<RunView runId="run-1" />);
    await screen.findByRole("heading", { name: "Goal Lock" });
    const stageNames = [
      "Goal Lock",
      "Source / Provenance",
      "Inspection Findings",
      "AI Proposal",
      "Action Guard",
      "Execution Outcome",
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
});
