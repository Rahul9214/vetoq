import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "./page";

describe("foundation shell", () => {
  it("provides one main landmark and a descriptive primary heading", () => {
    render(<Home />);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Trust the Goal.Verify the Action.",
    );
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
  it("discloses unavailable workflows without fake actions", () => {
    render(<Home />);
    expect(
      screen.getByRole("region", { name: "Foundation only" }),
    ).toHaveTextContent("Security workflows are not available in this build.");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });
});
