import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { CaseReportView } from "@/components/case-report-view";

export const metadata: Metadata = {
  title: "Case report",
  robots: { index: true, follow: true },
};

export default async function CasePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <CaseReportView caseId={id} />
      </main>
      <SiteFooter />
    </Providers>
  );
}