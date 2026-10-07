import assert from "node:assert/strict";
import { chromium } from "@playwright/test";
import { decodeFunctionData, fromHex, fromRlp } from "viem";
import { studionet } from "genlayer-js/chains";

import { decodeCalldata } from "./genlayer-calldata.mjs";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3111";
// Same-origin by default so the app's CSP (connect-src 'self') applies unchanged.
const apiOrigin = process.env.PLAYWRIGHT_API_ORIGIN ?? baseURL;
const rpcURL = "https://studio.genlayer.com/api";
const caseId = "a1b2c3d4e5f6";
const account = "0x1111111111111111111111111111111111111111";
const contract = "0xb3c179E52EC98c1114B55CFCB9b3EdFCc5D0d07b";
const pinned = {
  originRepo: "psf/requests",
  originCommit: "1".repeat(40),
  targetRepo: "pallets/werkzeug",
  targetCommit: "2".repeat(40),
  manifestHash: "a".repeat(64),
  evidenceDigest: "case=a1b2c3d4e5f6; revision=0; pinned evidence",
};

function decodeWalletWrite(transaction) {
  const outer = decodeFunctionData({
    abi: studionet.consensusMainContract.abi,
    data: transaction.data,
  });
  assert.equal(outer.functionName, "addTransaction");
  const encodedAppData = outer.args[4];
  const [encodedCall] = fromRlp(encodedAppData);
  return decodeCalldata(fromHex(encodedCall, "bytes"));
}

function report(revision) {
  const manifestHash = revision === 2 ? "f".repeat(64) : pinned.manifestHash;
  const verdict = revision === 2 ? "SHARED_UPSTREAM" : "INDEPENDENT";
  const revisions = revision === 0 ? [] : [
    {
      revision_number: 1, verdict: "INDEPENDENT", confidence: "HIGH", direction: null,
      shared_upstream: null, manifest_hash: pinned.manifestHash,
      tx_hash: `0x${"c".repeat(64)}`, created_at: null, is_current: revision === 1,
    },
    ...(revision === 2 ? [{
      revision_number: 2, verdict, confidence: "MEDIUM", direction: null,
      shared_upstream: "acme/common", manifest_hash: manifestHash,
      tx_hash: `0x${"d".repeat(64)}`, created_at: null, is_current: true,
    }] : []),
  ];
  const current = revisions.at(-1);
  return {
    case: {
      id: caseId, origin_repo: pinned.originRepo, target_repo: pinned.targetRepo,
      origin_commit: pinned.originCommit, target_commit: pinned.targetCommit,
      manifest_hash: manifestHash, current_revision: revision,
      lifecycle: revision === 0 ? "analysis_ready" : revision === 1 ? "resolved" : "challenged",
      chain_backed: revision > 0, chain_status: null,
      pending_tx_hash: null, created_at: null,
    },
    verdict: {
      verdict: current?.verdict ?? "INDEPENDENT", confidence: current?.confidence ?? "HIGH",
      direction: current?.direction ?? null, shared_upstream: current?.shared_upstream ?? null,
      independent_origin_plausibility: "HIGH", summary: {},
      rationale: revision === 2 ? "Accepted challenge revision." : "Analysis preview.",
      revision_number: revision, tx_hash: current?.tx_hash ?? null,
      network: revision > 0 ? "studionet" : null,
    },
    evidence: [], conflicting_evidence: [], alternative_explanations: [], graph: [], revisions,
  };
}

async function useScenario({ page, context, mode = "accepted", chainId = 61999 }) {
  const state = { revision: 0, txs: new Map(), writes: [], prepCalls: 0, challengeId: "challenge-e2e-1" };
  await context.addInitScript(({ accountAddress, chain }) => {
    let connected = false;
    const listeners = new Map();
    const provider = {
      isMetaMask: true,
      selectedAddress: null,
      chainId: `0x${chain.toString(16)}`,
      on(event, callback) {
        const group = listeners.get(event) ?? new Set();
        group.add(callback);
        listeners.set(event, group);
      },
      removeListener(event, callback) { listeners.get(event)?.delete(callback); },
      async request({ method, params = [] }) {
        if (method === "eth_chainId") return provider.chainId;
        if (method === "eth_accounts") return connected ? [accountAddress] : [];
        if (method === "eth_requestAccounts") {
          connected = true;
          provider.selectedAddress = accountAddress;
          for (const callback of listeners.get("accountsChanged") ?? []) callback([accountAddress]);
          return [accountAddress];
        }
        if (method === "eth_sendTransaction") {
          const scenario = window.__forkreasonScenario;
          if (scenario === "wallet_rejected") {
            const error = new Error("User rejected the request");
            error.code = 4001;
            throw error;
          }
          const transaction = params[0];
          window.__forkreasonWrites.push(transaction);
          const txHash = `0x${(window.__forkreasonWrites.length === 1 ? "c" : "d").repeat(64)}`;
          return txHash;
        }
        if (method === "wallet_getPermissions") return [];
        throw new Error(`Unexpected wallet request: ${method}`);
      },
    };
    window.__forkreasonScenario = window.__forkreasonScenario ?? "accepted";
    window.__forkreasonWrites = [];
    Object.defineProperty(window, "ethereum", { configurable: false, value: provider });
  }, { accountAddress: account, chain: chainId });
  await page.addInitScript((scenario) => { window.__forkreasonScenario = scenario; }, mode);
  if (mode === "pending") {
    await context.addInitScript(() => {
      const original = window.setTimeout.bind(window);
      window.setTimeout = (handler, delay, ...args) =>
        original(handler, delay === 3000 ? 1 : delay, ...args);
    });
  }

  await context.route(`${apiOrigin}/api/v1/**`, async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname;
    const respond = (body, status = 200) => route.fulfill({
      status, contentType: "application/json", body: JSON.stringify(body),
    });

    if (method === "GET" && path === `/api/v1/cases/${caseId}`) return respond(report(state.revision));
    if (method === "POST" && path === "/api/v1/chain/submit-preparation") {
      state.prepCalls += 1;
      const values = [pinned.originRepo, pinned.originCommit, pinned.targetRepo,
        pinned.targetCommit, pinned.manifestHash, pinned.evidenceDigest];
      return respond({
        case_id: caseId, revision_number: 0, manifest_hash: pinned.manifestHash,
        evidence_digest: pinned.evidenceDigest,
        chain: { network: "studionet", rpc_url: rpcURL, contract_address: contract },
        write: { contract: "ForkReasonRegistry", method: "submit_case", args: values, requires_wallet_signature: true },
      });
    }
    if (method === "POST" && path === "/api/v1/chain/transactions") {
      const body = request.postDataJSON();
      state.txs.set(body.tx_hash, { ...body, status: "submitted" });
      return respond({ tx_hash: body.tx_hash, case_id: caseId, kind: body.kind, status: "submitted" }, 202);
    }
    if (method === "GET" && path.startsWith("/api/v1/chain/transactions/")) {
      const txHash = path.split("/").at(-1);
      const transaction = state.txs.get(txHash);
      if (!transaction) return respond({ error: { code: "transaction_not_found", message: "missing" } }, 404);
      if (mode === "pending") transaction.status = "consensus_pending";
      else if (mode === "failed") transaction.status = "failed";
      else {
        transaction.status = "accepted";
        state.revision = transaction.kind === "registration" ? 1 : 2;
      }
      return respond({ tx_hash: txHash, case_id: caseId, kind: transaction.kind, status: transaction.status });
    }
    if (method === "POST" && path === `/api/v1/cases/${caseId}/challenge-preparation`) {
      const body = request.postDataJSON();
      return respond({
        challenge_id: state.challengeId, case_id: caseId, base_revision: 1, expected_revision: 2,
        evidence_digest: `CHALLENGE against revision 1: ${body.evidence_summary}`,
        evidence_digest_sha256: "e".repeat(64),
        chain: { network: "studionet", rpc_url: rpcURL, contract_address: contract },
        write: { contract: "ForkReasonRegistry", method: "challenge_case", args: [pinned.manifestHash, 1, body.rationale, `CHALLENGE against revision 1: ${body.evidence_summary}`], requires_wallet_signature: true },
      });
    }
    return respond({ error: { code: "unexpected_mock_api", message: `${method} ${path}` } }, 500);
  });

  await context.route(rpcURL, async (route) => {
    const { id, method } = route.request().postDataJSON();
    let result = null;
    if (method === "eth_getTransactionCount") result = "0x0";
    else if (method === "eth_estimateGas") result = "0x30d40";
    else if (method === "eth_gasPrice") result = "0x1";
    else if (method === "eth_getTransactionByHash") {
      const writes = await page.evaluate(() => window.__forkreasonWrites);
      const hash = route.request().postDataJSON().params?.[0];
      const selected = writes.at(-1);
      const decoded = selected ? decodeWalletWrite(selected) : null;
      const isFailure = mode === "failed";
      const isPending = mode === "pending";
      result = {
        hash, from: account, to: studionet.consensusMainContract.address,
        status: isPending ? "2" : "7", statusName: isPending ? "PROPOSING" : "FINALIZED",
        tx_id: hash, from_address: account,
        to_address: studionet.consensusMainContract.address, recipient: contract,
        txExecutionResult: isFailure ? 2 : 1,
        txExecutionResultName: isFailure ? "FINISHED_WITH_ERROR" : "FINISHED_WITH_RETURN",
        data: { calldata: { readable: decoded ? JSON.stringify(decoded, (_key, value) =>
          typeof value === "bigint" ? Number(value) : value) : "{}" } },
        consensus_data: { validators: [{ result: isFailure ? "AQ==" : "AAA=" }] },
      };
    }
    return route.fulfill({
      status: 200, contentType: "application/json",
      headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*" },
      body: JSON.stringify({ jsonrpc: "2.0", id, result }),
    });
  });
  return state;
}

async function connectWallet(page, connectedLabel = /sign and register/i) {
  const panel = page.locator(".registration-panel");
  await panel.getByRole("button", { name: /^connect wallet$/i }).click();
  const dialog = page.getByRole("dialog");
  await dialog.waitFor({ state: "visible" });
  await dialog.getByRole("button", { name: /browser wallet/i }).click();
  await panel.getByRole("button", { name: connectedLabel }).waitFor({ state: "visible" });
}

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") console.error("browser console:", message.text());
  });
  page.on("pageerror", (error) => console.error("browser page error:", error.message));
  const success = await useScenario({ page, context });
  await page.goto(`${baseURL}/case/${caseId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Register this analysis on GenLayer" }).waitFor();
  const registration = page.locator(".registration-panel");
  assert.equal(await registration.getByRole("button", { name: /connect a wallet/i }).isDisabled(), true);
  assert.equal(success.prepCalls, 0, "disconnected visitor must not prepare a transaction");

  await connectWallet(page);
  await registration.getByRole("button", { name: /sign and register/i }).click();
  await page.getByText("Case report · revision 1").waitFor({ timeout: 10000 });
  const initialWrites = await page.evaluate(() => window.__forkreasonWrites);
  assert.equal(initialWrites.length, 1, "initial registration must send exactly one wallet transaction");
  const initialCall = decodeWalletWrite(initialWrites[0]);
  assert.equal(initialCall.method, "submit_case");
  assert.deepEqual(initialCall.args, [pinned.originRepo, pinned.originCommit, pinned.targetRepo,
    pinned.targetCommit, pinned.manifestHash, pinned.evidenceDigest]);

  await page.getByRole("link", { name: "Challenge this finding" }).first().click();
  await page.locator("#challenge-rationale").fill("A shared ancestor explains the matching implementation.");
  await page.locator("#challenge-evidence").fill("Both projects identify acme/common in pinned history.");
  await page.getByRole("button", { name: "Prepare challenge" }).click();
  await page.getByRole("button", { name: "Sign with your wallet" }).waitFor();
  await page.getByRole("button", { name: "Sign with your wallet" }).click();
  await page.getByRole("link", { name: "Return to the case" }).waitFor({ timeout: 10000 });
  const writes = await page.evaluate(() => window.__forkreasonWrites);
  assert.equal(writes.length, 2, "challenge should add exactly one signed wallet transaction");
  const challengeCall = decodeWalletWrite(writes[1]);
  assert.equal(challengeCall.method, "challenge_case");
  assert.equal(challengeCall.args[0], pinned.manifestHash);
  assert.equal(challengeCall.args[1], 1n);
  assert.equal(challengeCall.args[2], "A shared ancestor explains the matching implementation.");

  await page.getByRole("link", { name: "Return to the case" }).click();
  await page.getByText("Case report · revision 2").waitFor({ timeout: 10000 });
  await page.getByRole("heading", { name: "Revision history" }).scrollIntoViewIfNeeded();
  await page.getByText("rev 1", { exact: true }).waitFor();
  await page.getByText("rev 2", { exact: true }).waitFor();
  assert.equal(await page.locator('.revision-item[data-current="false"] .revision-number').textContent(), "rev 1");
  console.log("PASS registration six-argument browser write, wallet gating, challenge write, and public Case revisions 1→2");
  await context.close();

  for (const scenario of ["wallet_rejected", "wrong_network", "failed", "pending"]) {
    const scenarioContext = await browser.newContext();
    const scenarioPage = await scenarioContext.newPage();
    const chain = scenario === "wrong_network" ? 1 : 61999;
    const state = await useScenario({ page: scenarioPage, context: scenarioContext,
      mode: scenario, chainId: chain });
    await scenarioPage.goto(`${baseURL}/case/${caseId}`, { waitUntil: "domcontentloaded" });
    const panel = scenarioPage.locator(".registration-panel");
    if (scenario === "wrong_network") {
      await connectWallet(scenarioPage, /switch wallet to studionet/i);
      assert.equal(await panel.getByRole("button", { name: /switch wallet to studionet/i }).isDisabled(), true);
      assert.equal(state.prepCalls, 0, "wrong network must be rejected before preparing a write");
    } else {
      await connectWallet(scenarioPage);
      await panel.getByRole("button", { name: /sign and register/i }).click();
      if (scenario === "wallet_rejected") {
        await scenarioPage.getByRole("alert").filter({ hasText: /rejected|nothing was sent/i }).waitFor();
        assert.equal((await scenarioPage.evaluate(() => window.__forkreasonWrites)).length, 0);
        assert.equal(state.txs.size, 0);
      } else if (scenario === "failed") {
        await scenarioPage.getByRole("alert").filter({
          hasText: /finalized this transaction without accepting|contract error|could not be verified/i,
        }).waitFor({ timeout: 10000 });
        assert.equal(state.revision, 0, "failed execution cannot publish a Case revision");
      } else {
        await scenarioPage.getByText("Consensus is still pending. ForkReason will keep following this transaction.").waitFor({ timeout: 10000 });
        assert.equal(state.revision, 0, "pending consensus cannot publish a Case revision");
      }
    }
    await scenarioContext.close();
    console.log(`PASS ${scenario}`);
  }

  const missingContext = await browser.newContext();
  const missingPage = await missingContext.newPage();
  await missingContext.route(`${apiOrigin}/api/v1/analyses/missing-e2e`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "job_not_found", message: "That analysis does not exist." } }),
    }),
  );
  await missingPage.goto(`${baseURL}/analysis/missing-e2e`, { waitUntil: "domcontentloaded" });
  await missingPage.getByRole("status").filter({ hasText: "That analysis does not exist." }).waitFor();
  assert.equal(await missingPage.locator(".skeleton-line").count(), 0);
  await missingPage.getByText("Analysis unavailable", { exact: true }).waitFor();
  await missingContext.close();
  console.log("PASS missing analysis deep link exits loading state");
} finally {
  await browser.close();
}
