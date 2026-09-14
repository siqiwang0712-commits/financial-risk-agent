import type { NextConfig } from "next";
import path from "path";

// Baseline browser hardening. The app shipped none of these headers, so it was
// frameable and sniffable. `Content-Security-Policy` allows only same-origin
// scripts/styles/images plus the inline styles the Workbench uses for the
// server-rendered shell.
//
// `'unsafe-eval'` is granted in development only: React's dev-mode HMR and error
// overlay need `eval`, and without the exception the page fails to boot under
// `next dev` while looking fine in production. Production never gets it.
const isDevelopment = process.env.NODE_ENV === "development";
const scriptSrc = isDevelopment ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self' 'unsafe-inline'";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      scriptSrc,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "connect-src 'self'",
      "font-src 'self' data:",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "object-src 'none'",
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
