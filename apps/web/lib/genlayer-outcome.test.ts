import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { observedExecutionResult } from "./genlayer.ts";

const fixture = JSON.parse(
  readFileSync(new URL("../scripts/fixtures/studio-outcomes.json", import.meta.url), "utf8"),
) as { transactions: Array<{ note: string; result_name: string; leader_receipt: unknown[]; expect_success: boolean }> };

describe("browser execution outcome on real Studio transactions", () => {
  for (const row of fixture.transactions) {
    it(row.note, () => {
      const outcome = observedExecutionResult({
        result_name: row.result_name,
        consensus_data: { leader_receipt: row.leader_receipt },
      });
      assert.equal(outcome === "FINISHED_WITH_RETURN", row.expect_success);
    });
  }
});
