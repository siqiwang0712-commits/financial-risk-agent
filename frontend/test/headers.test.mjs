import assert from "node:assert/strict";
import test from "node:test";

import { HSTS_VALUE, hstsHeaderFor, isSecureRequest } from "../lib/headers.mjs";

// `Strict-Transport-Security` was emitted unconditionally, including over plain HTTP
// on the local stack. A browser ignores it there, and asserting a year of HTTPS-only
// for a deployment that is not serving HTTPS is a promise the app cannot keep. The
// decision now depends on the request's effective scheme.

test("HSTS is only sent for a request that actually arrived over TLS", () => {
  assert.equal(hstsHeaderFor("https"), HSTS_VALUE);
  assert.equal(hstsHeaderFor("HTTPS"), HSTS_VALUE);
  assert.equal(hstsHeaderFor("https:"), HSTS_VALUE);
  assert.equal(hstsHeaderFor(" http "), null);
});

test("plain HTTP never gets an HSTS claim", () => {
  for (const proto of ["http", "http:", "", null, undefined, "ftp", "ws"]) {
    assert.equal(hstsHeaderFor(proto), null, String(proto));
  }
});

test("the decision is a pure predicate over the scheme", () => {
  assert.equal(isSecureRequest("https"), true);
  assert.equal(isSecureRequest("wss"), true);
  assert.equal(isSecureRequest("http"), false);
  assert.equal(isSecureRequest(null), false);
});
