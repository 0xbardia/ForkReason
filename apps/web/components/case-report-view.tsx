"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { EvidenceGraph, buildGraph } from "@/components/evidence-graph";
import { RepoDna } from "@/components/repo-dna";
import { api, ApiClientError, type CaseReport, type Confidence, type Verdict } from "@/lib/api";
import {
  CONFIDENCE_META,
  DIRECTION_LABEL,
  EXPLANATION_LABEL,
  formatDate,
  LAYER_LABEL,
  shortSha,
  VERDICT_META,
} from "@/lib/presentation";

const LAYER_ORDER = ["CODE", "ARCHITECTURE", "HISTORY", "BUG", "TEST", "LANGUAGE"];

/**
 * The case report.
 *
 * Answers, above the fold: what relationship was found, how confident, in
 * which direction, and why. Everything else is progressively disclosed, so a
 * normal reader gets the answer immediately and an engineer can drill into
 * exact files, commits and the manifest hash.
 */
/**
 * The colour a verdict paints its own section with. This is semantic, not
 * decorative: coral for a derivation conflict, amber for uncertainty, mint for
 * a clean independent result, so the page's mood is legible before a word is
 * read.
 */
const VERDICT_HUE: Record<Verdict, string> = {
  LIKELY_DERIVED: "var(--coral)",
  HEAVILY_DERIVED: "var(--amber)",
  INDEPENDENT: "var(--mint)",
  SHARED_UPSTREAM: "var(--aqua)",
  DECLARED_FORK: "var(--volt)",
  INSUFFICIENT_EVIDENCE: "var(--text-faint)",
};

export function CaseReportView({ caseId }: { caseId: string }) {
  const [report, setReport] = useState<CaseReport | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api
      .getCase(caseId, controller.signal)
      .then(setReport)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError({
          code: err instanceof ApiClientError ? err.code : "load_failed",
          message:
            err instanceof ApiClientError
              ? err.message
              : "This case report could not be loaded.",
        });
      });
    return () => controller.abort();
  }, [caseId]);

  const graph = useMemo(() => {
    if (!report) return null;
    return buildGraph(
      report.case.origin_repo,
      report.case.target_repo,
      report.evidence,
      report.graph,
      report.verdict.shared_upstream,
    );
  }, [report]);

  if (error) {
    return (
      <div className="layout prose-page">
        <header className="prose-page-head">
          <p className="eyebrow">Case report</p>
          <h1 className="heading-1">
            {error.code === "case_not_found" ? "No such case" : "Report unavailable"}
          </h1>
          <p className="lead">{error.message}</p>
        </header>
        <div className="notfound-actions">
          <Link href="/explore" className="btn btn-primary">
            Browse public cases
          </Link>
          <Link href="/trace" className="btn btn-secondary">
            Start a trace
          </Link>
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="layout prose-page" aria-busy="true">
        <div className="skeleton-line skeleton-line-lg" style={{ width: "18rem", height: "2rem" }} />
        <div className="skeleton-line" style={{ width: "30rem", marginTop: "1rem" }} />
        <div className="skeleton-line" style={{ width: "24rem" }} />
      </div>
    );
  }

  const { case: meta, verdict } = report;
  const verdictMeta = VERDICT_META[verdict.verdict as Verdict];
  const confidenceMeta = CONFIDENCE_META[verdict.confidence as Confidence];
  const counts = report.evidence.reduce<Record<string, number>>((acc, item) => {
    acc[item.dna_layer] = (acc[item.dna_layer] ?? 0) + 1;
    return acc;
  }, {});
  const strongCount = report.evidence.filter((e) => e.strength === "HIGH").length;

  const shareUrl = typeof window !== "undefined" ? window.location.href : "";

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div
      className="layout case-page"
      style={{ "--verdict-hue": VERDICT_HUE[verdict.verdict] ?? "var(--aqua)" } as CSSProperties}
    >
      {/* --- 1. The answer ------------------------------------------- */}
      <section className="case-headline" aria-labelledby="verdict-heading">
        <p className="eyebrow">Case report · revision {meta.current_revision}</p>

        <h1 id="verdict-heading" className="case-verdict">
          <span className={`case-verdict-badge badge-${verdictMeta.tone}`}>
            {verdictMeta.label}
          </span>
        </h1>

        <p className="case-confidence">
          <span className={`badge badge-${confidenceMeta.tone}`}>
            {confidenceMeta.tone === "muted" ? "" : ""}
            {verdict.confidence} confidence
          </span>
          {verdict.direction ? (
            <span className="badge badge-muted">
              {DIRECTION_LABEL[verdict.direction]}
            </span>
          ) : null}
          {verdict.shared_upstream ? (
            <span className="badge badge-aqua">upstream: {verdict.shared_upstream}</span>
          ) : null}
        </p>

        <p className="case-flow" aria-hidden="true">
          <span className="mono case-flow-repo">{meta.origin_repo}</span>
          <span className="case-flow-arrow" />
          <span className="mono case-flow-repo">{meta.target_repo}</span>
        </p>

        <p className="case-summary">{verdict.rationale}</p>

        <ul className="case-counts">
          <li>
            <span className="case-count-value">{strongCount}</span>
            <span className="case-count-label">strong signals</span>
          </li>
          <li>
            <span className="case-count-value">{report.evidence.length}</span>
            <span className="case-count-label">supporting</span>
          </li>
          <li>
            <span className="case-count-value case-count-coral">
              {report.conflicting_evidence.length}
            </span>
            <span className="case-count-label">conflicting</span>
          </li>
          <li>
            <span className="case-count-value case-count-aqua">
              {report.alternative_explanations.length}
            </span>
            <span className="case-count-label">explanations weighed</span>
          </li>
        </ul>

        <div className="case-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copyLink()}>
            {copied ? "Link copied" : "Share case"}
          </button>
          <Link href={`/case/${meta.id}/evidence`} className="btn btn-secondary btn-sm">
            Open evidence explorer
          </Link>
          <Link href={`/case/${meta.id}/challenge`} className="btn btn-signal btn-sm">
            Challenge this finding
          </Link>
        </div>
      </section>

      {/* --- 2. Repo DNA ----------------------------------------------- */}
      <section className="case-section" aria-labelledby="dna-heading">
        <h2 id="dna-heading" className="case-section-heading">
          Repo DNA
        </h2>
        <RepoDna
          title="Evidence layers"
          values={Object.fromEntries(
            LAYER_ORDER.map((layer) => [
              layer,
              Math.min(1, (counts[layer] ?? 0) / 4),
            ]),
          ) as never}
        />
      </section>

      {/* --- 3. Strongest evidence ------------------------------------- */}
      <section className="case-section" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading" className="case-section-heading">
          Strongest evidence
        </h2>
        <p className="case-section-note">
          Every item is bound to a pinned commit and a file path. Scroll the
          explorer for the full set with bounded excerpts from both sides.
        </p>
        <ul className="evidence-list">
          {report.evidence.slice(0, 8).map((item) => (
            <li key={item.id}>
              <EvidenceRow item={item} />
            </li>
          ))}
        </ul>
        {report.evidence.length > 8 ? (
          <Link href={`/case/${meta.id}/evidence`} className="btn btn-secondary btn-sm case-more">
            View all {report.evidence.length} evidence items
          </Link>
        ) : null}
      </section>

      {/* --- 4. Conflicting evidence ----------------------------------- */}
      {report.conflicting_evidence.length > 0 ? (
        <section className="case-section" aria-labelledby="conflicting-heading">
          <h2 id="conflicting-heading" className="case-section-heading">
            Conflicting evidence
          </h2>
          <p className="case-section-note">
            Evidence that argues against the verdict. ForkReason does not hide it.
          </p>
          <ul className="evidence-list evidence-list-conflicting">
            {report.conflicting_evidence.slice(0, 6).map((item) => (
              <li key={item.id}>
                <EvidenceRow item={item} conflicting />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* --- 5. Alternative explanations -------------------------------- */}
      <section className="case-section" aria-labelledby="explanations-heading">
        <h2 id="explanations-heading" className="case-section-heading">
          Alternative explanations
        </h2>
        <p className="case-section-note">
          Every explanation ForkReason can weigh, scored on evidence. The selected
          one is marked; the rest are shown because a verdict is only credible if
          you can see what it beat.
        </p>
        <ul className="explanation-list">
          {report.alternative_explanations.map((explanation) => (
            <li
              key={explanation.kind}
              className="explanation-item"
              data-selected={explanation.is_selected}
            >
              <div className="explanation-head">
                <span className="explanation-kind">
                  {EXPLANATION_LABEL[explanation.kind] ?? explanation.kind}
                </span>
                <span className={`badge badge-${explanation.support === "HIGH" ? "coral" : explanation.support === "MEDIUM" ? "amber" : "muted"}`}>
                  {explanation.support}
                </span>
                {explanation.is_selected ? (
                  <span className="badge badge-mint">selected</span>
                ) : null}
              </div>
              <div
                className="explanation-meter"
                role="meter"
                aria-valuenow={Math.round(explanation.score * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${explanation.kind} support`}
              >
                <span
                  className="explanation-meter-fill"
                  data-selected={explanation.is_selected}
                  style={{ width: `${Math.round(explanation.score * 100)}%` }}
                />
              </div>
              <p className="explanation-why">{explanation.rationale}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* --- 6. Evidence graph ------------------------------------------ */}
      {graph && graph.nodes.length > 2 ? (
        <section className="case-section" aria-labelledby="graph-heading">
          <h2 id="graph-heading" className="case-section-heading">
            Evidence graph
          </h2>
          <div className="glass case-graph-panel" data-tint="aqua">
            <EvidenceGraph
              nodes={graph.nodes}
              edges={graph.edges}
              evidence={report.evidence}
              originRepo={meta.origin_repo}
              targetRepo={meta.target_repo}
              sharedUpstream={verdict.shared_upstream}
            />
          </div>
        </section>
      ) : null}

      {/* --- 7. Consensus ------------------------------------------------ */}
      <section className="case-section" aria-labelledby="consensus-heading">
        <h2 id="consensus-heading" className="case-section-heading">
          GenLayer consensus
        </h2>
        <div className="consensus-panel">
          <div className="consensus-field">
            <span className="eyebrow">Verdict</span>
            <span className="mono">{verdict.verdict}</span>
          </div>
          <div className="consensus-field">
            <span className="eyebrow">Confidence bucket</span>
            <span className="mono">{verdict.confidence}</span>
          </div>
          <div className="consensus-field">
            <span className="eyebrow">Direction</span>
            <span className="mono">{verdict.direction ?? "NONE"}</span>
          </div>
          <div className="consensus-field">
            <span className="eyebrow">Independent origin</span>
            <span className="mono">
              {verdict.independent_origin_plausibility ?? "—"}
            </span>
          </div>
          <div className="consensus-field consensus-field-wide">
            <span className="eyebrow">Evidence manifest hash</span>
            <span className="mono consensus-hash">{meta.manifest_hash}</span>
          </div>
          <div className="consensus-field">
            <span className="eyebrow">Network</span>
            <span className="mono">{verdict.network ?? "not yet recorded"}</span>
          </div>
          <div className="consensus-field consensus-field-wide">
            <span className="eyebrow">Transaction</span>
            {verdict.tx_hash ? (
              <span className="mono consensus-hash">{verdict.tx_hash}</span>
            ) : (
              <span className="consensus-pending">
                Not yet submitted. Connect a wallet to record this finding on
                chain — the analysis itself needs no signature.
              </span>
            )}
          </div>
        </div>
        <p className="prose-note">
          The manifest hash is a SHA-256 over canonical JSON. Anyone can
          recompute it from the same pinned commits and confirm nothing was
          altered between analysis and record.
        </p>
      </section>

      {/* --- 8. Revisions ------------------------------------------------ */}
      <section className="case-section" aria-labelledby="revisions-heading">
        <h2 id="revisions-heading" className="case-section-heading">
          Revision history
        </h2>
        <ol className="revision-list">
          {report.revisions.map((revision) => (
            <li key={revision.revision_number} className="revision-item" data-current={revision.is_current}>
              <div className="revision-head">
                <span className="revision-number mono">rev {revision.revision_number}</span>
                <span className={`badge badge-${VERDICT_META[revision.verdict as Verdict].tone}`}>
                  {VERDICT_META[revision.verdict as Verdict].label}
                </span>
                <span className="badge badge-muted">{revision.confidence}</span>
                {revision.is_current ? (
                  <span className="badge badge-mint">current</span>
                ) : null}
              </div>
              <p className="revision-meta mono">
                manifest {shortSha(revision.manifest_hash, 16)}
                {revision.created_at ? ` · ${formatDate(revision.created_at)}` : ""}
                {revision.tx_hash ? ` · tx ${shortSha(revision.tx_hash, 12)}` : ""}
              </p>
            </li>
          ))}
        </ol>
        <p className="prose-note">
          Revisions are append-only. A challenge adds revision N+1 and never
          rewrites revision N.
        </p>
      </section>

      <section className="case-section case-section-last" aria-labelledby="challenge-cta">
        <h2 id="challenge-cta" className="case-section-heading">
          Disagree with this finding?
        </h2>
        <p className="prose">
          If you have evidence this analysis missed — a declared fork parent, an
          earlier commit, a common ancestor — challenge it. The challenge is
          signed by your wallet and produces a new revision. The original stays
          readable.
        </p>
        <Link href={`/case/${meta.id}/challenge`} className="btn btn-signal">
          Challenge this case
        </Link>
      </section>
    </div>
  );
}

function EvidenceRow({
  item,
  conflicting = false,
}: {
  item: CaseReport["evidence"][number];
  conflicting?: boolean;
}) {
  const tone = conflicting ? "coral" : item.strength === "HIGH" ? "coral" : item.strength === "MEDIUM" ? "amber" : "muted";
  return (
    <article className="evidence-row" data-conflicting={conflicting}>
      <div className="evidence-row-head">
        <span className={`badge badge-${tone}`}>{item.strength}</span>
        <span className="evidence-layer">{LAYER_LABEL[item.dna_layer] ?? item.dna_layer}</span>
        <span className="evidence-type mono">{item.evidence_type.replace(/_/g, " ")}</span>
      </div>

      <p className="evidence-why">{item.rationale}</p>

      <div className="evidence-sources">
        <div className="evidence-source">
          <span className="eyebrow">Origin</span>
          <span className="mono evidence-source-repo">{item.origin.repo}</span>
          {item.origin.path ? (
            <span className="mono evidence-source-path">{item.origin.path}</span>
          ) : null}
          {item.origin.commit ? (
            <span className="mono evidence-source-commit" title={item.origin.commit}>
              {shortSha(item.origin.commit)}
            </span>
          ) : null}
        </div>
        <div className="evidence-source">
          <span className="eyebrow">Target</span>
          <span className="mono evidence-source-repo">{item.target.repo}</span>
          {item.target.path ? (
            <span className="mono evidence-source-path">{item.target.path}</span>
          ) : null}
          {item.target.commit ? (
            <span className="mono evidence-source-commit" title={item.target.commit}>
              {shortSha(item.target.commit)}
            </span>
          ) : null}
        </div>
      </div>

      {item.excerpt ? <pre className="evidence-excerpt">{item.excerpt}</pre> : null}
    </article>
  );
}