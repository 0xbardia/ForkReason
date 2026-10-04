import type { Metadata, Viewport } from "next";

// Self-hosted variable fonts. No external font request, which keeps the page
// inside its own CSP origin and removes a third-party dependency.
import "@fontsource-variable/instrument-sans";
import "@fontsource-variable/jetbrains-mono";

import "@/styles/globals.css";
import "@/styles/components.css";
import "@/styles/pages.css";
import "@/styles/case.css";
import "@/styles/docs.css";

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3111",
  ),
  title: {
    default: "ForkReason — Trace where software really came from",
    template: "%s · ForkReason",
  },
  description:
    "ForkReason compares software repositories, reconstructs meaningful development lineage, evaluates alternative explanations for similarity, and records an evidence-backed decision through GenLayer consensus.",
  applicationName: "ForkReason",
  keywords: [
    "software provenance",
    "repository lineage",
    "software lineage",
    "GenLayer",
    "code provenance",
    "developer tools",
  ],
  authors: [{ name: "ForkReason" }],
  openGraph: {
    type: "website",
    title: "ForkReason — Trace where software really came from",
    description:
      "Evidence-backed software lineage, recorded through GenLayer consensus.",
    url: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3111",
    siteName: "ForkReason",
  },
  twitter: {
    card: "summary_large_image",
    title: "ForkReason — Trace where software really came from",
    description:
      "Evidence-backed software lineage, recorded through GenLayer consensus.",
  },
  robots: { index: true, follow: true },
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
};

/**
 * Font faces are registered as variables so tokens.css can reference them by
 * name, keeping font choice out of every component.
 */
/**
 * The nonce-based CSP requires a per-request render: Next reads the nonce out
 * of the incoming `Content-Security-Policy` header and stamps it onto its
 * inline bootstrap scripts. A statically prerendered page has no request, so
 * Next emits those scripts without a nonce and the browser blocks them — the
 * page renders nothing. This forces per-request rendering for the app shell.
 */
export const dynamic = "force-dynamic";

export const viewport: Viewport = {
  themeColor: "#07110F",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}