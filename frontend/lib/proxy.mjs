/**
 * Pure helpers for the `/api/v1/[...path]` proxy route.
 *
 * These used to live inside `app/api/v1/[...path]/route.ts`, where importing the
 * module in a test drags in `next/server`. The behaviour is unchanged — this is the
 * same logic, moved somewhere a plain `node --test` can exercise it, because the
 * traversal guard, the upstream allowlist and the two numeric limits are exactly
 * the parts that must not regress silently.
 */

export const ALLOWED_METHODS = new Set(["GET", "POST"]);
export const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "x-api-key", "x-correlation-id"];
export const FORWARDED_RESPONSE_HEADERS = ["content-type", "x-correlation-id"];
export const SEGMENT_PATTERN = /^[A-Za-z0-9._~-]+$/;
export const DEFAULT_UPLOAD_BYTES = 50 * 1024 * 1024;
export const DEFAULT_TIMEOUT_SECONDS = 60;

/** Same shape the backend accepts for `X-Correlation-Id`. */
export const CORRELATION_ID_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;

/** Copy only explicitly allowed headers into a new mutable collection. */
export function forwardedHeaders(source, names) {
  const headers = new Headers();
  for (const name of names) {
    const value = source.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

/**
 * Accept a caller-supplied correlation id only if it is well formed.
 *
 * The proxy echoed whatever arrived — a five-kilobyte header came back verbatim in
 * self-generated error bodies while upstream responses carried the value the
 * backend had normalised, so the two layers disagreed and a single request had two
 * identities. Normalising here makes every hop agree by construction.
 */
export function normalizeCorrelationId(raw, generate = () => crypto.randomUUID()) {
  const candidate = (raw ?? "").trim();
  return CORRELATION_ID_PATTERN.test(candidate) ? candidate : generate();
}

/** Absolute upstream base URL, or null when unset/unsafe/misconfigured. */
export function resolveUpstream(env) {
  const upstream = env.FINRISK_API_UPSTREAM;
  if (!upstream) return null;
  let base;
  try {
    base = new URL(upstream);
  } catch {
    return null;
  }
  if (base.protocol !== "http:" && base.protocol !== "https:") return null;
  // Block cloud metadata / link-local addresses outright, and honour an explicit
  // allowlist when one is configured: `FINRISK_API_UPSTREAM=http://169.254.169.254`
  // otherwise turned the proxy into an unauthenticated reader of instance metadata.
  const host = base.hostname.toLowerCase();
  if (host.startsWith("169.254.") || host === "metadata.google.internal" || host === "[fd00:ec2::254]") {
    return null;
  }
  const allowed = (env.FINRISK_API_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean);
  if (allowed.length && !allowed.includes(host)) return null;
  return base;
}

/** Rebuild `/api/v1/<segments>` against the upstream, or null when unsafe. */
export function rebuildTarget(base, segments, search) {
  // Reject traversal and encoded separators before URL normalization can resolve
  // them away (`/api/v1/../../admin` used to reach an arbitrary upstream path).
  if (
    !Array.isArray(segments) ||
    segments.length === 0 ||
    segments.some(
      (segment) => !segment || segment === "." || segment === ".." || !SEGMENT_PATTERN.test(segment),
    )
  ) {
    return null;
  }
  const suffix = segments.join("/");
  const target = new URL(`/api/v1/${suffix}${search}`, base);
  if (target.origin !== base.origin || !target.pathname.startsWith("/api/v1/")) return null;
  return target;
}

/** Upload ceiling in bytes; the backend reads the same variable name. */
export function uploadLimit(env) {
  const parsed = Number.parseInt(env.FINRISK_MAX_UPLOAD_BYTES ?? String(DEFAULT_UPLOAD_BYTES), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_UPLOAD_BYTES;
}

/**
 * Bytes of multipart framing the proxy must tolerate on top of the file limit.
 *
 * The configured limit is a *file* size: the backend applies it to the uploaded PDF
 * bytes (`len(data) > max_bytes`). The proxy only sees the encoded request body, which
 * wraps that file in a boundary, part headers and the small text fields — so comparing
 * the body length against the file limit rejected valid uploads. Measured against the
 * real intake form the framing is a few hundred bytes; this allowance is orders of
 * magnitude above that while still bounding the request body, and anything above the
 * file limit still ends as a 413 (upstream when it slips through the allowance).
 */
export const MULTIPART_OVERHEAD_BYTES = 64 * 1024;

/** Request-body ceiling: the file limit plus multipart framing. */
export function uploadEnvelopeLimit(env) {
  return uploadLimit(env) + MULTIPART_OVERHEAD_BYTES;
}

/**
 * Proxy deadline: the backend's own budget plus a two-second grace so the backend's
 * 504 is relayed instead of being raced by the proxy's own abort.
 */
export function upstreamTimeoutMs(env, graceMs = 2_000) {
  const seconds = Number.parseFloat(env.FINRISK_ANALYSIS_TIMEOUT_SECONDS ?? String(DEFAULT_TIMEOUT_SECONDS));
  const effective = Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_TIMEOUT_SECONDS;
  return effective * 1_000 + graceMs;
}
