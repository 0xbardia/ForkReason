import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `output: "standalone"` produces a self-contained server bundle for PM2,
  // which avoids copying node_modules into production.
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,
  productionBrowserSourceMaps: false,
  experimental: {
    // Tree-shake the barrel files that RainbowKit and wagmi ship.
    optimizePackageImports: [
      "@rainbow-me/rainbowkit",
      "wagmi",
      "viem",
      "genlayer-js",
    ],
  },
  images: {
    formats: ["image/avif", "image/webp"],
    // Remote patterns are deliberately empty: ForkReason serves no remote
    // images, so an open image proxy is pure attack surface.
    remotePatterns: [],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          {
            // `unsafe-eval` is required by RainbowKit's WalletConnect SDK and is
            // the one documented exception. No third-party script origins are
            // permitted, and 'unsafe-inline' is limited to styles.
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              "connect-src 'self' https://studio.genlayer.com https://rpc-bradbury.genlayer.com wss://",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
              "object-src 'none'",
              "upgrade-insecure-requests",
            ].join("; "),
          },
        ],
      },
      {
        // The API proxies through nginx in production, but Next must not cache
        // anything user-specific.
        source: "/api/:path*",
        headers: [{ key: "Cache-Control", value: "no-store" }],
      },
    ];
  },
};

export default nextConfig;