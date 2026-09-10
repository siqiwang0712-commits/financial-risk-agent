import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.resolve(__dirname),
  async rewrites() {
    const upstream = process.env.FINRISK_API_UPSTREAM;
    return upstream
      ? [{ source: "/api/v1/:path*", destination: `${upstream}/api/v1/:path*` }]
      : [];
  },
};

export default nextConfig;
