/**
 * Did the contract call itself succeed? Decided by the leader's execution and
 * the consensus verdict. A validator that was cancelled after quorum reports
 * `idle`/ERROR and says nothing about the call, so it is not consulted.
 */
export function executionSucceeded(transaction) {
  const receipts = [].concat(transaction?.consensus_data?.leader_receipt ?? []);
  const leader = receipts.find((receipt) => receipt?.mode === "leader");
  return (
    leader?.execution_result === "SUCCESS" &&
    ["AGREE", "MAJORITY_AGREE"].includes(String(transaction?.result_name ?? ""))
  );
}
