"use client";

/**
 * Security surface.
 *
 * The claims here are only worth making if they are backed by tests, so each
 * one names the gate that enforces it. Anything accepted as residual risk is
 * labelled as such rather than presented as solved.
 */
export function SecurityView() {
  return (
    <div className="layout prose-page">
      <header className="prose-page-head">
        <p className="eyebrow">Trust</p>
        <h1 className="heading-1">Security</h1>
        <p className="lead">
          ForkReason analyzes hostile input and lets a model participate in a
          decision. Both are treated as attack surfaces rather than features.
        </p>
      </header>

      <section className="prose-section">
        <h2 className="heading-3">Repository content is never executed</h2>
        <p>
          Analyzed repositories are untrusted input. ForkReason materializes a
          snapshot with <code>git archive &lt;pinned-sha&gt;</code> into an
          isolated staging repository, which yields exactly the tracked blobs at
          one commit. There is no working tree, no <code>.git</code> directory,
          no hooks, and no submodule content.
        </p>
        <ul>
          <li>No <code>npm install</code>, build, or package script ever runs.</li>
          <li>Every <code>git</code> call is an argument array with <code>shell=false</code>.</li>
          <li>
            The git environment sets <code>GIT_CONFIG_NOSYSTEM</code>,{" "}
            <code>GIT_CONFIG_GLOBAL=/dev/null</code> and{" "}
            <code>GIT_ASKPASS=/bin/false</code>, so repository configuration
            cannot influence execution.
          </li>
          <li>
            Symlinks, hard links, devices, absolute paths and traversal are
            rejected before and after path resolution.
          </li>
        </ul>
        <p className="prose-note">
          Verified by <code>apps/api/tests/test_safe_intake.py</code> against
          archives that attempt traversal and symlink escape.
        </p>
      </section>

      <section className="prose-section">
        <h2 className="heading-3">Prompt injection is a release gate</h2>
        <p>
          Consensus does not defend against prompt injection. If the leader and
          every validator read the same malicious instruction and obey it, they
          agree on the same wrong answer — and agreement is exactly what
          consensus is supposed to mean.
        </p>
        <p>The defences, in the order they apply:</p>
        <ol>
          <li>
            Deterministic preprocessing. Fingerprinting strips comments and
            string literals before any structural comparison.
          </li>
          <li>
            Minimal excerpts. The consensus digest is capped at 12,000
            characters and never contains whole files.
          </li>
          <li>
            Strong delimiters. Untrusted content is fenced inside{" "}
            <code>&lt;forkreason_evidence&gt;</code> tags.
          </li>
          <li>
            Explicit inert-data instruction, stated as an absolute rule above
            the evidence block.
          </li>
          <li>Strict typed parsing against an allowed enum set.</li>
          <li>
            Deterministic rule checks in code — chronology, contradiction
            between verdict and confidence, and the shared-upstream requirement.
          </li>
          <li>Independent validator evaluation of the substantive fields.</li>
          <li>Fail closed: unparseable or off-enum output is rejected.</li>
        </ol>
        <p className="prose-note">
          Verified by <code>contracts/tests/test_prompt_injection.py</code>,
          which places the mandated attack phrases in a README, a code comment,
          a string constant, HTML, commit metadata and challenge evidence — and
          asserts that a verdict demanded by injected text is refused even when
          the leader has already obeyed it.
        </p>
      </section>

      <section className="prose-section">
        <h2 className="heading-3">Verdicts are checked for substance</h2>
        <p>
          A leader is never accepted because its output parses. The validator
          independently derives its own decision from the same bounded evidence,
          applies the same deterministic guards, and compares the stable field
          tuple: verdict, confidence, direction, shared upstream, independent
          origin plausibility, and evidence classes. Rationale prose is never
          compared for equality.
        </p>
        <p>
          A test drives the exact scenario that matters: a leader that returns a
          valid-looking but substantively incorrect verdict. The validator must
          reject it.
        </p>
      </section>

      <section className="prose-section">
        <h2 className="heading-3">Your keys stay with you</h2>
        <p>
          ForkReason holds no server key that can act for a user. Every
          state-changing GenLayer action is signed by the browser wallet. The
          backend prepares payloads and indexes transaction hashes it observes; it
          never signs a write on a user's behalf.
        </p>
        <p>
          The chain is the authority on revision and verdict state. The
          application database indexes that state for search and display, and
          never silently becomes an alternative source of truth.
        </p>
      </section>

      <section className="prose-section">
        <h2 className="heading-3">Browser protections</h2>
        <ul>
          <li>
            A nonce-based Content Security Policy restricts scripts to what this
            server emitted for the current request. Styles allow inline because
            Next injects critical CSS that way.
          </li>
          <li>
            <code>frame-ancestors 'none'</code>, <code>X-Frame-Options: DENY</code>,{" "}
            <code>nosniff</code>, strict referrer policy and a restrictive
            permissions policy are set on every response.
          </li>
          <li>
            No remote images, so the image optimizer is not an open proxy.
          </li>
          <li>
            A decided transaction is never reported as successful unless the
            execution result is <code>FINISHED_WITH_RETURN</code>.{" "}
            <code>ACCEPTED</code> only means the committee agreed on the receipt.
          </li>
        </ul>
      </section>

      <section className="prose-section">
        <h2 className="heading-3">Accepted residual risk</h2>
        <div className="risk-table" role="table" aria-label="Accepted residual risks">
          <div className="risk-row risk-row-head" role="row">
            <span role="columnheader">Risk</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Rationale</span>
          </div>
          <div className="risk-row" role="row">
            <span role="cell">
              <code>'unsafe-eval'</code> in the CSP script-src
            </span>
            <span role="cell">
              <span className="badge badge-amber">accepted</span>
            </span>
            <span role="cell">
              WalletConnect's SDK evaluates a dynamically built bundle. Removing
              it breaks wallet connectivity. Scoped to <code>script-src</code>;
              no third-party script origins are permitted.
            </span>
          </div>
          <div className="risk-row" role="row">
            <span role="cell">
              Public GitHub API rate limits without a token
            </span>
            <span role="cell">
              <span className="badge badge-amber">accepted</span>
            </span>
            <span role="cell">
              Unauthenticated requests are limited per IP. ForkReason degrades to
              a clear error with bounded retry rather than hiding the problem. A
              token is recommended in production.
            </span>
          </div>
          <div className="risk-row" role="row">
            <span role="cell">
              Moderate advisories in WalletConnect / Reown SDKs
            </span>
            <span role="cell">
              <span className="badge badge-amber">accepted</span>
            </span>
            <span role="cell">
              Transitive, no fix without breaking RainbowKit 2.2.11, and only
              reachable when a WalletConnect project id is configured. No
              critical or high advisories remain.
            </span>
          </div>
        </div>
      </section>

      <section className="prose-section">
        <h2 className="heading-3">Disclosure</h2>
        <p>
          If you believe you have found a vulnerability, open a private security
          advisory on the{" "}
          <a
            href="https://github.com/0xbardia/ForkReason/security/advisories/new"
            target="_blank"
            rel="noopener noreferrer"
          >
            repository
          </a>
          . Please do not open a public issue for an unfixed vulnerability.
        </p>
        <p>
          Full detail lives in <code>SECURITY.md</code>,{" "}
          <code>docs/THREAT-MODEL.md</code> and{" "}
          <code>docs/SECURITY-FINDINGS.md</code>.
        </p>
      </section>
    </div>
  );
}