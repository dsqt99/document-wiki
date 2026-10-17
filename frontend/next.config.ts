import type { NextConfig } from "next";

// Backend address the Next server proxies to (never exposed to the browser).
const backend = (process.env.INTERNAL_API_URL || "http://127.0.0.1:5055").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/mcp", destination: `${backend}/mcp/` },
      { source: "/mcp/:path*", destination: `${backend}/mcp/:path*` },
      { source: "/oauth/:path*", destination: `${backend}/oauth/:path*` },
      { source: "/.well-known/:path*", destination: `${backend}/.well-known/:path*` },
    ];
  },
};

export default nextConfig;
