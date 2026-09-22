import type { NextConfig } from "next";
import path from "path";

// Baseline browser hardening. The app shipped none of these headers, so it was
// frameable and sniffable.
//
// `Content-Security-Policy` is deliberately *not* here. It needs a per-request nonce
// for `script-src` (see `middleware.ts`), and this config is resolved once at build
// time for the standalone output, so a policy declared here could not carry one and
// would have to keep `'unsafe-inline'`. Two policies would also both be enforced,
// which is confusing to reason about.
//
// `Strict-Transport-Security` is likewise absent: it is only meaningful for a
// response that actually travelled over TLS, which `middleware.ts` determines per
// request by inspecting the effective scheme.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.resolve(__dirname),
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
