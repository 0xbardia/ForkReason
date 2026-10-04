import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { SecurityView } from "@/components/security-view";

export const metadata: Metadata = {
  title: "Security",
  description:
    "ForkReason's threat model, prompt-injection defences, and responsible disclosure policy.",
};

export default function SecurityPage() {
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <SecurityView />
      </main>
      <SiteFooter />
    </Providers>
  );
}