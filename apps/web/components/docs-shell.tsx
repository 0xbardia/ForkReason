"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";

export interface DocSection {
  title: string;
  href?: string;
  blurb?: string;
}

export interface DocGroup {
  label: string;
  sections: DocSection[];
}

/** Documentation content is defined once, in one place, so the sidebar and the
 *  routes cannot drift apart. */
export const DOC_GROUPS: DocGroup[] = [
  {
    label: "Start",
    sections: [
      { title: "Overview", href: "/docs", blurb: "What ForkReason is and is not." },
      { title: "Quick start", href: "/docs/quickstart", blurb: "Trace your first relationship." },
      { title: "How ForkReason works", href: "/docs/how-it-works", blurb: "The pipeline, end to end." },
    ],
  },
  {
    label: "Evidence",
    sections: [
      { title: "Repo DNA", href: "/docs/repo-dna", blurb: "Six layers and what each can prove." },
      { title: "Evidence model", href: "/docs/evidence-model", blurb: "How evidence is weighted and bounded." },
      { title: "Verdicts", href: "/docs/verdicts", blurb: "The six outcomes and their meaning." },
      { title: "Lineage timeline", href: "/docs/lineage-timeline", blurb: "Why chronology decides direction." },
      { title: "Shared upstream", href: "/docs/shared-upstream", blurb: "Finding the common ancestor." },
    ],
  },
  {
    label: "Consensus",
    sections: [
      { title: "GenLayer consensus", href: "/docs/consensus", blurb: "How a decision is reached." },
      { title: "Challenges & revisions", href: "/docs/challenges", blurb: "Contesting a finding." },
      { title: "Contract", href: "/docs/contract", blurb: "ForkReasonRegistry methods." },
      { title: "Wallet transactions", href: "/docs/wallet", blurb: "What your wallet signs." },
    ],
  },
  {
    label: "Build",
    sections: [
      { title: "Architecture", href: "/docs/architecture", blurb: "Processes, data model, boundaries." },
      { title: "API", href: "/docs/api", blurb: "Versioned endpoints." },
      { title: "Testing", href: "/docs/testing", blurb: "Fixtures and release gates." },
      { title: "Deployment", href: "/docs/deployment", blurb: "Running ForkReason yourself." },
      { title: "Open source", href: "/docs/open-source", blurb: "Repository and license." },
    ],
  },
  {
    label: "Trust",
    sections: [
      { title: "Security model", href: "/security", blurb: "Threats and controls." },
      { title: "Prompt injection", href: "/docs/prompt-injection", blurb: "Repository text as data." },
      { title: "Threat model", href: "/docs/threat-model", blurb: "Adversaries and assumptions." },
      { title: "Limitations", href: "/docs/limitations", blurb: "What ForkReason cannot do." },
      { title: "Roadmap", href: "/roadmap", blurb: "What comes after V1." },
      { title: "FAQ", href: "/docs/faq", blurb: "Common questions." },
    ],
  },
];

export const DOC_SECTIONS = DOC_GROUPS.flatMap((group) => group.sections);

export function DocsShell({
  sections,
  current,
}: {
  sections: DocSection[];
  current?: string;
}) {
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [navOpen, setNavOpen] = useState(false);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return DOC_GROUPS;
    return DOC_GROUPS.map((group) => ({
      ...group,
      sections: group.sections.filter(
        (section) =>
          section.title.toLowerCase().includes(needle) ||
          (section.blurb ?? "").toLowerCase().includes(needle),
      ),
    })).filter((group) => group.sections.length > 0);
  }, [query]);

  const matched = sections.length > 0 ? sections : undefined;

  return (
    <div className="docs-layout">
      <aside className="docs-sidebar" data-open={navOpen}>
        <button
          type="button"
          className="docs-sidebar-toggle"
          aria-expanded={navOpen}
          aria-controls="docs-nav"
          onClick={() => setNavOpen((open) => !open)}
        >
          Documentation menu
          <span aria-hidden="true" className="docs-sidebar-chevron" data-open={navOpen} />
        </button>

        <div className="docs-search">
          <label htmlFor="docs-search" className="sr-only">
            Search documentation
          </label>
          <input
            id="docs-search"
            type="search"
            className="explore-input"
            placeholder="Search docs…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <nav id="docs-nav" className="docs-nav" aria-label="Documentation">
          {groups.length === 0 ? (
            <p className="docs-nav-empty">No documentation matches “{query}”.</p>
          ) : null}

          {groups.map((group) => (
            <div key={group.label} className="docs-nav-group">
              <h2 className="docs-nav-heading eyebrow">{group.label}</h2>
              <ul>
                {group.sections.map((section) => {
                  const href = section.href ?? "/docs";
                  const isCurrent = href === current || pathname === href;
                  return (
                    <li key={href}>
                      <Link
                        href={href}
                        className="docs-nav-link"
                        aria-current={isCurrent ? "page" : undefined}
                        data-active={isCurrent}
                      >
                        {section.title}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      <article className="docs-content">
        {matched ? null : (
          <p className="docs-content-placeholder eyebrow">ForkReason documentation</p>
        )}
      </article>
    </div>
  );
}