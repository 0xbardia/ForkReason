import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { executionSucceeded } from "./genlayer-outcome.mjs";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/studio-outcomes.json", import.meta.url), "utf8"));
const asTransaction = (row) => ({ result_name: row.result_name, consensus_data: { leader_receipt: row.leader_receipt } });

describe("execution outcome of real Studio transactions", () => {
  for (const row of fixture.transactions) {
    it(`${row.note}`, () => {
      assert.equal(executionSucceeded(asTransaction(row)), row.expect_success);
    });
  }

  it("is false without a leader receipt or a consensus verdict", () => {
    assert.equal(executionSucceeded({}), false);
    assert.equal(executionSucceeded({ result_name: "MAJORITY_AGREE", consensus_data: { leader_receipt: [] } }), false);
    assert.equal(executionSucceeded({ result_name: "TIMEOUT", consensus_data: { leader_receipt: [{ mode: "leader", execution_result: "SUCCESS" }] } }), false);
  });
});
