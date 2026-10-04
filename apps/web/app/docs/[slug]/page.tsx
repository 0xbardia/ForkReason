import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { DocsShell, DOC_GROUPS } from "@/components/docs-shell";
import { DocContent } from "@/components/docs-content";
import { DOC_PAGES, findDocPage } from "@/lib/docs-data";

export function generateStaticParams() {
  return DOC_PAGES.filter((page) => page.slug).map((page) => ({ slug: page.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const page = findDocPage(slug);
  if (!page) return { title: "Not found" };
  return { title: page.title, description: page.summary };
}

export default async function DocPageRoute({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page = findDocPage(slug);
  if (!page) notFound();

  return (
    <Providers>
      <SiteNav />
      <main id="main" className="page-main">
        <div className="layout docs-shell">
          <DocsShell groups={DOC_GROUPS} current={`/docs/${slug}`} />
          <article className="docs-content">
            <DocContent page={page} />
          </article>
        </div>
      </main>
      <SiteFooter />
    </Providers>
  );
}
