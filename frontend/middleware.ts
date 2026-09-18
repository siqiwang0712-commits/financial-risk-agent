import { NextRequest, NextResponse } from "next/server";
import { hstsHeaderFor } from "./lib/headers.mjs";

/**
 * Emit `Strict-Transport-Security` only when the request actually arrived over TLS.
 *
 * `output: "standalone"` bakes the resolved `headers()` config into the build, so a
 * build-time flag could not reflect how the artefact is deployed. The transport is a
 * per-request fact, so the decision is made per request: `x-forwarded-proto` when a
 * TLS terminator is in front, otherwise the URL's own scheme.
 */
export function middleware(request: NextRequest) {
  const response = NextResponse.next();
  const proto = request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol;
  const hsts = hstsHeaderFor(proto);
  if (hsts) {
    response.headers.set("Strict-Transport-Security", hsts);
  }
  return response;
}

export const config = {
  // Document/asset responses only. HSTS pins an *origin*, and the browser learns it
  // from the navigation response, so the API routes do not need it — and keeping the
  // middleware off `/api/` keeps it out of the streaming upload path entirely.
  matcher: ["/((?!api/|_next/static|_next/image).*)"],
};
