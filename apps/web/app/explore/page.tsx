import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { ExploreView } from "@/components/explore-view";

export const metadata: Metadata = {
  title: "Explore cases",
  description:
    "Browse public ForkReason lineage cases, filter by verdict, and open any case to inspect its evidence.",
};

export default function ExplorePage() {
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <ExploreView />
      </main>
      <SiteFooter />
    </Providers>
  );
}