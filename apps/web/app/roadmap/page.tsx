import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { Roadmap } from "@/components/roadmap";

export const metadata: Metadata = {
  title: "Roadmap",
  description:
    "What ForkReason ships today, what comes next, and what is deliberately out of scope.",
};

export default function RoadmapPage() {
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <Roadmap />
      </main>
      <SiteFooter />
    </Providers>
  );
}
