"use client";

import { useState } from "react";

import { RepoDna } from "@/components/repo-dna";
import { CONFIDENCE_META, VERDICT_META } from "@/lib/presentation";
import type { Confidence, Verdict } from "@/lib/api";

/**
 * Landing content sections.
 *
 * These are the narrative beats of the page. Fixture-derived content is always
 * labelled as such — a demo case presented as live production history would
 * undermine the whole product (constitution I.4).
 */

export function ProductProof() {
  return (
    <section className="section proof-section" aria-labelledby="proof-heading">
      <div className="layout">
        <header className="section-head">
          <p className="eyebrow">A worked example</p>
          <h2 id="proof-heading" className="heading-2">
            A finding, with its counter-evidence attached
          </h2>
          <p className="lead">
            This is a fixture bundled with ForkReason for demonstration. Real
            cases in Explore come from actual repository analyses.
          </p>
        </header>

        <FixtureCase />
      </div>
    </section>
  );
}

function FixtureCase() {
  const verdict = "LIKELY_DERIVED" as Verdict;
  const confidence = "HIGH" as Confidence;
  const meta = VERDICT_META[verdict];
  const confidenceMeta = CONFIDENCE_META[confidence];

  return (
    <div className="glass proof-case" data-tint="coral">
      <div className="proof-case-head">
        <div>
          <p className="eyebrow">Fixture · not live data</p>
          <div className="proof-pair">
            <span className="mono">acme/ledger-core</span>
            <span className="proof-arrow" aria-label="derived into">
              →
            </span>
            <span className="mono">contrib/ledger-engine</span>
          </div>
        </div>
        <div className="proof-verdict">
          <span className={`badge badge-${meta.tone}`}>{meta.label}</span>
          <span className={`badge badge-${confidenceMeta.tone}`}>{confidence}</span>
        </div>
      </div>

      <p className="proof-summary">
        The target carries an off-by-one defect the origin fixed five months
        earlier, shares uncommon constants, and reuses distinctive test names
        under renamed modules. The commit timeline puts the origin first.
      </p>

      <ul className="proof-signals">
        <li>
          <span className="proof-signal-count">5</span>
          <span className="proof-signal-label">strong signals</span>
        </li>
        <li>
          <span className="proof-signal-count proof-signal-count-coral">1</span>
          <span className="proof-signal-label">conflicting signal</span>
        </li>
        <li>
          <span className="proof-signal-count proof-signal-count-aqua">6</span>
          <span className="proof-signal-label">explanations weighed</span>
        </li>
        <li>
          <span className="proof-signal-count proof-signal-count-signal">1</span>
          <span className="proof-signal-label">revision recorded</span>
        </li>
      </ul>

      <p className="proof-conflict">
        <strong>Counter-evidence kept:</strong> the target&apos;s author renamed
        every module and rewrote the public API. ForkReason reports that
        divergence rather than suppressing it.
      </p>
    </div>
  );
}

export function HowItThinks() {
  const steps = [
    { label: "Similarity", tone: "muted", text: "Two files match. That alone explains nothing — every framework produces matches." },
    { label: "Chronology", tone: "aqua", text: "Did the signal appear in the origin before the target? Without order, similarity is coincidence." },
    { label: "Historical evidence", tone: "coral", text: "Shared defects, fix timing, and implementation order narrow what actually happened." },
    { label: "Alternative explanations", tone: "amber", text: "Shared upstream, same specification, coincidence, insufficient history — each scored on its own evidence." },
    { label: "Consensus", tone: "signal", text: "Independent validators re-derive the decision from the same evidence. Agreement is recorded on chain." },
  ];

  return (
    <section className="section think-section" aria-labelledby="think-heading">
      <div className="layout">
        <header className="section-head">
          <p className="eyebrow">The reasoning</p>
          <h2 id="think-heading" className="heading-2">
            Similarity is not lineage
          </h2>
          <p className="lead">
            A code-matching tool answers &ldquo;how similar are these?&rdquo; and
            stops. A lineage tool has to answer &ldquo;what actually happened
            here?&rdquo; — and be honest when the answer is nothing.
          </p>
        </header>

        <ol className="think-chain">
          {steps.map((step, index) => (
            <li key={step.label} className="think-step" data-tone={step.tone}>
              <span className="think-step-index" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="think-step-label">{step.label}</h3>
              <p className="think-step-text">{step.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export function DnaSection() {
  return (
    <section className="section dna-section" aria-labelledby="dna-heading">
      <div className="layout">
        <header className="section-head">
          <p className="eyebrow">The evidence model</p>
          <h2 id="dna-heading" className="heading-2">
            Six layers, weighted against coincidence
          </h2>
          <p className="lead">
            ForkReason measures a repository across six independent dimensions. A
            match on framework boilerplate is discounted to nothing before it can
            become evidence of anything.
          </p>
        </header>

        <RepoDna />

        <p className="dna-note">
          Each layer can be strong on its own and still lead to{' '}
          <span className="badge badge-muted">INSUFFICIENT_EVIDENCE</span>. That
          outcome is a result, not a failure.
        </p>
      </div>
    </section>
  );
}

export function WhyGenLayer() {
  const steps = [
    { n: "01", label: "Evidence", text: "The pipeline produces a bounded manifest: strongest signals, contradictions, and every competing explanation.", tone: "aqua" },
    { n: "02", label: "Independent evaluation", text: "Validators do not vote on the leader's answer. Each derives its own conclusion from the same evidence.", tone: "mint" },
    { n: "03", label: "Stable fields compared", text: "Verdict, direction, shared upstream, confidence bucket. Prose is never compared for equality.", tone: "volt" },
    { n: "04", label: "Consensus", text: "Agreement produces a decision. Disagreement produces nothing — the case does not resolve as accepted.", tone: "signal" },
    { n: "05", label: "Immutable revision", text: "The finding is recorded with its manifest hash. It is appended to, never edited.", tone: "amber" },
  ];

  return (
    <section className="section genlayer-section" aria-labelledby="genlayer-heading">
      <div className="layout">
        <div className="genlayer-grid">
          <div className="genlayer-copy">
            <p className="eyebrow">Why GenLayer</p>
            <h2 id="genlayer-heading" className="heading-2">
              One model does not decide the case
            </h2>
            <p className="lead">
              A lineage finding is a judgement about the past. Judgements that
              rest on one model reading two READMEs are not verifiable, and not
              worth recording.
            </p>
            <p className="prose">
              GenLayer runs the decision through independent validators. A
              validator that merely confirms the leader has parsed valid JSON is
              not verification — so ForkReason&apos;s validators recompute the
              decision from the evidence and compare the substantive fields.
            </p>
            <p className="prose">
              The result is a record anyone can check: the evidence manifest, its
              hash, the revision, and the transaction that committed it.
            </p>
          </div>

          <ol className="genlayer-steps">
            {steps.map((step) => (
              <li key={step.n} className="genlayer-step" data-tone={step.tone}>
                <span className="genlayer-step-n mono">{step.n}</span>
                <div>
                  <h3 className="genlayer-step-label">{step.label}</h3>
                  <p className="genlayer-step-text">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

export function ChallengeSection() {
  const [stage, setStage] = useState<1 | 2>(1);
  return (
    <section className="section challenge-section" aria-labelledby="challenge-heading">
      <div className="layout">
        <header className="section-head">
          <p className="eyebrow">Contestable by design</p>
          <h2 id="challenge-heading" className="heading-2">
            A conclusion you disagree with should not be the end of it
          </h2>
          <p className="lead">
            Every resolved case can be challenged with new evidence. Revision N is
            never overwritten — a challenge produces revision N+1, and both stay
            readable forever.
          </p>
        </header>

        <div className="glass challenge-demo" data-tint="amber">
          <div className="challenge-revisions" role="group" aria-label="Challenge example">
            <button
              type="button"
              className="challenge-revision"
              data-active={stage === 1}
              onClick={() => setStage(1)}
              aria-pressed={stage === 1}
            >
              <span className="eyebrow">Revision 1</span>
              <span className={`badge badge-${VERDICT_META.LIKELY_DERIVED.tone}`}>
                {VERDICT_META.LIKELY_DERIVED.label}
              </span>
              <span className="challenge-revision-note">high confidence</span>
            </button>

            <div className="challenge-arrow" aria-hidden="true">
              <span />
            </div>

            <button
              type="button"
              className="challenge-revision"
              data-active={stage === 2}
              onClick={() => setStage(2)}
              aria-pressed={stage === 2}
            >
              <span className="eyebrow">Revision 2</span>
              <span className={`badge badge-${VERDICT_META.SHARED_UPSTREAM.tone}`}>
                {VERDICT_META.SHARED_UPSTREAM.label}
              </span>
              <span className="challenge-revision-note">common ancestor found</span>
            </button>
          </div>

          <div className="challenge-detail" aria-live="polite">
            {stage === 1 ? (
              <>
                <h3 className="heading-3">The first pass</h3>
                <p className="prose">
                  Strong code and bug signals, a compatible timeline, and no
                  counter-evidence. ForkReason records a derivation and stops
                  there.
                </p>
              </>
            ) : (
              <>
                <h3 className="heading-3">After a challenge</h3>
                <p className="prose">
                  A challenger supplies the origin project&apos;s own declared
                  fork parent. That explains the shared code better than
                  derivation does, so the new revision reads{' '}
                  <span className="badge badge-aqua">SHARED_UPSTREAM</span> — and
                  revision 1 remains readable.
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export function OpenSourceSection() {
  return (
    <section className="section oss-section" aria-labelledby="oss-heading">
      <div className="layout">
        <div className="oss-grid">
          <div>
            <p className="eyebrow">Verifiable by construction</p>
            <h2 id="oss-heading" className="heading-2">
              Open source, because the evidence has to be checkable
            </h2>
            <p className="lead">
              A forensic claim you cannot audit is a rumour with a nice font.
              ForkReason&apos;s pipeline, evidence model, contract and verdicts
              are all public.
            </p>
          </div>

          <ul className="oss-links">
            <li>
              <a
                href="https://github.com/0xbardia/ForkReason"
                target="_blank"
                rel="noopener noreferrer"
                className="oss-link"
              >
                <span className="oss-link-label">Source repository</span>
                <span className="oss-link-value mono">github.com/0xbardia/ForkReason</span>
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </li>
            <li>
              <a href="/docs/consensus" className="oss-link">
                <span className="oss-link-label">Consensus model</span>
                <span className="oss-link-value">How validators decide</span>
              </a>
            </li>
            <li>
              <a href="/docs/evidence-model" className="oss-link">
                <span className="oss-link-label">Evidence model</span>
                <span className="oss-link-value">What counts, and why</span>
              </a>
            </li>
            <li>
              <a href="/security" className="oss-link">
                <span className="oss-link-label">Security &amp; threat model</span>
                <span className="oss-link-value">Adversarial testing</span>
              </a>
            </li>
            <li>
              <a href="/docs/limitations" className="oss-link">
                <span className="oss-link-label">Limitations</span>
                <span className="oss-link-value">What ForkReason cannot do</span>
              </a>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section className="section cta-section" aria-labelledby="cta-heading">
      <div className="layout">
        <div className="glass cta-panel" data-tint="mint">
          <div className="cta-glow" aria-hidden="true" />
          <h2 id="cta-heading" className="heading-1 cta-heading">
            Find out where it came from.
          </h2>
          <p className="lead cta-lead">
            Two repositories. A real forensic pipeline. A decision you can
            check, challenge, and trace back to the evidence.
          </p>
          <div className="cta-actions">
            <a href="/trace" className="btn btn-primary btn-lg">
              Trace a relationship
            </a>
            <a href="/explore" className="btn btn-secondary btn-lg">
              Explore public cases
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}