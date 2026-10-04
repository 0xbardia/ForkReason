import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { AnalysisProgress } from "@/components/analysis-progress";

export const metadata: Metadata = {
  title: "Analysis in progress",
  robots: { index: false, follow: false },
};

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <AnalysisProgress jobId={id} />
      </main>
      <SiteFooter />
    </Providers>
  );
}