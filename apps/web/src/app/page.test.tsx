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
      /Give AI room to work/i,
    );
    expect(
      screen.getAllByText("Trust the Goal. Verify the Action.").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByRole("banner").length).toBeGreaterThan(0);
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Sign in" }).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("link", { name: "Open secure workbench" }).length,
    ).toBeGreaterThan(0);
  });

  it("explains the full security boundary without fabricated results", () => {
    authState.isLoaded = true;
    authState.isSignedIn = false;
    render(<HomeView initialUserId={null} />);
    expect(
      screen.getByRole("heading", {
        name: "Credentials do not answer whether this action was delegated.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Product illustration")).toBeInTheDocument();
    expect(screen.getByText("Illustrative execution path")).toBeInTheDocument();
    expect(
      screen.queryByText("Indirect Prompt Injection"),
    ).not.toBeInTheDocument();
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
      screen.queryByRole("heading", { name: /Give AI room to work/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "Guarded execution workspace",
      }),
    ).not.toBeInTheDocument();
  });

  it("does not flash public marketing UI for a server-authenticated session", () => {
    authState.isLoaded = false;
    authState.isSignedIn = false;
    render(<HomeView initialUserId="user_operator" />);
    expect(
      screen.queryByRole("heading", { name: /Give AI room to work/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Guarded execution workspace",
      }),
    ).toBeInTheDocument();
  });
});
