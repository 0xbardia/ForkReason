import Link from "next/link";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";

export const metadata = {
  title: "Page not found",
};

/**
 * Custom 404.
 *
 * Offers the routes a lost visitor most likely wanted rather than a dead end.
 */
export default function NotFound() {
  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main notfound">
        <div className="layout notfound-inner">
          <p className="eyebrow">404 · no such case</p>
          <h1 className="heading-1">This page does not exist</h1>
          <p className="lead">
            If you followed a case link, the case may have been recorded under a
            different id — case identifiers are content-addressed, so they change
            when the evidence changes.
          </p>

          <div className="notfound-actions">
            <Link href="/trace" className="btn btn-primary">
              Start a new trace
            </Link>
            <Link href="/explore" className="btn btn-secondary">
              Browse public cases
            </Link>
            <Link href="/docs" className="btn btn-ghost">
              Read the docs
            </Link>
          </div>
        </div>
      </main>
      <SiteFooter />
    </Providers>
  );
}