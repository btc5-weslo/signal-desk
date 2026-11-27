import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow importing from ../shared (generated contracts) via the @shared/* tsconfig path.
  // Current imports are type-only (erased at build), but this keeps runtime imports working too.
  experimental: { externalDir: true },
  // Hide the Next.js dev-mode indicator badge.
  devIndicators: false,
};

export default nextConfig;
