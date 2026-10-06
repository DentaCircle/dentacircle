import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next writes its own agent docs into this app. The repo rules live at the root.
  agentRules: false,
};

export default nextConfig;
