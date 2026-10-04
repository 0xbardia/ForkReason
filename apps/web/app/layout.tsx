import type { Metadata, Viewport } from "next";

import "./styles/globals.css";

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