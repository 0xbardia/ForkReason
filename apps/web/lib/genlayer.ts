/**
 * GenLayer chain access.
 *
 * Design constraints that come straight from the constitution and spec:
 *
 *  * READS use an account-free client. No wallet, no prompt, no signature.
 *  * WRITES are signed by the user's browser wallet. There is no server key
 *    and no `PRIVATE_KEY` anywhere in this file or in the repository.
 *  * A "decided" GenLayer transaction is not a successful one. `ACCEPTED` means
 *    the committee agreed on the receipt, so `ExecutionResult` must also be
 *    checked before the UI claims success.
 *  * `writeContract` returns the GenLayer transaction id, not the EVM hash.
 *    That id is what the receipt API consumes and what we record.
 *
 * API notes (verified against genlayer-js 1.1.8): see
 * `docs/GENLAYER-DAPP-VERIFIED.md`.
 */

import { createClient } from "genlayer-js";
import { localnet, studionet, testnetAsimov, testnetBradbury } from "genlayer-js/chains";
import {
  ExecutionResult,
  TransactionHashVariant,
  TransactionStatus,
} from "genlayer-js/types";
/**
 * The chain type is inferred from the values themselves rather than
 * re-declared. `genlayer-js/chains` does not export its chain type, and a
 * hand-written approximation drifts from the real shape (the contract fields
 * are objects with abi/bytecode, not bare addresses).
 */
type GenLayerChain = (typeof studionet);

export type GenLayerNetwork = "studionet" | "localnet" | "testnet_bradbury" | "testnet_asimov";

const CHAINS: Record<GenLayerNetwork, GenLayerChain> = {
  studionet,
  localnet,
  testnet_bradbury: testnetBradbury,
  testnet_asimov: testnetAsimov,
};

export function resolveChain(network: string | undefined): GenLayerChain {
  const key = (network ?? "studionet") as GenLayerNetwork;
  return CHAINS[key] ?? studionet;
}

export function isSupportedNetwork(network: number | undefined): boolean {
  return Object.values(CHAINS).some((chain) => chain.id === network);
}

export function chainForNetwork(network: string | undefined) {
  return resolveChain(network);
}

export function rpcForNetwork(network: string | undefined): string {
  return (
    process.env.NEXT_PUBLIC_GENLAYER_RPC_URL?.replace(/\/$/, "") ??
    resolveChain(network).rpcUrls.default.http[0] ??
    "https://studio.genlayer.com/api"
  );
}

export function contractAddress(): `0x${string}` | null {
  const value = process.env.NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS?.trim();
  if (!value) return null;
  if (!/^0x[0-9a-fA-F]{40}$/.test(value)) {
    // Misconfiguration must be visible, but never crash a page render.
    if (process.env.NODE_ENV !== "production") {
      console.warn(
        "NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS is set but is not a 20-byte hex address; ignoring it.",
      );
    }
    return null;
  }
  return value as `0x${string}`;
}

// --- reads (no wallet) ----------------------------------------------------

export function readClient(network: string | undefined) {
  return createClient({
    chain: resolveChain(network),
    endpoint: rpcForNetwork(network),
  });
}

export interface ChainReadResult {
  ok: boolean;
  value?: unknown;
  error?: string;
}

/** Account-free view call. Never prompts the wallet. */
export async function callView(
  functionName: string,
  args: unknown[] = [],
  network?: string,
  address?: `0x${string}`,
): Promise<ChainReadResult> {
  const target = address ?? contractAddress();
  if (!target) {
    return { ok: false, error: "No ForkReason contract address is configured." };
  }
  try {
    const client = readClient(network);
    const value = await client.readContract({
      address: target,
      functionName,
      args: args as never[],
      // Finalized state only: a read that can see an undecided write would
      // report a value the chain has not committed to.
      transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
      jsonSafeReturn: true,
    });
    return { ok: true, value };
  } catch (error) {
    return { ok: false, error: readableChainError(error) };
  }
}

export async function getCaseCount(network?: string): Promise<number | null> {
  const result = await callView("get_case_count", [], network);
  if (!result.ok) return null;
  const value = result.value;
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "number") return value;
  return null;
}

// --- writes (user wallet only) -------------------------------------------

export type TxPhase =
  | "idle"
  | "preparing"
  | "awaiting_signature"
  | "submitted"
  | "awaiting_decision"
  | "finalizing"
  | "accepted"
  | "failed"
  | "undetermined";

export interface WriteResult {
  ok: boolean;
  phase: TxPhase;
  txId?: string;
  statusName?: string;
  executionResult?: string;
  message?: string;
}

/**
 * Submit a contract write signed by the user's wallet.
 *
 * `provider` must be an EIP-1193 provider from the connected wallet. The
 * address is passed as `account`; genlayer-js then calls `eth_sendTransaction`,
 * which is what raises the wallet prompt. There is no local-signing path here
 * on purpose: a local signer would mean a key in the browser.
 */
export async function writeContract(
  params: {
    functionName: string;
    args: unknown[];
    account: `0x${string}`;
    provider: unknown;
    network?: string;
  },
  onPhase?: (phase: TxPhase) => void,
): Promise<WriteResult> {
  const target = contractAddress();
  if (!target) {
    return {
      ok: false,
      phase: "failed",
      message: "ForkReason's GenLayer contract is not configured on this deployment.",
    };
  }
  if (!params.account) {
    return { ok: false, phase: "failed", message: "No wallet address is connected." };
  }

  let txId: string;
  try {
    onPhase?.("awaiting_signature");
    const client = createClient({
      chain: resolveChain(params.network),
      endpoint: rpcForNetwork(params.network),
      account: params.account,
      provider: params.provider as never,
    });

    onPhase?.("submitted");
    // 1.1.8 requires `value`, and returns the GenLayer transaction id.
    txId = (await client.writeContract({
      address: target,
      functionName: params.functionName,
      args: params.args as never[],
      value: BigInt(0),
    })) as string;
  } catch (error) {
    return { ok: false, phase: "failed", message: readableChainError(error) };
  }

  try {
    onPhase?.("awaiting_decision");
    const client = readClient(params.network);
    const receipt = await client.waitForTransactionReceipt({
      hash: txId as never,
      status: TransactionStatus.ACCEPTED,
      interval: 3000,
      retries: 40,
    });

    const statusName =
      (receipt as { statusName?: string }).statusName ?? "UNKNOWN";
    const executionResult =
      (receipt as { txExecutionResultName?: string }).txExecutionResultName ??
      ExecutionResult.NOT_VOTED;

    // A decided transaction can still have failed. Check both.
    if (executionResult !== ExecutionResult.FINISHED_WITH_RETURN) {
      return {
        ok: false,
        phase: "failed",
        txId,
        statusName,
        executionResult,
        message:
          executionResult === ExecutionResult.FINISHED_WITH_ERROR
            ? "The transaction was decided but the contract reverted, so no state changed."
            : "The transaction was decided but the contract did not complete successfully.",
      };
    }

    if (statusName === TransactionStatus.UNDETERMINED) {
      onPhase?.("undetermined");
      return {
        ok: false,
        phase: "undetermined",
        txId,
        statusName,
        executionResult,
        message:
          "Validators did not reach a decision. The case can be appealed on GenLayer.",
      };
    }

    onPhase?.("accepted");
    return { ok: true, phase: "accepted", txId, statusName, executionResult };
  } catch (error) {
    return {
      ok: false,
      phase: "failed",
      txId,
      message: readableChainError(error),
    };
  }
}

export async function transactionStatus(
  txId: string,
  network?: string,
): Promise<{ statusName: string; executionResult: string } | null> {
  try {
    const client = readClient(network);
    const tx = await client.getTransaction({ hash: txId as never });
    return {
      statusName: (tx as { statusName?: string }).statusName ?? "UNKNOWN",
      executionResult:
        (tx as { txExecutionResultName?: string }).txExecutionResultName ??
        ExecutionResult.NOT_VOTED,
    };
  } catch {
    return null;
  }
}

// --- errors ---------------------------------------------------------------

/**
 * Turn a chain error into something a user can act on.
 *
 * The raw message can contain RPC internals; only recognised shapes are
 * surfaced, and anything else is replaced with a generic message rather than
 * leaking a stack or an internal URL.
 */
export function readableChainError(error: unknown): string {
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "";

  const lower = raw.toLowerCase();

  if (lower.includes("user rejected") || lower.includes("user denied")) {
    return "You rejected the transaction in your wallet. Nothing was signed or sent.";
  }
  if (lower.includes("user refused") || lower.includes("cancelled by user")) {
    return "You cancelled the transaction in your wallet.";
  }
  if (lower.includes("unauthorized") || lower.includes("signature")) {
    return "Your wallet could not sign this transaction. Check that the account is unlocked.";
  }
  if (lower.includes("unsupported chain") || lower.includes("chain mismatch")) {
    return "Your wallet is on a different network. Switch to the configured GenLayer network and retry.";
  }
  if (lower.includes("insufficient funds")) {
    return "This wallet does not have enough GEN to cover the transaction fee.";
  }
  if (lower.includes("nonce")) {
    return "The wallet reported a nonce conflict. Wait a moment and retry.";
  }
  if (lower.includes("already known") || lower.includes("replacement")) {
    return "A transaction with the same nonce is already in flight.";
  }
  if (lower.includes("fetch failed") || lower.includes("network")) {
    return "Could not reach the GenLayer network. Check your connection and retry.";
  }
  if (lower.includes("execution reverted") || lower.includes("reverted")) {
    return "The contract rejected this transaction. The case may already be recorded, or the revision may be stale.";
  }

  return "The GenLayer network did not accept this transaction. No state was changed.";
}

/** Human labels for the real lifecycle, used by the consensus timeline. */
export const STATUS_LABELS: Record<string, string> = {
  UNINITIALIZED: "Preparing",
  PENDING: "Submitted",
  PROPOSING: "Validators proposing",
  COMMITTING: "Validators committing",
  REVEALING: "Validators revealing",
  ACCEPTED: "Decision reached",
  UNDETERMINED: "Undetermined",
  FINALIZED: "Finalized",
  CANCELED: "Canceled",
  APPEAL_REVEALING: "Appeal revealing",
  APPEAL_COMMITTING: "Appeal committing",
  READY_TO_FINALIZE: "Ready to finalize",
  VALIDATORS_TIMEOUT: "Validators timed out",
  LEADER_TIMEOUT: "Leader timed out",
  LEADER_REVEALING: "Leader revealing",
};

export function statusLabel(statusName: string | undefined): string {
  if (!statusName) return "Unknown";
  return STATUS_LABELS[statusName] ?? statusName;
}