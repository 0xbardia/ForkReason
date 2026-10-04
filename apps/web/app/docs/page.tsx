import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { DocsShell, DOC_GROUPS } from "@/components/docs-shell";
import { DocContent } from "@/components/docs-content";
import { findDocPage } from "@/lib/docs-data";

export const metadata: Metadata = {
  title: "Documentation",
  description:
    "How ForkReason reconstructs software lineage: Repo DNA, the evidence model, verdicts, shared upstream, GenLayer consensus, security and limitations.",
};

export default function DocsIndexPage() {
  const overview = findDocPage("");
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <div className="layout docs-shell">
          <DocsShell groups={DOC_GROUPS} current="/docs" />
          <article className="docs-content">
            {overview ? <DocContent page={overview} /> : null}
          </article>
        </div>
      </main>
      <SiteFooter />
    </Providers>
  );
}
