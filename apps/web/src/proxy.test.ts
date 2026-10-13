// @vitest-environment node
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";
import packageJson from "../package.json";
import proxy, { config } from "./proxy";

type Handler = (
  auth: { protect: () => Promise<void> },
  request: NextRequest,
) => Promise<void>;

vi.mock("@clerk/nextjs/server", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@clerk/nextjs/server")>()),
  clerkMiddleware: (handler: Handler) => handler,
}));

const matches = (url: string) => unstable_doesMiddlewareMatch({ config, url });

describe("Clerk proxy boundary", () => {
  it("runs Clerk for the BFF so server auth() has session state", () => {
    expect(matches("http://localhost:3000/api/v1/me")).toBe(true);
    expect(matches("http://localhost:3000/api/v1/runs/abc/events")).toBe(true);
  });

  it("runs Clerk for authenticated and auth pages", () => {
    for (const path of [
      "/",
      "/sign-in",
      "/sign-in/factor-one",
      "/sign-up",
      "/runs/abc",
      "/tickets/abc",
    ]) {
      expect(matches(`http://localhost:3000${path}`)).toBe(true);
    }
  });

  it("does not run Clerk for static framework assets", () => {
    expect(matches("http://localhost:3000/_next/static/app.js")).toBe(false);
    expect(matches("http://localhost:3000/favicon.ico")).toBe(false);
  });

  it("binds the server to the origin Next.js presents to Clerk", () => {
    // Clerk rewrites pass-through requests to request.url. A different server
    // origin makes Next.js proxy that rewrite back to itself indefinitely.
    expect(new NextRequest("http://127.0.0.1:3000/api/v1/me").url).toBe(
      "http://localhost:3000/api/v1/me",
    );
    expect(packageJson.scripts.dev).toContain("--hostname localhost");
    expect(packageJson.scripts.start).toContain("--hostname localhost");
  });

  it("protects pages but leaves BFF authentication to its JSON contract", async () => {
    const handler = proxy as unknown as Handler;
    const protect = vi.fn(async () => undefined);
    await handler(
      { protect },
      new NextRequest("http://localhost:3000/api/v1/me"),
    );
    await handler({ protect }, new NextRequest("http://localhost:3000/"));
    expect(protect).not.toHaveBeenCalled();
    await handler(
      { protect },
      new NextRequest("http://localhost:3000/runs/abc"),
    );
    await handler(
      { protect },
      new NextRequest("http://localhost:3000/tickets/x"),
    );
    expect(protect).toHaveBeenCalledTimes(2);
  });
});
