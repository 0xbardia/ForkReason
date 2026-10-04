import { SiteNav } from "@/components/site-nav";
import { Providers } from "@/components/providers";
import { Hero } from "@/components/hero";
import {
  ChallengeSection,
  DnaSection,
  FinalCta,
  HowItThinks,
  OpenSourceSection,
  ProductProof,
  WhyGenLayer,
} from "@/components/landing-sections";
import { SiteFooter } from "@/components/site-footer";

export default function LandingPage() {
  return (
    <Providers>
      <SiteNav />
      <main id="main">
        <Hero />
        <ProductProof />
        <HowItThinks />
        <DnaSection />
        <WhyGenLayer />
        <ChallengeSection />
        <OpenSourceSection />
        <FinalCta />
      </main>
      <SiteFooter />
    </Providers>
  );
}