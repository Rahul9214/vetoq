import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HomeView } from "./home-view";

const authState = vi.hoisted(() => ({
  isLoaded: true,
  isSignedIn: false,
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => authState,
  UserButton: () => null,
}));

vi.mock("@/lib/api", () => ({
  api: vi.fn(async (path: string) => {
    if (path === "/me") {
      return {
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
    }
    return { items: [] };
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("VETOQ product shell", () => {
  it("provides semantic product identity and public authentication controls", () => {
    authState.isLoaded = true;
    authState.isSignedIn = false;
    render(<HomeView initialUserId={null} />);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Trust the goal.*Verify the action/i,
    );
    expect(screen.getAllByRole("banner").length).toBeGreaterThan(0);
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Sign in" }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("link", { name: "Start secure run" }),
    ).toBeInTheDocument();
  });

  it("explains the full security boundary without fabricated results", () => {
    authState.isLoaded = true;
    authState.isSignedIn = false;
    render(<HomeView initialUserId={null} />);
    expect(
      screen.getByRole("heading", {
        name: "Content can request an action. It cannot authorize one.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Illustration · not live telemetry/),
    ).toBeInTheDocument();
    expect(screen.getByText("Indirect Prompt Injection")).toBeInTheDocument();
    expect(screen.getAllByText("tickets.create")).toHaveLength(3);
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("keeps a branded loading shell while the session is unknown", () => {
    authState.isLoaded = false;
    authState.isSignedIn = false;
    render(<HomeView initialUserId={null} />);
    expect(
      screen.getByRole("status", { name: "Loading VETOQ session" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: /Trust the goal/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "Verify the next action before it becomes an effect.",
      }),
    ).not.toBeInTheDocument();
  });

  it("does not flash public marketing UI for a server-authenticated session", () => {
    authState.isLoaded = false;
    authState.isSignedIn = false;
    render(<HomeView initialUserId="user_operator" />);
    expect(
      screen.queryByRole("heading", { name: /Trust the goal/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Verify the next action before it becomes an effect.",
      }),
    ).toBeInTheDocument();
  });
});
