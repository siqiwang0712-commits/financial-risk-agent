import { NextRequest, NextResponse } from "next/server";

// Reads and writes are the only methods the Workbench performs. DELETE/PUT/PATCH
// were re-exported to the browser for no reason.
const ALLOWED_METHODS = new Set(["GET", "POST"]);
// Only the headers the upstream actually needs. Forwarding the client's whole
// header set leaked `cookie`/`authorization` to the upstream and let a caller
// influence it arbitrarily.
const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "x-api-key", "x-correlation-id"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "content-length"];
const UPSTREAM_TIMEOUT_MS = 10_000;
const SEGMENT_PATTERN = /^[A-Za-z0-9._~-]+$/;

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

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (!ALLOWED_METHODS.has(request.method)) {
    return NextResponse.json({ detail: "method not allowed" }, { status: 405 });
  }
  const base = resolveUpstream();
  if (!base) {
    return NextResponse.json({ detail: "API upstream is unavailable" }, { status: 503 });
  }
  const { path } = await context.params;
  const target = rebuildTarget(base, path, request.nextUrl.search);
  if (!target) {
    return NextResponse.json({ detail: "invalid upstream path" }, { status: 400 });
  }
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();
  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const responseHeaders = new Headers();
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    if (!response.ok) {
      // Do not relay the upstream body or status-specific details to the browser.
      return NextResponse.json({ detail: "upstream error" }, { status: response.status, headers: responseHeaders });
    }
    return new NextResponse(response.body, { status: response.status, headers: responseHeaders });
  } catch {
    return NextResponse.json({ detail: "API upstream request failed" }, { status: 502 });
  }
}

export const dynamic = "force-dynamic";
export { proxy as GET, proxy as POST };
