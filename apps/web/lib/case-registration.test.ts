import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { CaseReport, SubmitCasePreparation } from "./api.ts";
import { buildSubmitCaseArgs } from "./case-registration.ts";

const report = {
  case: {
    id: "a".repeat(24), origin_repo: "psf/requests", origin_commit: "1".repeat(40),
    target_repo: "pallets/werkzeug", target_commit: "2".repeat(40),
    manifest_hash: "3".repeat(64), current_revision: 0, lifecycle: "analysis_ready",
    chain_backed: false, created_at: null,
  },
} as CaseReport;
const preparation = {
  case_id: report.case.id, revision_number: 0, manifest_hash: report.case.manifest_hash,
  evidence_digest: "pinned evidence", chain: { network: "studionet", rpc_url: "", contract_address: "0x" + "a".repeat(40) },
  write: {
    contract: "ForkReasonRegistry", method: "submit_case",
    args: [report.case.origin_repo, report.case.origin_commit, report.case.target_repo,
      report.case.target_commit, report.case.manifest_hash, "pinned evidence"],
    requires_wallet_signature: true,
  },
} as SubmitCasePreparation;

describe("submit_case argument mapping", () => {
  it("returns the six ABI arguments in contract order from this analyzed case", () => {
    assert.deepEqual(buildSubmitCaseArgs(report, preparation), [
      "psf/requests", "1".repeat(40), "pallets/werkzeug", "2".repeat(40),
      "3".repeat(64), "pinned evidence",
    ]);
  });

  it("rejects missing or reordered required case identity", () => {
    const reordered = {
      ...preparation,
      write: { ...preparation.write, args: [...preparation.write.args].reverse() },
    } as SubmitCasePreparation;
    assert.throws(() => buildSubmitCaseArgs(report, reordered), /does not match/);
  });

  it("rejects malformed hashes and an analysis from another Case", () => {
    const malformed = {
      ...preparation,
      write: { ...preparation.write, args: [...preparation.write.args.slice(0, 4), "not-hex", preparation.evidence_digest] },
    } as SubmitCasePreparation;
    assert.throws(() => buildSubmitCaseArgs(report, malformed), /does not match/);
    assert.throws(() => buildSubmitCaseArgs({ ...report, case: { ...report.case, id: "b".repeat(24) } }, preparation), /does not match/);
  });
});
