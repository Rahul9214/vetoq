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

describe("same-origin BFF lineage passthrough", () => {
  const runId = "0b0c3f0e-8a63-4e0e-9a55-6f0f5f3f8c11";
  const nodeId = "6d1f6a52-0c47-4c5c-8a07-0d3a7f0b2e90";
  const actionId = "a3a1d0f7-52a5-4f0b-b8a6-1c4f2f6e9d33";
  const lineagePaths = [
    ["runs", runId, "lineage"],
    ["runs", runId, "lineage", "nodes", nodeId],
    ["runs", runId, "lineage", "actions", actionId],
  ];

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("forwards each lineage GET with the server-side token and correlation id", async () => {
    signedIn();
    for (const path of lineagePaths) {
      fetchMock.mockResolvedValueOnce(Response.json({ ok: path.length }));
      const response = await call("GET", path);
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ ok: path.length });
      expect(response.headers.get("cache-control")).toBe("no-store");
      expect(response.headers.get("content-type")).toBe("application/json");
    }
    expect(fetchMock.mock.calls.map(([target]) => String(target))).toEqual(
      lineagePaths.map(
        (path) => `http://127.0.0.1:18000/api/v1/${path.join("/")}`,
      ),
    );
    for (const [, init] of fetchMock.mock.calls) {
      const headers = new Headers(init?.headers);
      expect(init?.method).toBe("GET");
      expect(init?.body).toBeUndefined();
      expect(init?.cache).toBe("no-store");
      expect(headers.get("authorization")).toBe(`Bearer ${token}`);
      expect(headers.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
    }
  });

  it("never forwards a client-supplied workspace, cookie, or other header", async () => {
    signedIn();
    fetchMock.mockResolvedValue(Response.json({ ok: true }));
    await call("GET", lineagePaths[0]!, {
      headers: {
        "x-workspace-id": "workspace-attacker",
        cookie: "session=stolen",
        authorization: "Bearer attacker",
        "x-request-id": "attacker-chosen",
      },
    });
    const headers = new Headers(fetchMock.mock.calls[0]![1]?.headers);
    expect([...headers.keys()].sort()).toEqual([
      "authorization",
      "x-request-id",
    ]);
    expect(headers.get("authorization")).toBe(`Bearer ${token}`);
    expect(headers.get("x-request-id")).not.toBe("attacker-chosen");
  });

  it("forwards the direction selector and passes an invalid one through as 422", async () => {
    signedIn();
    fetchMock.mockResolvedValueOnce(Response.json({ direction: "ancestors" }));
    const ok = await call("GET", [...lineagePaths[1]!], {});
    expect(ok.status).toBe(200);
    expect(String(fetchMock.mock.calls[0]![0])).toBe(
      `http://127.0.0.1:18000/api/v1/runs/${runId}/lineage/nodes/${nodeId}`,
    );

    const request = new NextRequest(
      `http://localhost:3000/api/v1/runs/${runId}/lineage/nodes/${nodeId}?direction=ancestors`,
    );
    fetchMock.mockResolvedValueOnce(Response.json({ direction: "ancestors" }));
    await GET(request, { params: Promise.resolve({ path: lineagePaths[1]! }) });
    expect(String(fetchMock.mock.calls[1]![0])).toBe(
      `http://127.0.0.1:18000/api/v1/runs/${runId}/lineage/nodes/${nodeId}?direction=ancestors`,
    );

    const invalid = new NextRequest(
      `http://localhost:3000/api/v1/runs/${runId}/lineage/nodes/${nodeId}?direction=sideways`,
    );
    fetchMock.mockResolvedValueOnce(
      Response.json(
        {
          code: "invalid_input",
          message: "Request input is invalid.",
          correlation_id: "c0ffee00-0000-4000-8000-000000000000",
          retryable: false,
        },
        { status: 422 },
      ),
    );
    const refused = await GET(invalid, {
      params: Promise.resolve({ path: lineagePaths[1]! }),
    });
    expect(refused.status).toBe(422);
    expect(((await refused.json()) as { code: string }).code).toBe(
      "invalid_input",
    );
    expect(refused.headers.get("cache-control")).toBe("no-store");
    expect(String(fetchMock.mock.calls[2]![0])).toContain("direction=sideways");
  });

  it("keeps the non-enumerating 404 and the API error body unchanged", async () => {
    signedIn();
    const upstreamBody = {
      code: "not_found",
      message: "Request could not be completed.",
      correlation_id: "c0ffee00-0000-4000-8000-000000000001",
      retryable: false,
    };
    for (const path of lineagePaths) {
      fetchMock.mockResolvedValueOnce(
        Response.json(upstreamBody, { status: 404 }),
      );
      const response = await call("GET", path);
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual(upstreamBody);
      expect(response.headers.get("cache-control")).toBe("no-store");
    }
  });

  it("answers 401 without calling the API when signed out", async () => {
    session.auth.mockResolvedValue({ userId: null, getToken: vi.fn() });
    for (const path of lineagePaths) {
      await expectContract(
        await call("GET", path),
        401,
        "authentication_required",
      );
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("applies its own no-store header whatever the upstream says", async () => {
    signedIn();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: {
          "content-type": "application/json",
          "cache-control": "public, max-age=600",
        },
      }),
    );
    const response = await call("GET", lineagePaths[0]!);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("maps an unreachable, slow, or non-JSON upstream to the safe shapes", async () => {
    signedIn();
    fetchMock.mockRejectedValueOnce(
      new TypeError("connect ECONNREFUSED 10.0.0.9:5432"),
    );
    const unavailable = await expectContract(
      await call("GET", lineagePaths[0]!),
      503,
      "api_unavailable",
    );
    expect(unavailable.retryable).toBe(true);
    expect(JSON.stringify(unavailable)).not.toContain("ECONNREFUSED");
    fetchMock.mockRejectedValueOnce(
      new DOMException("The operation timed out.", "TimeoutError"),
    );
    await expectContract(
      await call("GET", lineagePaths[1]!),
      504,
      "api_timeout",
    );
    fetchMock.mockResolvedValueOnce(
      new Response(
        "<html><pre>Traceback (most recent call last)</pre></html>",
        {
          status: 500,
          headers: { "content-type": "text/html" },
        },
      ),
    );
    const html = await expectContract(
      await call("GET", lineagePaths[2]!),
      502,
      "invalid_upstream_response",
    );
    expect(JSON.stringify(html)).not.toContain("Traceback");
    fetchMock.mockResolvedValueOnce(
      Response.json(
        { code: "database_not_configured", retryable: true },
        { status: 503 },
      ),
    );
    const upstream503 = await call("GET", lineagePaths[0]!);
    expect(upstream503.status).toBe(503);
    expect(upstream503.headers.get("cache-control")).toBe("no-store");
  });

  it("rejects a malformed or entity-prefixed id before authentication", async () => {
    for (const bad of ["content:abc", "a/b", "..", "a b", "%00"]) {
      await expectContract(
        await call("GET", ["runs", runId, "lineage", "nodes", bad]),
        400,
        "invalid_path",
      );
    }
    expect(session.auth).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards extra query parameters without adding a body or workspace header", async () => {
    signedIn();
    fetchMock.mockResolvedValue(Response.json({ ok: true }));
    const request = new NextRequest(
      `http://localhost:3000/api/v1/runs/${runId}/lineage?workspace_id=attacker&depth=99999&unlimited=true`,
    );
    const response = await GET(request, {
      params: Promise.resolve({ path: lineagePaths[0]! }),
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const [target, init] = fetchMock.mock.calls[0]!;
    const forwarded = new URL(String(target));
    expect(forwarded.searchParams.get("workspace_id")).toBe("attacker");
    expect(forwarded.searchParams.get("depth")).toBe("99999");
    expect(forwarded.searchParams.get("unlimited")).toBe("true");
    expect(init?.body).toBeUndefined();
    const headers = new Headers(init?.headers);
    expect(headers.get("x-workspace-id")).toBeNull();
  });
});
