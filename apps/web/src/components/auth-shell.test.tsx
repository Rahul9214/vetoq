import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuthShell } from "./auth-shell";
import SignInPage from "../app/sign-in/[[...sign-in]]/page";
import SignUpPage from "../app/sign-up/[[...sign-up]]/page";

vi.mock("@clerk/nextjs", () => ({
  SignIn: () => (
    <form aria-label="Clerk sign in">
      <label>
        Email address
        <input name="identifier" />
      </label>
    </form>
  ),
  SignUp: () => (
    <form aria-label="Clerk sign up">
      <label>
        Email address
        <input name="emailAddress" />
      </label>
    </form>
  ),
}));

describe("auth shell", () => {
  it("keeps the product narrative beside the Clerk control", () => {
    render(<SignInPage />);
    expect(
      screen.getByRole("heading", { name: "Define the authority." }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sign in" })).toBeInTheDocument();
    const form = screen.getByRole("form", { name: "Clerk sign in" });
    expect(form).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /bypass/i }),
    ).not.toBeInTheDocument();
    const narrative = document.querySelector(".auth-narrative");
    const panel = document.querySelector(".auth-panel");
    expect(narrative).not.toBeNull();
    expect(panel).not.toBeNull();
    expect(panel).toContainElement(form);
    expect(
      narrative!.compareDocumentPosition(panel!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("routes sign-up through the same shell", () => {
    render(<SignUpPage />);
    expect(
      screen.getByRole("heading", { name: "Verify the action." }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Create account" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("form", { name: "Clerk sign up" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/sign-in",
    );
  });

  it("leaves a reachable field inside the auth surface", () => {
    render(
      <AuthShell mode="sign-in">
        <form aria-label="Clerk sign in">
          <label>
            Email address
            <input name="identifier" />
          </label>
        </form>
      </AuthShell>,
    );
    const field = screen.getByRole("textbox", { name: "Email address" });
    field.focus();
    expect(field).toHaveFocus();
    expect(document.querySelector(".auth-panel")).toContainElement(field);
  });
});
