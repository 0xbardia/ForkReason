import { NextResponse, type NextRequest } from "next/server";

/**
 * Per-request CSP nonce.
 *
 * The nonce is set on the request headers where Next reads it for its own
 * bootstrap script, and echoed in the response header. Everything else is
 * blocked by default.
 */
/**
 * Middleware runs on the Edge runtime, so Node's `crypto` module is
 * unavailable (`UnhandledSchemeError`). `crypto.getRandomValues` is the
 * WebCrypto equivalent and is present in every runtime that ships here.
 */
function createNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

export function middleware(request: NextRequest) {
  const nonce = createNonce();
  const isDev = process.env.NODE_ENV !== "production";
  // NEXT_PUBLIC_* values are inlined at build time. If unset, fall back to the
  // public API path rather than emitting an empty CSP source, which is itself a
  // parse error.
  const apiOrigin =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "";

  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'unsafe-eval'${isDev ? " 'unsafe-eval'" : ""}`,
    // Styles need inline: Next emits critical CSS as a style tag, and the
    // design system drives layout from CSS custom properties at runtime.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    // The API origin must be explicitly allowed. In production nginx proxies
    // /api so it is same-origin; in development the browser calls port 8421
    // directly, and omitting it produced a CSP refusal that looked like a
    // backend outage. A trailing double space is avoided so the directive
    // parses cleanly either way.
    `connect-src 'self' ${apiOrigin} https://studio.genlayer.com https://rpc-bradbury.genlayer.com https://rpc-asimov.genlayer.com wss://relay.walletconnect.com wss://*.walletconnect.com`.replace(/\s+/g, " ").trim(),
    "frame-src 'self' https://verify.walletconnect.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    ...(isDev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  // Next's bootstrap consults this to stamp the nonce onto its inline script.
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });

  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), interest-cohort=()",
  );
  if (!isDev) {
    response.headers.set(
      "Strict-Transport-Security",
      "max-age=63072000; includeSubDomains; preload",
    );
  }

  return response;
}

export const config = {
  // Static assets do not need a nonce, and skipping them keeps the header work
  // off the hot path.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};