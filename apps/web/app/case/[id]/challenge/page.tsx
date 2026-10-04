import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { ChallengeView } from "@/components/challenge-view";

export const metadata: Metadata = {
  title: "Challenge a finding",
  robots: { index: true, follow: true },
};

export default async function ChallengePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <ChallengeView caseId={id} />
      </main>
      <SiteFooter />
    </Providers>
  );
}
