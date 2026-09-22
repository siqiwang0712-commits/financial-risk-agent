import { NextRequest, NextResponse } from "next/server";
import { hstsHeaderFor } from "./lib/headers.mjs";

/**
 * Per-request security headers.
 *
 * `script-src` carries a per-request nonce instead of `'unsafe-inline'`. Next reads
 * the nonce out of the *request* `Content-Security-Policy` header
 * (`get-script-nonce-from-header`) and stamps it onto the scripts it renders, so the
 * header is set on both the forwarded request and the response. That only works while
 * the route renders per request, which is why `app/layout.tsx` opts out of static
 * prerendering.
 *
 * `Strict-Transport-Security` is emitted here rather than in `next.config.ts` because
 * it is only meaningful for a response that actually travelled over TLS, and the
 * `headers()` config is resolved at build time (standalone output) so it cannot know.
 */
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  // `next dev` compiles modules with `eval` (react-refresh / webpack HMR); without
  // `'unsafe-eval'` the client bundle is blocked outright and the page never
  // hydrates. The shipped bundle does not use `eval`.
  const isDevelopment = process.env.NODE_ENV !== "production";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDevelopment ? " 'unsafe-eval'" : ""}`,
    "script-src-attr 'none'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "font-src 'self' data:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
    "form-action 'self'",
    "worker-src 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);

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
