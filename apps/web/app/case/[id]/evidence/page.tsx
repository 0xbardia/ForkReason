import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { EvidenceExplorer } from "@/components/evidence-explorer";

export const metadata: Metadata = {
  title: "Evidence explorer",
  robots: { index: true, follow: true },
};

export default async function EvidencePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <EvidenceExplorer caseId={id} />
      </main>
      <SiteFooter />
    </Providers>
  );
}
