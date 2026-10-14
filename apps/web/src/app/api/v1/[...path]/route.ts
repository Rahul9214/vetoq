import { auth } from "@clerk/nextjs/server";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { redact } from "@/lib/redact";

const allowedMethods = new Set(["GET", "POST"]);
const segmentPattern = /^[A-Za-z0-9_-]+$/;
const maxBodyBytes = 512 * 1024;
const upstreamTimeoutMs = 10_000;
const runFields = [
  "workspace_id",
  "goal",
  "source",
  "media_type",
  "confirmed",
] as const;

function jsonError(code: string, status: number, correlationId: string) {
  return NextResponse.json(
    {
      code,
      message: "Request could not be completed.",
      correlation_id: correlationId,
      retryable: status === 503 || status === 504,
    },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}

function logFailure(event: string, correlationId: string, error: unknown) {
  console.error(
    JSON.stringify({
      event,
      correlation_id: correlationId,
      error: error instanceof Error ? error.name : "unknown",
      detail: error instanceof Error ? redact(error.message) : "",
    }),
  );
}

function runSubmission(raw: string, correlationId: string) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return jsonError("invalid_input", 422, correlationId);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return jsonError("invalid_input", 422, correlationId);
  }
  const record = parsed as Record<string, unknown>;
  const allowed = new Set<string>(runFields);
  if (Object.keys(record).some((key) => !allowed.has(key))) {
    return jsonError("invalid_input", 422, correlationId);
  }
  if (runFields.some((key) => !(key in record))) {
    return jsonError("invalid_input", 422, correlationId);
  }
  if (typeof record.media_type !== "string" || record.media_type.length === 0) {
    return jsonError("invalid_input", 422, correlationId);
  }
  const forwarded: Record<string, unknown> = {};
  for (const key of runFields) forwarded[key] = record[key];
  return JSON.stringify(forwarded);
}

function upstreamBase() {
  const configured = process.env.VETOQ_API_URL ?? "http://127.0.0.1:18000";
  try {
    const url = new URL(configured);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

async function forward(
  request: NextRequest,
  context: RouteContext<"/api/v1/[...path]">,
) {
  const correlationId = crypto.randomUUID();
  try {
    if (!allowedMethods.has(request.method)) {
      return jsonError("method_not_allowed", 405, correlationId);
    }
    if (
      request.method === "POST" &&
      request.headers.get("origin") !== request.nextUrl.origin
    ) {
      return jsonError("invalid_origin", 403, correlationId);
    }
    const { path } = await context.params;
    if (
      !Array.isArray(path) ||
      path.length === 0 ||
      path.some((segment) => !segmentPattern.test(segment))
    ) {
      return jsonError("invalid_path", 400, correlationId);
    }

    let session: Awaited<ReturnType<typeof auth>>;
    let token: string | null;
    try {
      session = await auth();
      token = session.userId ? await session.getToken() : null;
    } catch (error) {
      logFailure("bff_identity_unavailable", correlationId, error);
      return jsonError("identity_unavailable", 503, correlationId);
    }
    if (!session.userId || !token) {
      return jsonError("authentication_required", 401, correlationId);
    }

    const base = upstreamBase();
    if (!base) {
      logFailure("bff_api_not_configured", correlationId, null);
      return jsonError("api_not_configured", 503, correlationId);
    }
    const target = new URL(`/api/v1/${path.join("/")}`, base);
    request.nextUrl.searchParams.forEach((value, key) =>
      target.searchParams.append(key, value),
    );
    const headers = new Headers({
      Authorization: `Bearer ${token}`,
      "X-Request-ID": correlationId,
    });
    const contentType = request.headers.get("content-type");
    const idempotencyKey = request.headers.get("idempotency-key");
    if (contentType) headers.set("Content-Type", contentType);
    if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
    const options: RequestInit = {
      method: request.method,
      headers,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(upstreamTimeoutMs),
    };
    if (request.method === "POST") {
      if (Number(request.headers.get("content-length") ?? 0) > maxBodyBytes) {
        return jsonError("input_limit", 413, correlationId);
      }
      const raw = await request.text();
      if (new TextEncoder().encode(raw).byteLength > maxBodyBytes) {
        return jsonError("input_limit", 413, correlationId);
      }
      if (path.length === 1 && path[0] === "runs") {
        const submission = runSubmission(raw, correlationId);
        if (submission instanceof NextResponse) return submission;
        options.body = submission;
        headers.set("Content-Type", "application/json");
      } else {
        options.body = raw;
      }
    }

    let upstream: Response;
    let body: string;
    try {
      upstream = await fetch(target, options);
      body = await upstream.text();
    } catch (error) {
      const timedOut = error instanceof Error && error.name === "TimeoutError";
      logFailure("bff_api_unreachable", correlationId, error);
      return jsonError(
        timedOut ? "api_timeout" : "api_unavailable",
        timedOut ? 504 : 503,
        correlationId,
      );
    }
    if (
      !(upstream.headers.get("content-type") ?? "").includes("application/json")
    ) {
      logFailure("bff_invalid_upstream_response", correlationId, null);
      return jsonError("invalid_upstream_response", 502, correlationId);
    }
    return new NextResponse(body, {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    logFailure("bff_internal_error", correlationId, error);
    return jsonError("internal_error", 500, correlationId);
  }
}

export const GET = forward;
export const POST = forward;
