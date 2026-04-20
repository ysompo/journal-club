import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  transpilePackages: ["@jc/shared"],
  images: { unoptimized: true },
};

export default nextConfig;
