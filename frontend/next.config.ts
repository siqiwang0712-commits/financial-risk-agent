import type { NextConfig } from "next";
import path from "path";

// Baseline browser hardening. The app shipped none of these headers, so it was
// frameable and sniffable. `Content-Security-Policy` allows only same-origin
// scripts/styles/images plus the inline styles the Workbench uses for the
// server-rendered shell.
//
// `next dev` compiles modules with `eval` (react-refresh / webpack HMR), so a
// `script-src` without `'unsafe-eval'` blocks the client bundle outright: the
// page renders the server shell, never hydrates, and every control stays inert
// (`Load bundled sample` did nothing and the pilot panel sat on "Loading pilot
// data…"). The relaxation is scoped to development; the shipped bundle does not
// use `eval`, so production keeps the strict policy.
const isDevelopment = process.env.NODE_ENV !== "production";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // `Strict-Transport-Security` is deliberately *not* here: it is only meaningful for
  // a response that actually travelled over TLS, and this config is resolved at build
  // time (standalone output), so it cannot know. `middleware.ts` sets it per request
  // by inspecting the effective scheme. →
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}`,
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
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.resolve(__dirname),
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
