import type { NextConfig } from "next";

// Run with `next dev --webpack` (see package.json): this machine's Application
// Control policy blocks native binaries, so Turbopack (native only) is not used.
const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  // the dev server only serves its assets to "localhost" unless told otherwise
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
