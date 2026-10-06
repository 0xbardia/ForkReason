"use client";

import { ConnectButton } from "@rainbow-me/rainbowkit";
import { useAccount, useWalletClient } from "wagmi";
import { useEffect, useState } from "react";

import { GENLAYER_NETWORK } from "@/components/providers";
import { api, ApiClientError, type CaseReport, type SubmitCasePreparation } from "@/lib/api";
import { buildSubmitCaseArgs } from "@/lib/case-registration";
import { contractAddress, statusLabel, walletMatchesNetwork, writeContract, type TxPhase } from "@/lib/genlayer";

const TX_KEY = (caseId: string) => `forkreason:registration:${caseId}`;
const PHASE_COPY: Partial<Record<TxPhase, string>> = {
  preparing: "Checking the analyzed case and preparing the contract payload…",
  awaiting_signature: "Review the six case arguments in your wallet and sign.",
  submitted: "Transaction hash captured. Following the real GenLayer transaction…",
  awaiting_decision: "Validators are reaching consensus. The Case remains provisional until accepted.",
  pending: "Consensus is still pending. ForkReason will keep following this transaction.",
  accepted: "Consensus finalized. ForkReason is reconciling the accepted Case revision.",
  undetermined: "GenLayer consensus was undetermined. Your analysis remains available and was not registered.",
};

export function InitialRegistration({
  report,
  onReconciled,
}: {
  report: CaseReport;
  onReconciled: (report: CaseReport) => void;
}) {
  const { address, chainId, isConnected } = useAccount();
  const { data: walletClient } = useWalletClient();
  const [preparation, setPreparation] = useState<SubmitCasePreparation | null>(null);
  const [phase, setPhase] = useState<TxPhase>("idle");
  const [txId, setTxId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const walletOnNetwork = walletMatchesNetwork(GENLAYER_NETWORK, walletClient?.chain?.id ?? chainId);
  const accountMatches = Boolean(address && walletClient?.account.address.toLowerCase() === address.toLowerCase());

  useEffect(() => {
    const saved = window.localStorage.getItem(TX_KEY(report.case.id));
    const tx_hash = report.case.pending_tx_hash ?? (() => {
      if (!saved) return null;
      try { return (JSON.parse(saved) as { tx_hash?: string }).tx_hash ?? null; }
      catch { return null; }
    })();
    if (!tx_hash) return;
    try {
      if (!/^0x[0-9a-f]{64}$/i.test(tx_hash)) throw new Error("bad transaction id");
      setTxId(tx_hash);
      setPhase("pending");
      void api.recordChainWrite({
        case_id: report.case.id, tx_hash, kind: "registration",
      }).then((transaction) => {
        if (transaction.status === "consensus_pending") setPhase("pending");
        else setPhase("submitted");
      }).catch(() => undefined);
    } catch {
      window.localStorage.removeItem(TX_KEY(report.case.id));
    }
  }, [report.case.id, report.case.pending_tx_hash]);

  useEffect(() => {
    if (!txId || !["submitted", "awaiting_decision", "pending", "accepted"].includes(phase)) return;
    let stopped = false;
    const sync = async () => {
      try {
        // Re-recording is idempotent and recovers if the first API request
        // failed after the wallet had already returned its transaction id.
        await api.recordChainWrite({
          case_id: report.case.id, tx_hash: txId, kind: "registration",
        });
        const indexed = await api.getChainTransaction(txId);
        if (indexed.status === "failed" || indexed.status === "rejected") {
          window.localStorage.removeItem(TX_KEY(report.case.id));
          setError("GenLayer finalized this transaction without accepting the registration. Your analysis is unchanged.");
          setPhase("failed");
          return;
        }
        if (indexed.status === "undetermined") {
          setError("GenLayer consensus was undetermined. Your analysis is unchanged; you may retry registration.");
          setPhase("undetermined");
          return;
        }
        if (indexed.status === "consensus_pending") setPhase("pending");
        const latest = await api.getCase(report.case.id);
        if (!stopped && latest.case.current_revision >= 1) {
          window.localStorage.removeItem(TX_KEY(report.case.id));
          setPhase("accepted");
          setError(null);
          onReconciled(latest);
        }
      } catch {
        // Keep the durable tx id locally; the worker also retries indexed writes.
      }
    };
    void sync();
    const timer = window.setInterval(() => void sync(), 5000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [onReconciled, phase, report.case.id, txId]);

  async function register() {
    if (!isConnected || !address || !walletClient) {
      setError("Connect your wallet before registering. Your analysis remains available.");
      return;
    }
    if (!walletOnNetwork) {
      setError(`Switch your wallet to ${GENLAYER_NETWORK} before registering.`);
      return;
    }
    if (!accountMatches) {
      setError("The active wallet account changed. Reconnect the account and try again.");
      return;
    }
    setError(null);
    setPhase("preparing");
    try {
      const payload = await api.prepareSubmission(report.case.id);
      if (
        payload.chain.network !== GENLAYER_NETWORK ||
        payload.chain.contract_address.toLowerCase() !== contractAddress()?.toLowerCase()
      ) throw new Error("The API and browser GenLayer network configuration do not match.");
      const args = buildSubmitCaseArgs(report, payload);
      setPreparation(payload);
      const outcome = await writeContract({
        functionName: "submit_case",
        args,
        account: address,
        provider: walletClient,
        network: payload.chain.network,
      }, setPhase, async (id) => {
        window.localStorage.setItem(TX_KEY(report.case.id), JSON.stringify({ tx_hash: id }));
        setTxId(id);
        await api.recordChainWrite({ case_id: report.case.id, tx_hash: id, kind: "registration" });
      });
      if (outcome.txId) setTxId(outcome.txId);
      if (outcome.phase === "failed") {
        setError(outcome.message ?? "The transaction failed. Your analysis remains unchanged.");
        setPhase("failed");
      } else if (outcome.phase === "pending") {
        setError(outcome.message ?? null);
        setPhase("pending");
      } else if (outcome.phase === "undetermined") {
        setError(outcome.message ?? "GenLayer consensus was undetermined. Your analysis remains unchanged.");
        setPhase("undetermined");
      }
    } catch (cause) {
      setPhase("idle");
      setError(cause instanceof ApiClientError ? cause.message : cause instanceof Error ? cause.message : "Registration could not be prepared.");
    }
  }

  return (
    <section className="case-section registration-panel" aria-labelledby="registration-heading">
      <h2 id="registration-heading" className="case-section-heading">Register this analysis on GenLayer</h2>
      <p className="prose">
        This analysis is provisional until you sign <code>submit_case</code> and GenLayer accepts it.
        The public Case switches to the chain revision only after database reconciliation.
      </p>
      {!isConnected ? <ConnectButton /> : null}
      {isConnected && !walletOnNetwork ? (
        <p role="alert" className="challenge-error">Switch your wallet to {GENLAYER_NETWORK} before signing.</p>
      ) : null}
      {preparation ? (
        <details className="registration-arguments">
          <summary>Review all six contract arguments</summary>
          <ol>
            {preparation.write.args.map((value, index) => (
              <li key={index}><span>arg{index + 1}</span><code>{value}</code></li>
            ))}
          </ol>
        </details>
      ) : null}
      {PHASE_COPY[phase] ? <p role="status" aria-live="polite">{PHASE_COPY[phase]}</p> : null}
      {txId ? (
        <p className="mono registration-transaction">
          {statusLabel(phase === "accepted" ? "FINALIZED" : phase)} · {txId}
        </p>
      ) : null}
      {error ? <p role="alert" className="challenge-error">{error}</p> : null}
      <button
        type="button"
        className="btn btn-signal"
        disabled={!isConnected || !walletClient || !walletOnNetwork || phase === "preparing" || phase === "awaiting_signature" || phase === "submitted" || phase === "awaiting_decision" || phase === "pending" || report.case.current_revision > 0}
        onClick={() => void register()}
      >
        {phase === "pending" || phase === "submitted" || phase === "awaiting_decision"
          ? "Following transaction…"
          : isConnected && !walletOnNetwork ? `Switch wallet to ${GENLAYER_NETWORK}`
            : isConnected ? "Sign and register this Case" : "Connect a wallet to register"}
      </button>
    </section>
  );
}
