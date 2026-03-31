import type { NextConfig } from "next";

/**
 * API_BASE is a **server-side** runtime environment variable read by Next.js
 * during SSR and API Route calls.  It is NOT a NEXT_PUBLIC_ variable and is
 * therefore NOT baked into the client bundle at build time.
 *
 * In docker-compose the frontend service receives:
 *   environment:
 *     - API_BASE=http://backend:8000
 *
 * All browser fetch() calls use relative paths (e.g. `/api-proxy/alerts`)
 * and are rewritten server-side to the real backend URL, so the built image
 * is deployment-agnostic — no rebuilding needed for staging vs production.
 */
const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",

  /**
   * Rewrites proxy all /api-proxy/* calls through the Next.js server to the
   * backend, and /ws-proxy/* for WebSocket connections.
   *
   * Benefits:
   *  - The browser never needs to know the backend URL.
   *  - CORS is eliminated — same origin for browser → Next.js server.
   *  - API_BASE can be changed at container start without rebuilding.
   */
  async rewrites() {
    return [
      {
        source: "/api-proxy/:path*",
        destination: `${API_BASE}/:path*`,
      },
    ];
  },
};

export default nextConfig;
