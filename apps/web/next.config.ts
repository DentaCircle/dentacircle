import type { NextConfig } from "next";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

/** Base URL the `/api` rewrite proxies to. Trailing slashes are removed. */
export function apiProxyBaseUrl(): string {
  const configured = process.env.API_BASE_URL;
  if (configured === undefined || configured.trim() === "") return DEFAULT_API_BASE_URL;
  return configured.replace(/\/$/, "");
}

const nextConfig: NextConfig = {
  // Next writes its own agent docs into this app. The repo rules live at the root.
  agentRules: false,
  // The browser calls `/api/*` on this origin. Next proxies the request, including
  // the body, and forwards Set-Cookie so `dc_session` is stored for the web app.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyBaseUrl()}/:path*`,
      },
    ];
  },
};

export default nextConfig;
