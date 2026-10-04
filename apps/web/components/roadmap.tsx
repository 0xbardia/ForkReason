/**
 * Roadmap.
 *
 * The footer linked `/roadmap` before this route existed, which produced a 404
 * on a page the product advertises. It is also the one place the product can be
 * honest about scope: what shipped, what is next, and what it will never claim
 * to do.
 */

const SHIPPED = [
  {
    title: "Forensic pipeline",
    body: "Eight stages from pinned snapshot to consensus-ready digest, with real progress at every step.",
  },
  {
    title: "Six Repo DNA layers",
    body: "Code, Architecture, History, Bug, Test and Language, weighted by rarity rather than by count.",
  },
  {
    title: "Canonical evidence manifest",
    body: "A deterministic, hashable record that anyone can recompute and check.",
  },
  {
    title: "GenLayer consensus",
    body: "Independent validator re-derivation, fail-closed parsing, append-only revisions.",
  },
  {
    title: "Prompt-injection gate",
    body: "Adversarial fixtures across READMEs, comments, strings, HTML and commit metadata.",
  },
  {
    title: "Public registry",
    body: "Every case permanently addressable, with its counter-evidence and competing explanations.",
  },
];

const NEXT = [
  {
    title: "Stronger upstream discovery",
    body: "Current heuristics miss ancestors when no fork parent is declared.",
  },
  {
    title: "Improved historical bug inference",
    body: "Bug DNA is the strongest available signal; widen the detectable defect signatures.",
  },
  {
    title: "Richer evidence exports",
    body: "Portable, signed evidence bundles that travel with a bug report without losing the manifest hash.",
  },
  {
    title: "Improved shareable reports",
    body: "Print-quality and embeddable case reports, with Open Graph cards for shared URLs.",
  },
];

const LATER = [
  { title: "GitLab and Bitbucket", body: "Intake is already host-agnostic in design." },
  { title: "npm and PyPI lineage", body: "Which published version corresponds to which commit." },
  { title: "Package provenance", body: "Tying registry publishing events to repository history." },
  { title: "CI integration", body: "Lineage checks on every push or release." },
];

const RESEARCH = [
  { title: "Private repositories", body: "Needs user-authorized access and a new intake threat model." },
  { title: "Team workspaces", body: "Multi-tenant collections, sharing and permissions." },
  { title: "Provenance graph", body: "Repositories and relationships as a first-class graph." },
  { title: "Calibrated confidence", body: "Report a probability only where a calibration corpus earns one." },
];

const NEVER = [
  "Legal conclusions: ForkReason reports development relationships, not infringement.",
  "Authorship inference: who wrote what, and with what intent.",
  "Probabilities without a calibration methodology to stand on.",
  "Any custodial action on a user's behalf.",
];

function Group({ title, items }: { title: string; items: { title: string; body: string }[] }) {
  return (
    <section className="roadmap-group">
      <h2 className="roadmap-group-title">{title}</h2>
      <ul className="roadmap-list">
        {items.map((item) => (
          <li key={item.title} className="roadmap-item">
            <h3 className="roadmap-item-title">{item.title}</h3>
            <p className="roadmap-item-body">{item.body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Roadmap() {
  return (
    <div className="layout prose-page roadmap-page">
      <header className="roadmap-head">
        <p className="eyebrow">Roadmap</p>
        <h1 className="heading-1">What ships, and what does not</h1>
        <p className="lead">
          ForkReason will not move required work into a roadmap to make a release
          look finished. Everything below that is not shipped is genuinely
          unbuilt.
        </p>
      </header>

      <Group title="SHIPPED" items={SHIPPED} />
      <Group title="NEXT" items={NEXT} />
      <Group title="LATER" items={LATER} />
      <Group title="RESEARCH" items={RESEARCH} />

      <section className="roadmap-group roadmap-never">
        <h2 className="roadmap-group-title">WHAT WILL NOT BE BUILT</h2>
        <ul className="roadmap-never-list">
          {NEVER.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="roadmap-note">
          A tool that claims to measure provenance has to be clear about where it
          refuses to.
        </p>
      </section>
    </div>
  );
}