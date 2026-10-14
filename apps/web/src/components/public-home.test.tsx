import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PublicHome } from "./public-home";

const banned = [
  "hackathon",
  "prototype",
  "prompt-injection firewall",
  "official nine",
  "multimodal",
  "multi-agent",
  "specialist agent",
  "PDF",
  "malware",
  "SOC 2",
  "Gartner",
  "testimonial",
];

describe("public product experience", () => {
  it("positions the hero around bounded authority", () => {
    render(<PublicHome />);
    expect(
      screen.getAllByText("Agent Execution Security Platform").length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Give AI room to work/i,
    );
    expect(
      screen.getAllByText("Trust the Goal. Verify the Action.").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Product illustration")).toBeInTheDocument();
    expect(screen.getByText("Inside scope")).toBeInTheDocument();
    expect(
      screen.getByText(/Stopped before the side effect/),
    ).toBeInTheDocument();
  });

  it("keeps the execution story and the three-way boundary truthful", () => {
    render(<PublicHome />);
    expect(screen.getByText("Illustrative execution path")).toBeInTheDocument();
    for (const step of [
      "Goal confirmed",
      "Inspect evidence",
      "Revalidate",
      "Verify",
    ]) {
      expect(screen.getByText(step)).toBeInTheDocument();
    }
    expect(
      screen.getByRole("heading", { name: "Authority" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Evidence" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Action" })).toBeInTheDocument();
    expect(screen.getByText("Action Guard")).toBeInTheDocument();
    expect(
      screen.getByText(/Evidence does not become authority/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Approval does not expand the Goal Lock/),
    ).toBeInTheDocument();
    expect(screen.getByText("Proposed")).toBeInTheDocument();
    expect(screen.getByText("Authorized")).toBeInTheDocument();
    expect(screen.getByText("Executed")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(
      screen.getByText(/An attempted tool call is not a completed result/),
    ).toBeInTheDocument();
  });

  it("places the lavender close above the footer and routes into real pages", () => {
    render(<PublicHome />);
    const hero = document.querySelector(".public-hero");
    const close = document.querySelector(".public-close");
    const footer = document.querySelector(".public-footer");
    expect(hero).not.toBeNull();
    expect(close).not.toBeNull();
    expect(footer).not.toBeNull();
    expect(hero?.classList.contains("public-close")).toBe(false);
    expect(
      hero!.compareDocumentPosition(close!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      close!.compareDocumentPosition(footer!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "See how VETOQ works" }),
    ).toHaveAttribute("href", "#execution-path");
    expect(
      screen.getByRole("link", { name: "See VETOQ in action" }),
    ).toHaveAttribute("href", "/sign-in");
    expect(
      screen.getByRole("link", { name: "Open secure workbench" }),
    ).toHaveAttribute("href", "/sign-in");
    expect(
      screen.getByRole("link", { name: "Create account" }),
    ).toHaveAttribute("href", "/sign-up");
  });

  it("does not market unsupported or fabricated proof", () => {
    render(<PublicHome />);
    const text = document.body.textContent ?? "";
    for (const phrase of banned) {
      expect(text.toLowerCase()).not.toContain(phrase.toLowerCase());
    }
    expect(text).toContain("plain text");
    expect(text).toContain("JSON");
    expect(text).toContain("Markdown");
    expect(text).toContain("HTML");
    expect(text).toContain("email");
    expect(screen.getByText("Goal confirmed")).toBeInTheDocument();
  });
});
