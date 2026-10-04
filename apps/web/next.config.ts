import path from "node:path";

import type { NextConfig } from "next";

/**
 * Content Security Policy with a per-request nonce.
 *
 * The first version of this policy omitted `'unsafe-inline'` for scripts and
 * the page rendered *nothing*: Next's hydration payload is an inline script,
 * so React could not boot at all. That is a self-inflicted total failure, and
 * the obvious "fix" — adding `'unsafe-inline'` — would disable the protection
 * entirely.
 *
 * So: a nonce is generated per request, threaded through the proxy middleware
 * into both the response header and Next's own bootstrap. Only scripts this
 * server emitted for this request can execute.
 *
 * `'unsafe-eval'` is still required, because WalletConnect's SDK evaluates a
 * dynamically built bundle. It is confined to `script-src` and recorded as an
 * accepted risk in docs/SECURITY-FINDINGS.md.
 */

export function buildCsp(nonce: string): string {
  const connect = [
    "'self'",
    "https://studio.genlayer.com",
    "https://rpc-bradbury.genlayer.com",
    "https://rpc-asimov.genlayer.com",
    // WalletConnect relay, only reachable when a project id is configured.
    "wss://relay.walletconnect.com",
    "wss://*.walletconnect.com",
  ].join(" ");

  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'unsafe-eval'`,
    // Styles legitimately need inline: Next emits critical CSS as a style tag.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src ${connect}`,
    "frame-src 'self' https://verify.walletconnect.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
  ].join("; ");
}

const nextConfig: NextConfig = {
  // `output: "standalone"` produces a self-contained server bundle for PM2,
  // which avoids copying node_modules into production.
  output: "standalone",
  // Pin the trace root: Next otherwise infers /root because a stray lockfile
  // exists there, which bloats the standalone bundle.
  outputFileTracingRoot: path.join(import.meta.dirname, "..", ".."),
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
    // ForkReason serves no remote images, so an open image proxy is pure
    // attack surface.
    remotePatterns: [],
  },
};

export default nextConfig;