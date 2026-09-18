import assert from "node:assert/strict";
import test from "node:test";

import {
  ALLOWED_METHODS,
  CORRELATION_ID_PATTERN,
  DEFAULT_UPLOAD_BYTES,
  MULTIPART_OVERHEAD_BYTES,
  normalizeCorrelationId,
  rebuildTarget,
  resolveUpstream,
  uploadEnvelopeLimit,
  uploadLimit,
  upstreamTimeoutMs,
} from "../lib/proxy.mjs";

const env = (overrides = {}) => ({ FINRISK_API_UPSTREAM: "http://api:8000", ...overrides });

test("only the two methods the Workbench performs are proxied", () => {
  assert.deepEqual([...ALLOWED_METHODS].sort(), ["GET", "POST"]);
});

test("upstream is rejected when unset, unparseable or not http(s)", () => {
  assert.equal(resolveUpstream({}), null);
  assert.equal(resolveUpstream({ FINRISK_API_UPSTREAM: "not a url" }), null);
  assert.equal(resolveUpstream({ FINRISK_API_UPSTREAM: "file:///etc/passwd" }), null);
  assert.equal(resolveUpstream({ FINRISK_API_UPSTREAM: "gopher://api:8000" }), null);
  assert.equal(resolveUpstream(env())?.origin, "http://api:8000");
});

test("link-local and cloud-metadata upstreams are refused", () => {
  for (const host of ["http://169.254.169.254", "http://metadata.google.internal", "http://[fd00:ec2::254]"]) {
    assert.equal(resolveUpstream({ FINRISK_API_UPSTREAM: host }), null, host);
  }
});

test("an explicit host allowlist is enforced", () => {
  const allowed = env({ FINRISK_API_ALLOWED_HOSTS: "api.example.com, api" });
  assert.equal(resolveUpstream(allowed)?.host, "api:8000");
  assert.equal(
    resolveUpstream({ FINRISK_API_UPSTREAM: "http://evil.example", FINRISK_API_ALLOWED_HOSTS: "api" }),
    null,
  );
});

test("path traversal and encoded separators never reach a rebuilt target", () => {
  const base = new URL("http://api:8000");
  for (const segments of [
    [".."],
    ["..", "admin"],
    ["a", "..", "b"],
    ["."],
    [""],
    ["%2e%2e"],
    ["a/b"],
    ["a\\b"],
    [],
  ]) {
    assert.equal(rebuildTarget(base, segments, ""), null, JSON.stringify(segments));
  }
  const ok = rebuildTarget(base, ["public-pilot"], "");
  assert.equal(ok?.href, "http://api:8000/api/v1/public-pilot");
  assert.equal(rebuildTarget(base, ["documents", "analyze"], "?x=1")?.search, "?x=1");
});

test("a rebuilt target can never leave the /api/v1 prefix or the origin", () => {
  const base = new URL("http://api:8000");
  const target = rebuildTarget(base, ["enterprise", "overview"], "");
  assert.equal(target?.origin, base.origin);
  assert.ok(target?.pathname.startsWith("/api/v1/"));
});

test("upload limit falls back to 50 MiB on a missing or nonsense value", () => {
  assert.equal(uploadLimit({}), DEFAULT_UPLOAD_BYTES);
  assert.equal(uploadLimit({ FINRISK_MAX_UPLOAD_BYTES: "0" }), DEFAULT_UPLOAD_BYTES);
  assert.equal(uploadLimit({ FINRISK_MAX_UPLOAD_BYTES: "-5" }), DEFAULT_UPLOAD_BYTES);
  assert.equal(uploadLimit({ FINRISK_MAX_UPLOAD_BYTES: "abc" }), DEFAULT_UPLOAD_BYTES);
  assert.equal(uploadLimit({ FINRISK_MAX_UPLOAD_BYTES: "1024" }), 1024);
});

test("the request-body ceiling leaves room for multipart framing", () => {
  const limit = 4 * 1024;
  const configuration = { FINRISK_MAX_UPLOAD_BYTES: String(limit) };
  assert.equal(uploadLimit(configuration), limit);
  assert.ok(uploadEnvelopeLimit(configuration) > limit);

  // Reproduce the envelope the Workbench actually posts for a file of exactly
  // `limit` bytes: the boundary lines, the three text fields, the part headers and
  // the file itself. Comparing the *encoded* body against the raw file limit is what
  // made a legitimate boundary-size upload answer 413 from the proxy before the
  // backend ever saw it.
  const boundary = "----finriskenvelope";
  const parts = [
    `--${boundary}\r\nContent-Disposition: form-data; name="company"\r\n\r\nContract issuer\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="fiscal_year"\r\n\r\n2025\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="entity_id"\r\n\r\nent_0123456789abcdef\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="filing.pdf"\r\n`
      + "Content-Type: application/pdf\r\n\r\n",
  ];
  const envelope = Buffer.byteLength(parts.join("")) + limit
    + Buffer.byteLength(`\r\n--${boundary}--\r\n`);
  assert.ok(envelope > limit, "the encoded envelope is larger than the file — that is the bug");
  assert.ok(
    envelope <= uploadEnvelopeLimit(configuration),
    `a boundary-size upload must fit the ceiling (envelope ${envelope})`,
  );
});

test("the envelope ceiling still bounds the request body", () => {
  assert.equal(uploadEnvelopeLimit({}), DEFAULT_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES);
  assert.equal(uploadEnvelopeLimit({ FINRISK_MAX_UPLOAD_BYTES: "1" }), 1 + MULTIPART_OVERHEAD_BYTES);
  // Bounded, not unbounded: the headroom is a fixed allowance.
  assert.ok(uploadEnvelopeLimit({ FINRISK_MAX_UPLOAD_BYTES: "1024" }) < 100 * 1024);
});

test("the proxy deadline always trails the backend deadline", () => {
  assert.equal(upstreamTimeoutMs({}), 62_000);
  assert.equal(upstreamTimeoutMs({ FINRISK_ANALYSIS_TIMEOUT_SECONDS: "0.001" }), 2_001);
  assert.equal(upstreamTimeoutMs({ FINRISK_ANALYSIS_TIMEOUT_SECONDS: "bogus" }), 62_000);
});

test("a well-formed correlation id is preserved and anything else is replaced", () => {
  assert.equal(normalizeCorrelationId("abc-123_A.B"), "abc-123_A.B");
  assert.equal(normalizeCorrelationId("  spaced  "), "spaced");
  assert.match(normalizeCorrelationId(null), CORRELATION_ID_PATTERN);
  // Oversized and non-id values used to be echoed back verbatim.
  const fallback = () => "generated";
  assert.equal(normalizeCorrelationId("A".repeat(5000), fallback), "generated");
  assert.equal(normalizeCorrelationId("has space", fallback), "generated");
  assert.equal(normalizeCorrelationId("", fallback), "generated");
  assert.equal(normalizeCorrelationId(null, fallback), "generated");
  assert.equal(normalizeCorrelationId("<script>", fallback), "generated");
});
