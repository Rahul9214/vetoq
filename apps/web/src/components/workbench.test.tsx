import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { Me } from "@/lib/contracts";
import { Workbench } from "./workbench";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", () => ({ api: vi.fn() }));

const identity: Me = {
  principal: "user_fixture",
  access: "active",
  workspaces: [
    {
      id: "00000000-0000-4000-8000-00000000000a",
      name: "Demo support",
      role: "reviewer",
      policy_revision: "support-triage/1",
    },
  ],
  template: {
    id: "support-triage/1",
    tool: "tickets.create",
    destination: "local-ticket-store",
    max_writes: 1,
    expires_minutes: 30,
  },
};

describe("authenticated security workbench", () => {
  beforeEach(() => {
    push.mockReset();
    vi.mocked(api).mockReset();
  });

  it("renders only server-authorized workspace state", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/me") return identity;
      return { items: [] };
    });
    render(<Workbench />);
    expect(
      await screen.findByRole("heading", {
        name: "Ready for a goal-bound run",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Demo support").length).toBeGreaterThan(0);
    expect(screen.getByText("Identity verified")).toBeInTheDocument();
    expect(screen.getByText("Workspace authorized")).toBeInTheDocument();
    expect(screen.getByText("tickets.create")).toBeInTheDocument();
  });

  it("keeps a verified but unprovisioned identity out of the workbench", async () => {
    vi.mocked(api).mockResolvedValue({
      ...identity,
      access: "not_provisioned",
      workspaces: [],
    });
    render(<Workbench />);
    expect(
      await screen.findByRole("heading", {
        name: "No VETOQ workspace membership",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Untrusted support-email text"),
    ).not.toBeInTheDocument();
  });

  it("surfaces persistence failure and does not accept source content", async () => {
    vi.mocked(api).mockRejectedValue(new Error("database_not_configured"));
    render(<Workbench />);
    expect(
      await screen.findByRole("heading", {
        name: "The authenticated workspace could not be opened.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("database_not_configured")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Untrusted support-email text"),
    ).not.toBeInTheDocument();
  });

  it("submits the confirmed Goal Lock and routes to its persisted run", async () => {
    vi.mocked(api).mockImplementation(async (path: string) => {
      if (path === "/me") return identity;
      if (path.startsWith("/runs?")) return { items: [] };
      if (path === "/runs") return { id: "run-persisted" };
      throw new Error("unexpected_call");
    });
    render(<Workbench />);
    const source = await screen.findByLabelText("Untrusted support-email text");
    fireEvent.change(source, {
      target: { value: "Synthetic support request: cannot access the portal." },
    });
    fireEvent.click(
      screen.getByLabelText(
        /I confirm this exact scope and that the source is synthetic/,
      ),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Start guarded analysis/ }),
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/runs/run-persisted"),
    );
    const submitCall = vi
      .mocked(api)
      .mock.calls.find(([path]) => path === "/runs");
    expect(submitCall?.[1]?.method).toBe("POST");
    expect(
      (submitCall?.[1]?.headers as Record<string, string>)["Idempotency-Key"],
    ).toBeTruthy();
    expect(submitCall?.[1]?.body).toContain('"confirmed":true');
  });
});
