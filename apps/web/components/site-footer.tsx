import Link from "next/link";

const GITHUB_URL = "https://github.com/0xbardia/ForkReason";

const COLUMNS = [
  {
    title: "Product",
    links: [
      { href: "/trace", label: "New trace" },
      { href: "/explore", label: "Public cases" },
      { href: "/docs", label: "Documentation" },
      { href: "/roadmap", label: "Roadmap" },
    ],
  },
  {
    title: "Learn",
    links: [
      { href: "/docs/how-it-works", label: "How it works" },
      { href: "/docs/verdicts", label: "Verdicts" },
      { href: "/docs/repo-dna", label: "Repo DNA" },
      { href: "/docs/consensus", label: "Consensus" },
      { href: "/docs/limitations", label: "Limitations" },
    ],
  },
  {
    title: "Verify",
    links: [
      { href: "/security", label: "Security" },
      { href: "/docs/threat-model", label: "Threat model" },
      { href: "/docs/contract", label: "Contract" },
      { href: "/docs/testing", label: "Testing" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="layout">
        <div className="site-footer-grid">
          <div className="site-footer-brand">
            <p className="site-footer-tagline">
              Trace where software{" "}
              <span className="living-static">really came from</span>.
            </p>
            <p className="site-footer-note">
              ForkReason reconstructs software lineage and records it through
              GenLayer consensus. It reports relationship, not blame.
            </p>
            <p className="site-footer-version mono">
              v1.0.0 · AGPL-3.0 · bydx.fun
            </p>
          </div>

          {COLUMNS.map((column) => (
            <nav key={column.title} aria-label={column.title}>
              <h2 className="site-footer-heading eyebrow">{column.title}</h2>
              <ul className="site-footer-list">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="site-footer-link">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}

          <div>
            <h2 className="site-footer-heading eyebrow">Network</h2>
            <ul className="site-footer-list">
              <li>
                <span className="site-footer-link mono">studionet</span>
              </li>
              <li>
                <a
                  href={GITHUB_URL}
                  className="site-footer-link"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  GitHub
                </a>
              </li>
              <li>
                <a href="/docs/deployment" className="site-footer-link">
                  Deployment
                </a>
              </li>
            </ul>
          </div>
        </div>

        <hr className="divider" />

        <p className="site-footer-legal">
          ForkReason is a forensic tool for software lineage. It does not make
          legal determinations, and it does not accuse anyone.
        </p>
      </div>
    </footer>
  );
}