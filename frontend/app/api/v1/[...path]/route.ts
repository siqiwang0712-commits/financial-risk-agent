import { NextRequest, NextResponse } from "next/server";

// Reads and writes are the only methods the Workbench performs. DELETE/PUT/PATCH
// were re-exported to the browser for no reason.
const ALLOWED_METHODS = new Set(["GET", "POST"]);
// Only the headers the upstream actually needs. Forwarding the client's whole
// header set leaked `cookie`/`authorization` to the upstream and let a caller
// influence it arbitrarily.
const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "x-api-key", "x-correlation-id"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "x-correlation-id"];
// All three layers derive from one seconds-based deployment setting. The proxy
// waits two seconds beyond the backend deadline so it can relay the backend's
// 504 instead of racing it with a client-side abort.
const configuredAnalysisSeconds = Number.parseFloat(
  process.env.FINRISK_ANALYSIS_TIMEOUT_SECONDS ?? "60",
);
const UPSTREAM_TIMEOUT_MS = (
  Number.isFinite(configuredAnalysisSeconds) && configuredAnalysisSeconds > 0
    ? configuredAnalysisSeconds
    : 60
) * 1_000 + 2_000;
const MAX_UPLOAD_BYTES = Number.parseInt(
  process.env.FINRISK_MAX_UPLOAD_BYTES ?? String(50 * 1024 * 1024),
  10,
);
const SEGMENT_PATTERN = /^[A-Za-z0-9._~-]+$/;

class BodyLimitError extends Error {}

function errorResponse(detail: string, status: number, correlationId: string) {
  return NextResponse.json(
    { detail, correlation_id: correlationId },
    { status, headers: { "X-Correlation-Id": correlationId } },
  );
}

function resolveUpstream(): URL | null {
  const upstream = process.env.FINRISK_API_UPSTREAM;
  if (!upstream) return null;
  let base: URL;
  try {
    base = new URL(upstream);
  } catch {
    return null;
  }
  if (base.protocol !== "http:" && base.protocol !== "https:") return null;
  // Block cloud metadata / link-local addresses outright, and honour an explicit
  // allowlist when one is configured. Without this, `FINRISK_API_UPSTREAM=
  // http://169.254.169.254` turned the proxy into an unauthenticated reader of
  // instance metadata.
  const host = base.hostname.toLowerCase();
  if (host.startsWith("169.254.") || host === "metadata.google.internal" || host === "[fd00:ec2::254]") {
    return null;
  }
  const allowed = (process.env.FINRISK_API_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean);
  if (allowed.length && !allowed.includes(host)) return null;
  return base;
}

function rebuildTarget(base: URL, segments: string[], search: string): URL | null {
  // Reject traversal and encoded separators before URL normalization can resolve
  // them away (`/api/v1/../../admin` used to reach an arbitrary upstream path).
  if (segments.some((segment) => !segment || segment === "." || segment === ".." || !SEGMENT_PATTERN.test(segment))) {
    return null;
  }
  const suffix = segments.join("/");
  const target = new URL(`/api/v1/${suffix}${search}`, base);
  if (target.origin !== base.origin || !target.pathname.startsWith("/api/v1/")) return null;
  return target;
}

function boundedBody(stream: ReadableStream<Uint8Array> | null): ReadableStream<Uint8Array> | undefined {
  if (!stream) return undefined;
  let received = 0;
  const reader = stream.getReader();
  return new ReadableStream({
    async pull(controller) {
      // A client that disconnects mid-upload makes `read()` reject. Without this
      // the reader is never released, so the stream stays locked and the request
      // leaks until the socket times out.
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (cause) {
        await reader.cancel(String(cause)).catch(() => undefined);
        return controller.error(cause);
      }
      if (chunk.done) return controller.close();
      received += chunk.value.byteLength;
      if (received > MAX_UPLOAD_BYTES) {
        await reader.cancel("request body exceeds configured upload limit");
        return controller.error(new BodyLimitError("request body exceeds configured upload limit"));
      }
      controller.enqueue(chunk.value);
    },
    async cancel(reason) { await reader.cancel(reason); },
  });
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const correlationId = request.headers.get("x-correlation-id") || crypto.randomUUID();
  if (!ALLOWED_METHODS.has(request.method)) {
    return errorResponse("method not allowed", 405, correlationId);
  }
  const base = resolveUpstream();
  if (!base) {
    return errorResponse("API upstream is unavailable", 503, correlationId);
  }
  const { path } = await context.params;
  const target = rebuildTarget(base, path, request.nextUrl.search);
  if (!target) {
    return errorResponse("invalid upstream path", 400, correlationId);
  }
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-correlation-id", correlationId);
  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_UPLOAD_BYTES) {
    return errorResponse("request body exceeds configured upload limit", 413, correlationId);
  }
  // Never materialise an untrusted multipart upload in the proxy. The bounded
  // stream enforces the same limit when content-length is absent or dishonest.
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : boundedBody(request.body);
  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      // Node's fetch requires duplex for a streamed request; Next's RequestInit
      // declarations do not expose it yet.
      duplex: "half",
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    } as RequestInit & { duplex: "half" });
    const responseHeaders = new Headers();
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    if (!responseHeaders.has("x-correlation-id")) {
      responseHeaders.set("x-correlation-id", correlationId);
    }
    if (!response.ok) {
      // Preserve status and correlation but only relay the documented, safe error
      // field. Internal stack traces and provider details stay upstream.
      const upstream = await response.json().catch(() => ({}));
      const detail = typeof upstream?.detail === "string" ? upstream.detail : "upstream error";
      return NextResponse.json(
        { detail, correlation_id: responseHeaders.get("x-correlation-id") },
        { status: response.status, headers: responseHeaders },
      );
    }
    return new NextResponse(response.body, { status: response.status, headers: responseHeaders });
  } catch (error) {
    if (error instanceof BodyLimitError || String(error).includes("configured upload limit")) {
      return errorResponse("request body exceeds configured upload limit", 413, correlationId);
    }
    const name = error instanceof Error ? error.name : "";
    if (name === "TimeoutError" || name === "AbortError") {
      return errorResponse("API upstream request timed out", 504, correlationId);
    }
    return errorResponse("API upstream request failed", 502, correlationId);
  }
}

export const dynamic = "force-dynamic";
export { proxy as GET, proxy as POST };
