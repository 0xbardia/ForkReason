import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { decodeCall } from "./genlayer-calldata.mjs";

const real = JSON.parse(readFileSync(new URL("./fixtures/studio-submit-case-tx.json", import.meta.url), "utf8"));

describe("GenLayer calldata decoding against a real Studio transaction", () => {
  it("the node's readable form is not JSON, which is why the binary form is decoded", () => {
    assert.throws(() => JSON.parse(real.calldata_readable));
  });

  it("recovers submit_case and all six arguments, in contract order", () => {
    const call = decodeCall(real.calldata_base64);
    assert.equal(call.method, "submit_case");
    assert.equal(call.args.length, 6);
    const [originRepo, originCommit, targetRepo, targetCommit, manifestHash, evidenceDigest] = call.args;
    assert.equal(originRepo, "psf/requests");
    assert.match(originCommit, /^[0-9a-f]{40}$/);
    assert.equal(targetRepo, "pallets/werkzeug");
    assert.match(targetCommit, /^[0-9a-f]{40}$/);
    assert.match(manifestHash, /^[0-9a-f]{64}$/);
    assert.match(evidenceDigest, /^case: [0-9a-f]+\nrevision: 0\n/);
  });

  it("returns null for malformed calldata instead of guessing", () => {
    assert.equal(decodeCall(""), null);
    assert.equal(decodeCall("AAAA"), null);
    assert.equal(decodeCall(real.calldata_base64.slice(0, 40)), null);
  });
});
