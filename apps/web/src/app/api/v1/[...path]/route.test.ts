// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

const session = vi.hoisted(() => ({
  auth: vi.fn(),
}));

vi.mock("@clerk/nextjs/server", () => ({ auth: session.auth }));

const token =
  "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyX2ZpeHR1cmUifQ.c2lnbmF0dXJl";
const fetchMock = vi.fn<typeof fetch>();

function call(
  method: "GET" | "POST",
  path: string[],
  init: { headers?: Record<string, string>; body?: string } = {},
) {
  const request = new NextRequest(
    `http://localhost:3000/api/v1/${path.join("/")}`,
    { method, ...init },
  );
  const context = { params: Promise.resolve({ path }) };
  return (method === "GET" ? GET : POST)(request, context);
}

function signedIn() {
  session.auth.mockResolvedValue({
    userId: "user_fixture",
    getToken: vi.fn(async () => token),
  });
}

async function expectContract(
  response: Response,
  status: number,
  code: string,
) {
  expect(response.status).toBe(status);
  expect(response.headers.get("content-type")).toBe("application/json");
  const body = (await response.json()) as Record<string, unknown>;
  expect(body.code).toBe(code);
  expect(body.correlation_id).toMatch(/^[0-9a-f-]{36}$/);
  return body;
}

describe("same-origin BFF", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns a JSON 401 without calling the API when signed out", async () => {
    session.auth.mockResolvedValue({ userId: null, getToken: vi.fn() });
    await expectContract(
      await call("GET", ["me"]),
      401,
      "authentication_required",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports an unavailable identity boundary as 503 and redacts logs", async () => {
    session.auth.mockRejectedValue(
      new Error(`Clerk failed with Bearer ${token} and sk_test_fixture`),
    );
    await expectContract(
      await call("GET", ["me"]),
      503,
      "identity_unavailable",
    );
    const logged = vi.mocked(console.error).mock.calls.flat().join(" ");
    expect(logged).toContain("bff_identity_unavailable");
    expect(logged).not.toContain(token);
    expect(logged).not.toContain("sk_test_fixture");
  });

  it("forwards the server-side session token and correlation id", async () => {
    signedIn();
    fetchMock.mockResolvedValue(
      Response.json({ principal: "user_fixture", access: "active" }),
    );
    const response = await call("GET", ["me"]);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      principal: "user_fixture",
      access: "active",
    });
    const [target, init] = fetchMock.mock.calls[0]!;
    expect(String(target)).toBe("http://127.0.0.1:18000/api/v1/me");
    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBe(`Bearer ${token}`);
    expect(headers.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("passes structured API errors through unchanged", async () => {
    signedIn();
    fetchMock.mockResolvedValue(
      Response.json({ code: "workspace_forbidden" }, { status: 403 }),
    );
    const response = await call("GET", ["runs"]);
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ code: "workspace_forbidden" });
  });

  it("never relays a non-JSON upstream body", async () => {
    signedIn();
    fetchMock.mockResolvedValue(
      new Response("<html>Internal Server Error</html>", {
        status: 500,
        headers: { "content-type": "text/html" },
      }),
    );
    const response = await call("GET", ["me"]);
    const body = await expectContract(
      response,
      502,
      "invalid_upstream_response",
    );
    expect(JSON.stringify(body)).not.toContain("html");
  });

  it("separates an unreachable API from a slow one", async () => {
    signedIn();
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"));
    await expectContract(await call("GET", ["me"]), 503, "api_unavailable");
    fetchMock.mockRejectedValueOnce(
      new DOMException("The operation timed out.", "TimeoutError"),
    );
    await expectContract(await call("GET", ["me"]), 504, "api_timeout");
  });

  it("rejects invalid requests before authentication", async () => {
    await expectContract(await call("GET", [".."]), 400, "invalid_path");
    await expectContract(
      await call("POST", ["runs"], {
        headers: { origin: "https://attacker.invalid" },
        body: "{}",
      }),
      403,
      "invalid_origin",
    );
    expect(session.auth).not.toHaveBeenCalled();
  });

  it("bounds request bodies before forwarding", async () => {
    signedIn();
    const response = await call("POST", ["runs"], {
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: "x".repeat(512 * 1024 + 1),
    });
    await expectContract(response, 413, "input_limit");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards only the declared-format submission", async () => {
    signedIn();
    fetchMock.mockResolvedValue(
      Response.json({ id: "run-1" }, { status: 202 }),
    );
    const response = await call("POST", ["runs"], {
      headers: {
        origin: "http://localhost:3000",
        "content-type": "text/plain",
        "idempotency-key": "key-1",
      },
      body: JSON.stringify({
        workspace_id: "workspace-1",
        goal: "Create one ticket.",
        source: "hello",
        media_type: "text/plain; charset=UTF-8",
        confirmed: true,
      }),
    });
    expect(response.status).toBe(202);
    const [target, init] = fetchMock.mock.calls[0]!;
    expect(String(target)).toBe("http://127.0.0.1:18000/api/v1/runs");
    const headers = new Headers(init?.headers);
    expect(headers.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
    expect(headers.get("idempotency-key")).toBe("key-1");
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({
      workspace_id: "workspace-1",
      goal: "Create one ticket.",
      source: "hello",
      media_type: "text/plain; charset=UTF-8",
      confirmed: true,
    });
  });

  it("rejects sanitized and other unauthorized submission fields", async () => {
    signedIn();
    const sentinel = "SENTINEL_BFF_SOURCE";
    const response = await call("POST", ["runs"], {
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        workspace_id: "workspace-1",
        goal: "Create one ticket.",
        source: sentinel,
        media_type: "text/plain",
        confirmed: true,
        sanitized: true,
        source_class: "trusted",
        template: "support-triage/1",
      }),
    });
    const body = await expectContract(response, 422, "invalid_input");
    expect(JSON.stringify(body)).not.toContain(sentinel);
    expect(fetchMock).not.toHaveBeenCalled();
    const logged = vi.mocked(console.error).mock.calls.flat().join(" ");
    expect(logged).not.toContain(sentinel);
  });

  it("passes a structured ingestion error without the source body", async () => {
    signedIn();
    const sentinel = "SENTINEL_UPSTREAM_SOURCE";
    fetchMock.mockResolvedValue(
      Response.json(
        { code: "malformed_content", message: "Request input is invalid." },
        { status: 422 },
      ),
    );
    const response = await call("POST", ["runs"], {
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        workspace_id: "workspace-1",
        goal: "Create one ticket.",
        source: sentinel,
        media_type: "application/json",
        confirmed: true,
      }),
    });
    expect(response.status).toBe(422);
    const body = await response.text();
    expect(body).toContain("malformed_content");
    expect(body).not.toContain(sentinel);
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).toContain(sentinel);
  });

  it("leaves non-submission posts on the raw proxy path", async () => {
    signedIn();
    fetchMock.mockResolvedValue(Response.json({ state: "CANCELLED" }));
    await call("POST", ["runs", "run-1", "cancel"], {
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: "{}",
    });
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe("{}");
  });
});
