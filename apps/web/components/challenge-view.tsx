"use client";

import Link from "next/link";
import { useAccount, useWalletClient } from "wagmi";
import { useState } from "react";

import { api, ApiClientError, type ChallengePreparation } from "@/lib/api";
import { writeContract, statusLabel, type TxPhase } from "@/lib/genlayer";

const PHASE_COPY: Record<TxPhase, string> = {
  idle: "",
  preparing: "Preparing the challenge payload…",
  awaiting_signature: "Review the transaction in your wallet and sign.",
  submitted: "Transaction submitted to the GenLayer network.",
  awaiting_decision: "Validators are reaching consensus. This is not instant.",
  finalizing: "Recording the transaction reference…",
  accepted: "Challenge submitted. The revision appears once consensus completes.",
  failed: "",
  undetermined: "",
};

/**
 * Challenge surface.
 *
 * The whole chain boundary is visible here: the backend prepares, the wallet
 * signs, and the UI states plainly that ForkReason's server holds no key that
 * could act for the user.
 */
export function ChallengeView({ caseId }: { caseId: string }) {
  const { address, isConnected, chainId } = useAccount();
  const { data: walletClient } = useWalletClient();

  const [rationale, setRationale] = useState("");
  const [evidenceSummary, setEvidenceSummary] = useState("");
  const [preparation, setPreparation] = useState<ChallengePreparation | null>(null);
  const [phase, setPhase] = useState<TxPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ txId: string; statusName?: string } | null>(null);

  const canPrepare = rationale.trim().length >= 10 && evidenceSummary.trim().length >= 10;
  const canSign = Boolean(isConnected && address && walletClient && preparation);

  async function prepare() {
    if (!canPrepare) return;
    setError(null);
    setResult(null);
    setPhase("preparing");
    try {
      const payload = await api.prepareChallenge(caseId, {
        rationale: rationale.trim(),
        evidence_summary: evidenceSummary.trim(),
        submitter: address ?? "0x0000000000000000000000000000000000000000",
      });
      setPreparation(payload);
      setPhase("idle");
    } catch (err) {
      setPhase("idle");
      setError(
        err instanceof ApiClientError ? err.message : "The challenge could not be prepared.",
      );
    }
  }

  async function sign() {
    if (!preparation || !address || !walletClient) return;
    setError(null);
    setPhase("awaiting_signature");

    const outcome = await writeContract(
      {
        functionName: preparation.write.method,
        args: preparation.write.args,
        account: address,
        provider: walletClient,
      },
      setPhase,
    );

    if (outcome.ok && outcome.txId) {
      setResult({ txId: outcome.txId, statusName: outcome.statusName });
      setPhase("accepted");
      try {
        await api.markChallengeSubmitted(caseId, preparation.challenge_id, outcome.txId);
      } catch {
        // Indexing failure must not invalidate a signed transaction.
      }
      return;
    }

    if (outcome.phase === "undetermined") {
      setError(
        `${outcome.message ?? "Validators did not reach a decision."} Transaction ${outcome.txId} can be appealed on GenLayer.`,
      );
      setResult({ txId: outcome.txId ?? "", statusName: outcome.statusName });
      setPhase("undetermined");
      return;
    }

    setError(outcome.message ?? "The transaction did not complete.");
    setPhase("failed");
  }

  return (
    <div className="layout prose-page">
      <header className="prose-page-head">
        <Link href={`/case/${caseId}`} className="evidence-back">
          ← Back to case report
        </Link>
        <h1 className="heading-1">Challenge this finding</h1>
        <p className="lead">
          A challenge submits new evidence and produces revision N+1. Revision N is
          never overwritten — both remain readable forever.
        </p>
      </header>

      <section className="challenge-boundary">
        <div className="challenge-boundary-step">
          <span className="challenge-boundary-n mono">1</span>
          <div>
            <h2 className="challenge-boundary-label">You describe the evidence</h2>
            <p className="challenge-boundary-text">
              What does ForkReason have that the analysis missed?
            </p>
          </div>
        </div>
        <div className="challenge-boundary-step">
          <span className="challenge-boundary-n mono">2</span>
          <div>
            <h2 className="challenge-boundary-label">ForkReason prepares</h2>
            <p className="challenge-boundary-text">
              The server builds a bounded digest. It holds no key that can sign for
              you.
            </p>
          </div>
        </div>
        <div className="challenge-boundary-step">
          <span className="challenge-boundary-n mono">3</span>
          <div>
            <h2 className="challenge-boundary-label">You sign</h2>
            <p className="challenge-boundary-text">
              Your wallet signs the transaction. Validators then re-derive the
              decision from the new evidence.
            </p>
          </div>
        </div>
      </section>

      <section className="challenge-form">
        <div className="challenge-field">
          <label htmlFor="challenge-rationale" className="challenge-label">
            Why should the verdict change?
          </label>
          <p id="challenge-rationale-hint" className="challenge-hint">
            Be specific. &ldquo;The origin declares a fork parent that ForkReason did
            not consider&rdquo; is useful; &ldquo;it is wrong&rdquo; is not.
          </p>
          <textarea
            id="challenge-rationale"
            className="challenge-textarea"
            rows={3}
            maxLength={600}
            value={rationale}
            aria-describedby="challenge-rationale-hint"
            onChange={(event) => setRationale(event.target.value)}
            placeholder="The origin repository declares acme/common-core as its fork parent, which explains the shared code better than derivation."
          />
          <span className="challenge-count mono">{rationale.length}/600</span>
        </div>

        <div className="challenge-field">
          <label htmlFor="challenge-evidence" className="challenge-label">
            Supporting evidence
          </label>
          <p id="challenge-evidence-hint" className="challenge-hint">
            Commits, file paths, a declared parent, a link. ForkReason treats this
            as data, never as instructions.
          </p>
          <textarea
            id="challenge-evidence"
            className="challenge-textarea"
            rows={5}
            maxLength={2000}
            value={evidenceSummary}
            aria-describedby="challenge-evidence-hint"
            onChange={(event) => setEvidenceSummary(event.target.value)}
            placeholder="origin declares parent: acme/common-core (seen in the GitHub API 'parent' field). The shared CHECKPOINT_MAGIC constant appears in acme/common-core at commit 4f2a1b0, dated before both repositories."
          />
          <span className="challenge-count mono">{evidenceSummary.length}/2000</span>
        </div>

        {!isConnected ? (
          <p className="challenge-connect-note" role="status">
            You can prepare a challenge without a wallet. You will be asked to
            connect one when you are ready to sign it.
          </p>
        ) : null}

        {preparation ? (
          <div className="challenge-prepared">
            <p className="challenge-prepared-label eyebrow">Prepared transaction</p>
            <dl className="challenge-prepared-fields">
              <div>
                <dt>Contract</dt>
                <dd className="mono">{preparation.write.contract}</dd>
              </div>
              <div>
                <dt>Method</dt>
                <dd className="mono">{preparation.write.method}</dd>
              </div>
              <div>
                <dt>Base revision</dt>
                <dd className="mono">{preparation.base_revision}</dd>
              </div>
              <div>
                <dt>Expected revision</dt>
                <dd className="mono">{preparation.expected_revision}</dd>
              </div>
              <div>
                <dt>Digest hash</dt>
                <dd className="mono">{preparation.evidence_digest_sha256.slice(0, 24)}</dd>
              </div>
              <div>
                <dt>Network</dt>
                <dd className="mono">{preparation.chain.network}</dd>
              </div>
            </dl>
            {preparation.chain.contract_address ? (
              <p className="challenge-prepared-address mono">
                contract {preparation.chain.contract_address}
              </p>
            ) : (
              <p className="challenge-prepared-address">
                ForkReason&apos;s contract is not configured on this deployment, so
                signing will be refused rather than silently discarded.
              </p>
            )}
          </div>
        ) : null}

        {phase && PHASE_COPY[phase] ? (
          <p className="challenge-phase" role="status" aria-live="polite">
            {PHASE_COPY[phase]}
          </p>
        ) : null}

        {result ? (
          <div className="challenge-result" role="status">
            <p className="mono challenge-result-tx">transaction {result.txId}</p>
            {result.statusName ? (
              <p className="challenge-result-status">{statusLabel(result.statusName)}</p>
            ) : null}
            <Link href={`/case/${caseId}`} className="btn btn-secondary btn-sm">
              Return to the case
            </Link>
          </div>
        ) : null}

        {error ? (
          <p className="challenge-error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="challenge-actions">
          {!preparation ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void prepare()}
              disabled={!canPrepare}
            >
              Prepare challenge
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-signal"
              onClick={() => void sign()}
              disabled={!canSign || phase === "awaiting_signature" || phase === "submitted" || phase === "awaiting_decision"}
            >
              {phase === "awaiting_signature" || phase === "submitted" || phase === "awaiting_decision"
                ? "Waiting for consensus…"
                : isConnected
                  ? "Sign with your wallet"
                  : "Connect a wallet to sign"}
            </button>
          )}

          {preparation ? (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setPreparation(null);
                setPhase("idle");
                setResult(null);
              }}
            >
              Edit and re-prepare
            </button>
          ) : null}
        </div>

        <p className="challenge-footnote">
          ForkReason never signs a transaction on your behalf. If you do not
          approve it in your wallet, nothing is sent and no state changes.
        </p>
      </section>
    </div>
  );
}