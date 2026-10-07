import { createClient } from "genlayer-js";
import { localnet, studionet, testnetAsimov, testnetBradbury } from "genlayer-js/chains";
import { TransactionHashVariant } from "genlayer-js/types";

import { decodeCall } from "./genlayer-calldata.mjs";

const input = JSON.parse(await new Promise((resolve, reject) => {
  let data = "";
  process.stdin.setEncoding("utf8").on("data", (chunk) => (data += chunk));
  process.stdin.on("end", () => resolve(data));
  process.stdin.on("error", reject);
}));
const chains = {
  studionet,
  localnet,
  testnet_asimov: testnetAsimov,
  testnet_bradbury: testnetBradbury,
};
const chain = chains[input.network];
if (!chain || !/^0x[0-9a-f]{64}$/i.test(input.tx_id) || !/^0x[0-9a-f]{40}$/i.test(input.contract)) {
  throw new Error("invalid GenLayer inspection parameters");
}
const client = createClient({ chain, endpoint: input.rpc_url });
let transaction;
try {
  transaction = await client.getTransaction({ hash: input.tx_id });
} catch (error) {
  const message = String(error?.details ?? error?.message ?? error).slice(0, 200);
  process.stdout.write(JSON.stringify({ error: { message, rate_limited: /rate limit/i.test(message) } }));
  process.exit(0);
}
if (!transaction) {
  process.stdout.write(JSON.stringify({ transaction: { tx_id: input.tx_id, status: "NOT_FOUND" } }));
  process.exit(0);
}

// The binary calldata is authoritative; the node's `readable` text is not valid JSON.
const call = typeof transaction.data?.calldata?.base64 === "string"
  ? decodeCall(transaction.data.calldata.base64)
  : null;
const receipts = [
  ...(transaction.consensus_data?.validators ?? []),
  ...(Array.isArray(transaction.consensus_data?.leader_receipt)
    ? transaction.consensus_data.leader_receipt
    : transaction.consensus_data?.leader_receipt
      ? [transaction.consensus_data.leader_receipt]
      : []),
];
const results = receipts.map((receipt) => receipt.result).filter((value) => typeof value === "string");
const executionSuccess =
  typeof transaction.txExecutionResultName === "string"
    ? transaction.txExecutionResultName === "FINISHED_WITH_RETURN"
    : results.length > 0 && results.every((value) => {
        try { return atob(value).charCodeAt(0) === 0; } catch { return false; }
      });
const tx = {
  tx_id: transaction.tx_id ?? transaction.hash,
  status: transaction.statusName ?? transaction.status_name ?? "UNKNOWN",
  execution_success: executionSuccess,
  to: transaction.recipient ?? transaction.to_address ?? transaction.to,
  from: transaction.from_address ?? transaction.sender,
  call,
};

const readErrors = [];
async function read(functionName, args = []) {
  try {
    return await client.readContract({
      address: input.contract,
      functionName,
      args,
      transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
      jsonSafeReturn: true,
    });
  } catch (error) {
    readErrors.push(String(error?.details ?? error?.message ?? error).slice(0, 160));
    return null;
  }
}

// Contract reads are metered by the RPC (Studio allows 500 gen_call per hour),
// and there is nothing to verify until consensus has accepted a successful
// execution, so earlier polls stay at the transaction lookup.
const settled = (tx.status === "ACCEPTED" || tx.status === "FINALIZED") && tx.execution_success;
const [chainCase, revision, challenge] = settled
  ? await Promise.all([
      read("get_case", [input.chain_case_id]),
      read("get_revision", [input.chain_case_id, input.revision_number]),
      input.revision_number > 1
        ? read("get_challenge", [`${input.chain_case_id}#${input.revision_number}`])
        : Promise.resolve(null),
    ])
  : [null, null, null];
process.stdout.write(JSON.stringify({
  transaction: tx, case: chainCase, revision, challenge, read_errors: readErrors,
}));
