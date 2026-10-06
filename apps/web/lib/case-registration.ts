import type { CaseReport, SubmitCaseArgs, SubmitCasePreparation } from "@/lib/api";

const HASH = /^[0-9a-f]{1,128}$/i;
const COMMIT = /^[0-9a-f]{1,64}$/i;

/** Validate the API payload against the selected analyzed Case before writing. */
export function buildSubmitCaseArgs(
  report: CaseReport,
  preparation: SubmitCasePreparation,
): SubmitCaseArgs {
  const meta = report.case;
  const { args } = preparation.write;
  if (
    meta.current_revision !== 0 || preparation.revision_number !== 0 ||
    preparation.case_id !== meta.id || preparation.manifest_hash !== meta.manifest_hash ||
    args.length !== 6 || args[0] !== meta.origin_repo || args[1] !== meta.origin_commit ||
    args[2] !== meta.target_repo || args[3] !== meta.target_commit ||
    args[4] !== meta.manifest_hash || args[5] !== preparation.evidence_digest
  ) {
    throw new Error("Registration payload does not match this analyzed case.");
  }
  if (
    !args[0] || args[0].length > 240 || !args[2] || args[2].length > 240 ||
    !COMMIT.test(args[1]) || !COMMIT.test(args[3]) || !HASH.test(args[4]) ||
    !args[5] || args[5].length > 6000 ||
    (args[0] === args[2] && args[1] === args[3])
  ) {
    throw new Error("Registration payload contains invalid contract arguments.");
  }
  if (preparation.write.method !== "submit_case" || preparation.write.contract !== "ForkReasonRegistry") {
    throw new Error("The prepared write is not a ForkReasonRegistry registration.");
  }
  return [...args] as SubmitCaseArgs;
}
