/**
 * Pure policy for the `/api/v1/[...path]` proxy route.
 *
 * Extracted from `route.ts` so the allowlists and the `content-length` rule can
 * be exercised by `node --test`. The P0 this guards against - relaying the
 * upstream's `content-length` while replacing its body - was invisible to every
 * test in the repository because the rule lived inside a Next module that the
 * test runner cannot import.
 *
 * Anything accepted here is a `Headers`-like object (anything with `.get`), so
 * the helpers work with WHATWG `Headers`, `NextRequest.headers` and plain stubs.
 */

/** Reads and writes are the only methods the Workbench performs. */
export const ALLOWED_METHODS = Object.freeze(["GET", "POST"]);

/** Only the headers the upstream actually needs. */
export const FORWARDED_REQUEST_HEADERS = Object.freeze([
  "content-type",
  "accept",
  "x-api-key",
  "x-correlation-id",
]);

/**
 * Response headers that stay truthful no matter what body we return.
 *
 * `content-length` is deliberately absent: the error branch replaces the
 * upstream body, so relaying the upstream length made the response
 * self-inconsistent and browsers reported a network error instead of the real
 * status. It is re-attached by `selectResponseHeaders` on the success path only.
 */
export const FORWARDED_RESPONSE_HEADERS = Object.freeze(["content-type"]);

const SEGMENT_PATTERN = /^[A-Za-z0-9._~-]+$/;

function pick(headers, names) {
  const selected = {};
  for (const name of names) {
    const value = headers?.get?.(name);
    if (value) selected[name] = value;
  }
  return selected;
}

/** Request headers to forward upstream. Never the client's whole header set. */
export function selectRequestHeaders(headers) {
  return pick(headers, FORWARDED_REQUEST_HEADERS);
}

/**
 * Response headers to relay for the body we are about to send.
 *
 * `content-length` is included only when `bodyIsUnchanged`, i.e. when the
 * upstream body is streamed through byte-for-byte. On the error path the body is
 * replaced with a short JSON envelope, and forwarding the upstream length made
 * the client see `end of response with N bytes missing` - so a 401, 429 or 422
 * surfaced as "the upstream is unavailable" and the real reason was never shown.
 */
export function selectResponseHeaders(headers, { bodyIsUnchanged }) {
  const selected = pick(headers, FORWARDED_RESPONSE_HEADERS);
  if (bodyIsUnchanged) {
    const length = headers?.get?.("content-length");
    if (length) selected["content-length"] = length;
  }
  return selected;
}

/**
 * A single path segment safe to append to the upstream base.
 *
 * Rejects empty segments, `.`/`..` and anything containing a separator or an
 * encoded separator, before URL normalisation can resolve traversal away.
 */
export function isValidSegment(segment) {
  return (
    typeof segment === "string" &&
    segment !== "" &&
    segment !== "." &&
    segment !== ".." &&
    SEGMENT_PATTERN.test(segment)
  );
}
