import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { TraceWorkspace } from "@/components/trace-workspace";

export const metadata: Metadata = {
  title: "New trace",
  description:
    "Compare two public GitHub repositories and reconstruct their development lineage with evidence-backed reasoning.",
};

export default function TracePage() {
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <TraceWorkspace />
      </main>
      <SiteFooter />
    </Providers>
  );
}