import { NextRequest, NextResponse } from "next/server";
import {
  ALLOWED_METHODS,
  FORWARDED_REQUEST_HEADERS,
  FORWARDED_RESPONSE_HEADERS,
  normalizeCorrelationId,
  rebuildTarget,
  resolveUpstream,
  uploadEnvelopeLimit,
  upstreamTimeoutMs,
} from "../../../../lib/proxy.mjs";

// The file limit is enforced by the backend against the uploaded PDF bytes; the proxy
// bounds the *encoded body*, so it has to allow the multipart framing on top. Using
// the bare file limit here made a PDF of exactly the configured size come back as 413
// before the backend ever saw it.
const MAX_UPLOAD_BYTES = uploadEnvelopeLimit(process.env);
const UPSTREAM_TIMEOUT_MS = upstreamTimeoutMs(process.env);

class BodyLimitError extends Error {}

function errorResponse(detail: string, status: number, correlationId: string) {
  return NextResponse.json(
    { detail, correlation_id: correlationId },
    { status, headers: { "X-Correlation-Id": correlationId } },
  );
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
  const correlationId = normalizeCorrelationId(request.headers.get("x-correlation-id"));
  if (!ALLOWED_METHODS.has(request.method)) {
    return errorResponse("method not allowed", 405, correlationId);
  }
  const base = resolveUpstream(process.env);
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
