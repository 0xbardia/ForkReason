import Link from "next/link";
import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { DocsShell, DOC_SECTIONS } from "@/components/docs-shell";

export const metadata: Metadata = {
  title: "Documentation",
  description:
    "How ForkReason reconstructs software lineage: Repo DNA, the evidence model, verdicts, shared upstream, GenLayer consensus, security and limitations.",
};

export default function DocsIndexPage() {
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <div className="layout docs-shell">
          <DocsShell sections={DOC_SECTIONS} current="" />
        </div>
      </main>
      <SiteFooter />
    </Providers>
  );
}

export function generateStaticParams() {
  return DOC_SECTIONS.filter((section) => section.href).map((section) => ({
    slug: section.href!.slice(1),
  }));
}