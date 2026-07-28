import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: 'standalone',
  async rewrites() {
    const apiBase = process.env.INTERNAL_API_URL ?? 'http://127.0.0.1:5055';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
      {
        source: '/mcp',
        destination: `${apiBase}/mcp/`,
      },
      {
        source: '/mcp/:path*',
        destination: `${apiBase}/mcp/:path*`,
      },
      {
        source: '/oauth/:path*',
        destination: `${apiBase}/oauth/:path*`,
      },
      {
        source: '/.well-known/:path*',
        destination: `${apiBase}/.well-known/:path*`,
      },
    ];
  },
};

export default nextConfig;
