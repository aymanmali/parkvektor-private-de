import type { NextConfig } from "next";

const isVercelWithoutBackend =
  Boolean(process.env.VERCEL) && !process.env.NEXT_PUBLIC_API_BASE_URL;

const nextConfig: NextConfig = {
  output: process.env.VERCEL ? undefined : "standalone",
  env: {
    NEXT_PUBLIC_DEMO_MODE:
      process.env.NEXT_PUBLIC_DEMO_MODE ?? (isVercelWithoutBackend ? "true" : "false"),
  },
};

export default nextConfig;
