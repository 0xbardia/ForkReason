# GenLayer dApp Technical Reference (READ + WRITE from Next.js/React)

Verified against the **published npm tarballs** (`dist/*.d.ts` + runtime bundles), not just docs prose.
Retrieved: 2026-10-03. Source of truth: `registry.npmjs.org` + `unpkg.com/genlayer-js@<v>/dist/*`.

---

## 0. READ THIS FIRST — three traps that will waste your day

### Trap 1: `latest` (1.1.8) ≠ the API the docs describe
The docs at docs.genlayer.com use `waitForFinalization`, `isSuccessful`, `estimateTransactionFeesForWrite`,
and `waitUntil: 'decided' | 'finalized'`. **None of these exist in the `latest` tag.**

Verified by grepping the published `.d.ts` and runtime JS of `genlayer-js@1.1.8`:

| Symbol | 1.1.8 (`latest`) | 2.0.0-rc.1 (`rc`) |
|---|---|---|
| `waitForFinalization` | ABSENT | present |
| `waitForDecision` | ABSENT | present |
| `waitUntil: 'decided'\|'finalized'` | ABSENT | present |
| `isSuccessful` | ABSENT | present (runtime export) |
| `estimateTransactionFeesForWrite` | ABSENT | present |
| `writeContract({ fees })` | ABSENT | present |
| `writeContract({ value })` | **required** `bigint` | **optional** |
| `transfer()` | ABSENT | present |
| `advanced.getTransactionLifecycle` | ABSENT | present |
| `studioDevnet` chain | ABSENT | present |

`npm install genlayer-js` gives you **1.1.8**. To get the documented API you must pin explicitly:

```bash
npm install genlayer-js@2.0.0-rc.1   # documented API, RELEASE CANDIDATE — may break
npm install genlayer-js@1.1.8        # stable, older API (use the 1.1.8 section below)
```

Also note: **`1.2.0` exists but is NOT `latest`** (published 2026-04-23, older than 1.1.8's 2026-05-06).
It is not on the `latest` line. Don't `npm i genlayer-js@^1` expecting 1.2.0 to be current.

### Trap 2: RainbowKit 2.2.11 CANNOT use wagmi 3.x
`@rainbow-me/rainbowkit@2.2.11` declares `"wagmi": "^2.9.0"` as a peer dependency, but
`npm install wagmi` resolves to **3.7.7**. That is an unsatisfiable peer dep — the build breaks.

**Pin wagmi to 2.x explicitly:**

```bash
npm install wagmi@2 viem@2 @rainbow-me/rainbowkit@2 @tanstack/react-query@5
```
`wagmi@2` → resolves to **2.19.5** (latest 2.x). `viem@2` → **2.57.2**.
wagmi 3 additionally requires `typescript >=5.9.3` (2.x only needs `>=5.0.4`).

### Trap 3: GenLayer transactions are NOT EVM transactions
A GenLayer tx hash is **not** an Ethereum tx hash. `writeContract()` submits an *EVM* tx to the
consensus-main contract and then **scrapes the GenLayer tx id out of the receipt logs**
(`NewTransaction` / `CreatedTransaction` event `txId`). That GenLayer id — not the EVM hash — is what
`waitForTransactionReceipt` / `getTransaction` consume. Return it to the UI, not the EVM hash.

---

## 1. Exact versions

| Package | Version | Notes |
|---|---|---|
| `genlayer-js` | **1.1.8** (`latest`) | stable line; published 2026-05-06 |
| `genlayer-js` | **2.0.0-rc.1** (`rc`) | matches current docs; **not** `latest` |
| `@rainbow-me/rainbowkit` | **2.2.11** | peer: `wagmi ^2.9.0`, `viem 2.x`, `react >=18`, `@tanstack/react-query >=5` |
| `wagmi` | **2.19.5** (use this) | `latest` is 3.7.7 — incompatible with RainbowKit 2.2.11 |
| `viem` | **2.57.2** | `genlayer-js` depends on `viem ^2.29.0` |
| `react` | **19.3.0** | RainbowKit peer is `>=18`; OK |
| `@tanstack/react-query` | **5.104.1** | peer `react ^18 \|\| ^19` — OK |

**React 19 compatibility:** supported. RainbowKit raised its floor to React 19 / wagmi `^2.14.7`
in commit `f533ac2` ("chore: react 19, next 15 support"); `@tanstack/react-query@5` peers
`^18 || ^19`. No `--legacy-peer-deps` needed as long as wagmi stays on 2.x.

**Known runtime caveat (unverified claim, flagged):** RainbowKit bundles `WalletConnect`, which has
historically used Node polyfills under webpack/Next bundlers. If you hit `Buffer`/`process` errors,
fall back to `transports: { [chainId]: http(rpcUrl) }` (which is what you want on GenLayer anyway —
there is no WalletConnect chain metadata for a GenLayer chain id).

---

## 2. Networks / chains / RPC URLs

Import from the subpath `'genlayer-js/chains'`.

### genlayer-js 1.1.8 (4 chains, verbatim from the bundle)

| Export | chainId | RPC URL | `isStudio` | Explorer |
|---|---|---|---|---|
| `localnet` | **61127** | `http://127.0.0.1:4000/api` | `true` | same as RPC |
| `studionet` | **61999** | `https://studio.genlayer.com/api` | `true` | `https://genlayer-explorer.vercel.app` |
| `testnetAsimov` | **4221** | `https://rpc-asimov.genlayer.com` | `false` | `https://explorer-asimov.genlayer.com/` |
| `testnetBradbury` | **4221** | `https://rpc-bradbury.genlayer.com` | `false` | `https://explorer-bradbury.genlayer.com/` |

All four: `nativeCurrency { name: "GEN Token", symbol: "GEN", decimals: 18 }`,
`defaultNumberOfInitialValidators: 5`, `defaultConsensusMaxRotations: 3`, `testnet: true`.

⚠️ **Asimov and Bradbury share chainId 4221.** They are mutually exclusive in any wallet/EIP-3325
switching flow. Pick one per deployment.

⚠️ **There is no mainnet chain export.** `localnet`/`studionet` are `isStudio: true` (Studio-mode RPC,
different tx encoding + an `ACTIVATED`→`PENDING` status remap). `testnetBradbury` is `isStudio: false`
and reads state through the consensus-data contract instead.

2.0.0-rc.1 adds a fifth: `studioDevnet`.

### Chain config object (`GenLayerChain`)

`defineChain` from viem, extended with GenLayer fields. RPC URL override is via the top-level
`endpoint` option, **not** by mutating the chain:

```ts
interface ClientConfig {
  chain?: { id: number; name: string; rpcUrls: { default: { http: readonly string[] } };
            nativeCurrency: { name: string; symbol: string; decimals: number };
            blockExplorers?: { default: { name: string; url: string } } };
  endpoint?: string;              // <- custom RPC override
  account?: Account | Address;    // <- signer
  provider?: EthereumProvider;    // <- window.ethereum
}
```
Extra fields on the chain: `isStudio`, `consensusMainContract`, `consensusDataContract`,
`stakingContract`, `feeManagerContract`, `roundsStorageContract`, `appealsContract`,
`defaultNumberOfInitialValidators`, `defaultConsensusMaxRotations`.

---

## 3. Reading (view calls) — no wallet needed

Read client talks straight to GenLayer RPC. Free, no signature, no popup.

```ts
import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";

export const readClient = createClient({ chain: testnetBradbury });

export async function getStorage(address: `0x${string}`) {
  return readClient.readContract({
    address,                       // deployed IC address
    functionName: "get_complete_storage",
    args: [],
  });
}
```

Signature (1.1.8, verbatim from `dist/index-C3Ul1Rte.d.ts`):

```ts
readContract: <RawReturn extends boolean | undefined>(args: {
  account?: Account;              // optional; falls back to client.account, then zeroAddress
  address: Address;
  functionName: string;
  args?: CalldataEncodable[];
  kwargs?: Map<string, CalldataEncodable> | { [key: string]: CalldataEncodable };
  rawReturn?: RawReturn;
  jsonSafeReturn?: boolean;
  transactionHashVariant?: TransactionHashVariant;
}) => Promise<RawReturn extends true ? `0x${string}` : CalldataEncodable>
```

Behaviour verified in the 1.1.8 runtime bundle:
- `jsonSafeReturn` **defaults to `true`** → returns BigInt-safe, JSON-round-trippable values.
- `transactionHashVariant` **defaults to `"latest-nonfinal"`** (`TransactionHashVariant.LATEST_NONFINAL`).
  Use `"latest-final"` to read against finalized state only — the safe choice after a write.
- Transport is the custom RPC `gen_call` with `type: "read"`; **not** `eth_call`.
- `simulateWriteContract()` is the write-path dry run (same encoding, no state change).

⚠️ The docs example passes `stateStatus: "accepted"` to `readContract` — **that option does not exist**
in 1.1.8 nor in 2.0.0-rc.1 (grep-verified absent in both). The real control is `transactionHashVariant`.
Ignore that doc snippet.

---

## 4. Writing + the consensus lifecycle

### 4a. With 1.1.8 (stable / `latest`)

```ts
import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { TransactionStatus, ExecutionResult } from "genlayer-js/types";

const writeClient = createClient({
  chain: testnetBradbury,
  account: walletAddress as `0x${string}`,   // from wagmi useAccount()
  provider: window.ethereum,
});

const txId = await writeClient.writeContract({
  address: contractAddress,
  functionName: "update_storage",
  args: ["new_value"],
  value: BigInt(0),        // REQUIRED in 1.1.8
});

const receipt = await writeClient.waitForTransactionReceipt({
  hash: txId,
  status: TransactionStatus.FINALIZED,   // or ACCEPTED
  fullTransaction: false,               // runtime-supported; MISSING from 1.1.8 .d.ts
});

if (receipt.txExecutionResultName === ExecutionResult.FINISHED_WITH_RETURN) {
  // contract returned successfully
} else if (receipt.txExecutionResultName === ExecutionResult.FINISHED_WITH_ERROR) {
  // execution failed — state NOT modified
} else {
  // NOT_VOTED — not yet complete
}
```

1.1.8 signatures (verbatim):

```ts
writeContract: (args: {
  account?: Account; address: Address; functionName: string;
  args?: CalldataEncodable[];
  kwargs?: Map<string, CalldataEncodable> | { [key: string]: CalldataEncodable };
  value: bigint;                        // <-- REQUIRED
  leaderOnly?: boolean;
  consensusMaxRotations?: number;       // defaults to chain.defaultConsensusMaxRotations (3)
}) => Promise<any>                      // returns the GENLAYER tx id, not the EVM hash

waitForTransactionReceipt: (args: {
  hash: TransactionHash;
  status?: TransactionStatus;           // default "ACCEPTED"
  interval?: number;                    // default 3000 ms
  retries?: number;                     // default 10  -> ~30 s max
  fullTransaction?: boolean;            // default false
}) => Promise<GenLayerTransaction>
```

There is **no** `sendTransaction`, `getTxHash`, `pollForTransactionReceipt`, or `tx()` in genlayer-js.
The lifecycle method names are exactly: `writeContract` → (returns hash) →
`getTransaction` / `waitForTransactionReceipt`. `sim_fundAccount` is the only viem-style send that
exists, and it's localnet-only.

### 4b. With 2.0.0-rc.1 (the documented API)

```ts
import { createClient, isSuccessful } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";

const client = createClient({ chain: testnetBradbury, account: walletAddress as `0x${string}`, provider: window.ethereum });

const write = { address: contractAddress, functionName: "create_profile", args: ["alice", "Hello world"] };

const estimate = await client.estimateTransactionFeesForWrite(write);
const txId = await client.writeContract({
  ...write,
  fees: { distribution: estimate.distribution, messageAllocations: estimate.messageAllocations, feeValue: estimate.feeValue },
});

const transaction = await client.waitForFinalization({ hash: txId });   // final fees + refunds
if (!isSuccessful(transaction)) {
  throw new Error(`Write failed: ${transaction.statusName} / ${transaction.txExecutionResultName}`);
}
```

2.0.0-rc.1 deltas (verbatim from `dist/index-D2ZtkmJ5.d.ts`):

```ts
writeContract: (args: {
  ... , value?: bigint;               // now OPTIONAL
  validUntil?: BigNumberish;
  fees?: TransactionFeeOptions;       // { distribution?, messageAllocations?, feeValue? }
}) => Promise<any>

waitForTransactionReceipt: (args: {
  hash: TransactionHash;
  /** @deprecated Use waitUntil: "decided" or waitUntil: "finalized" instead. */
  status?: TransactionStatus;
  waitUntil?: TransactionReceiptWaitUntil;   // "decided" | "finalized"
  interval?: number; retries?: number; fullTransaction?: boolean;
}) => Promise<GenLayerTransaction>

waitForDecision:      (args: { hash; interval?; retries?; fullTransaction? }) => Promise<GenLayerTransaction>
waitForFinalization:  (args: { hash; interval?; retries?; fullTransaction? }) => Promise<GenLayerTransaction>

type TransactionFeeOptions = {
  distribution?: FeesDistributionInput;
  messageAllocations?: MessageFeeAllocationInput[];
  feeValue?: BigNumberish;
};

type TransactionReceiptWaitUntil = "decided" | "finalized";
```

### Which wait to use
- `waitForDecision` / `waitUntil: "decided"` — consensus reached; appeal window still open. Use for UI "accepted".
- `waitForFinalization` — appeal window closed, fees settled/refunded. Use for **accounting and durable completion**.
- `waitForTransactionReceipt({ status: ACCEPTED })` in 1.1.8 also returns on any decided state
  (the implementation checks `status === "ACCEPTED" && isDecidedState(...)`), so `UNDETERMINED`,
  `VALIDATORS_TIMEOUT`, `LEADER_TIMEOUT`, `CANCELED` and `FINALIZED` all satisfy it. **It can return a
  failed-but-decided tx** — you must still inspect `txExecutionResultName`.

---

## 5. Transaction statuses — exact enum values

### `TransactionStatus` in genlayer-js 1.1.8 (verbatim, `genlayer-js/types`)

```ts
declare enum TransactionStatus {
    UNINITIALIZED = "UNINITIALIZED",
    PENDING = "PENDING",
    PROPOSING = "PROPOSING",
    COMMITTING = "COMMITTING",
    REVEALING = "REVEALING",
    ACCEPTED = "ACCEPTED",
    UNDETERMINED = "UNDETERMINED",
    FINALIZED = "FINALIZED",
    CANCELED = "CANCELED",
    APPEAL_REVEALING = "APPEAL_REVEALING",
    APPEAL_COMMITTING = "APPEAL_COMMITTING",
    READY_TO_FINALIZE = "READY_TO_FINALIZE",
    VALIDATORS_TIMEOUT = "VALIDATORS_TIMEOUT",
    LEADER_TIMEOUT = "LEADER_TIMEOUT"
}
```

Notes:
- The value you asked about as `UNDEFINED` is actually **`UNINITIALIZED`**. There is no `UNDEFINED`
  member in either version (grep-verified).
- `PENDING → PROPOSING → COMMITTING → REVEALING → ACCEPTED` is the normal happy path.
- Numeric codes over the wire: `transactionsStatusNumberToName` maps `"0"`–`"13"` (0 = UNINITIALIZED,
  5 = ACCEPTED, 7 = FINALIZED). On Studio chains, `ACTIVATED` is remapped to `PENDING` client-side.
- `getTransaction()` returns **both** `status` (number) and `statusName` (string). Read `statusName`.

### `TransactionStatus` in 2.0.0-rc.1 (changed!)

```ts
declare enum TransactionStatus {
    UNINITIALIZED, PENDING, PROPOSING, COMMITTING, REVEALING, ACCEPTED,
    UNDETERMINED, FINALIZED, CANCELED, APPEAL_REVEALING, APPEAL_COMMITTING,
    VALIDATORS_TIMEOUT, LEADER_TIMEOUT, LEADER_REVEALING
}
```
Diffs vs 1.1.8: **`READY_TO_FINALIZE` removed**, **`LEADER_REVEALING` added**. Don't string-match on
`READY_TO_FINALIZE` if you might upgrade.

2.0.0-rc.1 also adds, for advanced reads:
```ts
declare enum TransactionResolutionAction {
    NO_OP = "NoOp", CANCEL = "Cancel", REPLACE_ACTOR = "ReplaceActor",
    ROTATE_LEADER = "RotateLeader", RESOLVE_APPEAL = "ResolveAppeal",
    MATERIALIZE_DECISION = "MaterializeDecision", FINALIZE = "Finalize"
}
type TransactionReceiptWaitUntil = "decided" | "finalized";
type TransactionLifecycle =
  | { state: "processing"; phase: TransactionProcessingPhase }
  | { state: "decided"; outcome: TransactionDecisionOutcome }
  | { state: "finalized"; outcome?: TransactionDecisionOutcome }
  | { state: "canceled" };
// outcome: "accepted" | "undetermined" | "validators-timeout" | "leader-timeout"
```

### `ExecutionResult` — consensus is NOT execution success

1.1.8 (3 values):
```ts
declare enum ExecutionResult {
    NOT_VOTED = "NOT_VOTED",
    FINISHED_WITH_RETURN = "FINISHED_WITH_RETURN",
    FINISHED_WITH_ERROR = "FINISHED_WITH_ERROR"
}
```
2.0.0-rc.1 (6 values) adds `TIMEOUT`, `NONDET_DISAGREE`, `DETERMINISTIC_VIOLATION`.

`ACCEPTED` means the committee agreed on the receipt — it does **not** mean the contract succeeded.
Always require `FINISHED_WITH_RETURN` in addition to the status. In 2.0.0-rc.1, `isSuccessful(tx)`
does this check for you.

Protocol codes (docs, for cross-referencing only): `5` = Accepted, `7` = Finalized.

---

## 6. Wallet binding & signing

There is **no `signerAddress` field** anywhere in genlayer-js 1.1.8 or 2.0.0-rc.1 (grep-verified
absent in both `.d.ts` sets and the runtime bundle). The binding is done the viem way:

```ts
const writeClient = createClient({
  chain: testnetBradbury,
  account: walletAddress as `0x${string}`,   // wagmi useAccount().address
  provider: window.ethereum,
});
```

How it resolves, per call: `const senderAccount = args.account || client.account;` → the address is
passed as the `from` of the RPC request (`readContract` uses `account?.address ?? client.account?.address ?? zeroAddress`).
So per-call `account` overrides the client-level one.

**Two distinct signing paths**, chosen inside `_sendTransaction` by `account.type`:

1. `type: "local"` (e.g. `createAccount()` / `privateKeyToAccount()`) → genlayer-js calls
   `eth_gasPrice`, builds a legacy tx, and signs it itself via `account.signTransaction(...)`,
   then `eth_sendRawTransaction`. No popup.
2. Otherwise (bare address + `provider`) → calls **`eth_sendTransaction`**, which pops the wallet.
   The returned EVM hash is then mined, and the GenLayer tx id is extracted from receipt logs via
   `extractTxIdFromLogs()` (`NewTransaction` → `CreatedTransaction` fallback).

Both paths then `waitForTransactionReceipt` on the **EVM** tx and throw `"<op> reverted: EVM tx 0x…"`
if it reverted. There is a fallback-encoded-data retry triggered by
`isAddTransactionAbiMismatchError()` ("invalid pointer in tuple" / "could not decode" / etc.).

### With wagmi/RainbowKit

Use the wagmi address as `account` and `window.ethereum` as `provider`. `provider` gives
genlayer-js the raw EIP-1193 object for signing. Two practical notes:

- wagmi's `useWalletClient()` is already EIP-1193-capable and is the cleaner source than
  `window.ethereum` (it survives the injected-provider being replaced). If you pass a wagmi
  `WalletClient` as `provider`, verify genlayer-js only calls standard EIP-1193 methods — from the
  bundle it uses `eth_sendTransaction`, `eth_gasPrice`, `eth_estimateGas`, `eth_chainId`,
  `wallet_addEthereumChain`, `wallet_switchEthereumChain`, `wallet_getSnaps`, `wallet_requestSnaps`.
- Only `eth_sendTransaction` triggers UI. Reads never prompt.

### The Snap problem — this is the big one for RainbowKit

`client.connect(network, snapSource)` is **MetaMask-Snap-only**:

```ts
var connect = async (client, network = "studionet", snapSource = "npm") => {
  if (!window.ethereum) throw new Error("MetaMask is not installed.");
  if (network === "mainnet") throw new Error(`${network} is not available yet. Please use localnet.`);
  ...
  await window.ethereum.request({ method: "wallet_addEthereumChain", params: [chainParams] });
  await window.ethereum.request({ method: "wallet_switchEthereumChain", params: [{ chainId: chainIdHex }] });
  const id = snapSource === "local" ? "local:http://localhost:8081" : "npm:genlayer-wallet-plugin";
  const installedSnaps = await window.ethereum.request({ method: "wallet_getSnaps" });
  if (!isGenLayerSnapInstalled) {
    await window.ethereum.request({ method: "wallet_requestSnaps", params: { [id]: {} } });
  }
  client.chain = selectedNetwork;
};
```

Consequences for a RainbowKit dApp:
- `connect()` calls `wallet_getSnaps` / `wallet_requestSnaps`, which **only MetaMask supports**.
  With RainbowKit you will use non-MetaMask wallets (WalletConnect, WalletConnect-based mobile).
- `connect()` throws on `network === "mainnet"` — there is no mainnet.
- It mutates `client.chain` as a side effect.

**Recommendation:** don't call `client.connect()` in a RainbowKit app. Construct the client with the
imported chain constant and let RainbowKit/wagmi own connection state; use
`wallet_addEthereumChain` / `wallet_switchEthereumChain` via wagmi's `switchChain` for network switching.
Call `connect()` only if you specifically need the MetaMask GenLayer Snap (`genlayer-wallet-plugin`).

### Chain-id caveat for wallets
Because `testnetAsimov` and `testnetBradbury` are both **4221**, `switchChain({ chainId: 4221 })`
cannot distinguish them. If you offer both in a wallet UI, you must switch by RPC URL manually.

---

## 7. Working Next.js / React skeleton

```ts
// lib/genlayer.ts
import { createClient } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { useAccount, useWalletClient } from "wagmi";
import { useMemo } from "react";

export const CONTRACT = "0x…" as `0x${string}`;
export const CHAIN = testnetBradbury;

// Reads: module-level, no wallet. Safe in RSC/client components.
export const readClient = createClient({ chain: CHAIN });

export async function getValue(): Promise<unknown> {
  return readClient.readContract({
    address: CONTRACT,
    functionName: "get_storage",
    args: [],
    transactionHashVariant: "latest-final", // only read finalized state
  });
}

// Writes: memoized per connected wallet.
export function useGenLayerWriter() {
  const { address } = useAccount();
  const { data: walletClient } = useWalletClient();

  return useMemo(() => {
    if (!address) return null;
    return createClient({
      chain: CHAIN,
      account: address,
      provider: window.ethereum, // swap for walletClient if you need multi-provider support
    });
  }, [address, walletClient]);
}
```

```ts
// app/actions/write.ts  — client-side only
import { TransactionStatus, ExecutionResult } from "genlayer-js/types";

export async function submitUpdate(client: ReturnType<typeof useGenLayerWriter>) {
  const txId = await client.writeContract({
    address: CONTRACT,
    functionName: "update_storage",
    args: ["new_value"],
    value: BigInt(0),           // required on 1.1.8; optional on 2.0.0-rc.1
  });

  const receipt = await client.waitForTransactionReceipt({
    hash: txId,
    status: TransactionStatus.FINALIZED,
    interval: 2000,
    retries: 60,               // ~2 min; defaults are 3 s × 10 = 30 s and will time out
  });

  if (receipt.txExecutionResultName !== ExecutionResult.FINISHED_WITH_RETURN) {
    throw new Error(`${receipt.statusName} / ${receipt.txExecutionResultName}`);
  }
  return { txId, receipt };
}
```

RainbowKit provider (wagmi **2.x** API — `WagmiProvider`, no `chains` prop on `RainbowKitProvider`):

```tsx
"use client";
import { WagmiProvider, http } from "wagmi";
import { RainbowKitProvider, getDefaultConfig } from "@rainbow-me/rainbowkit";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { testnetBradbury } from "genlayer-js/chains";

const config = getDefaultConfig({
  appName: "My GenLayer dApp",
  projectId: process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID!,
  chains: [testnetBradbury as any],   // GenLayerChain is a viem Chain, satisfies wagmi's type
  transports: { [testnetBradbury.id]: http("https://rpc-bradbury.genlayer.com") },
});
const queryClient = new QueryClient();

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <WagmiProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider>{children}</RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
```

Also export `"use client"` at the top of any file that imports genlayer-js and touches `window`.

### TanStack Query for reads
Reads are consensus-backed and slower than EVM `eth_call`. Cache them:

```ts
const q = useQuery({
  queryKey: ["value", CONTRACT],
  queryFn: getValue,
  staleTime: 15_000,
  refetchInterval: 10_000,
});
```
Invalidate/refetch on write success rather than optimistically mutating — GenLayer has no mempool
to observe, so there is no "pending → confirmed" local state to mirror.

---

## 8. Errors and edge cases

| Situation | Behaviour |
|---|---|
| EVM leg reverts | throws `` `${op} reverted: EVM tx ${hash}` `` |
| No `NewTransaction`/`CreatedTransaction` event in receipt | throws "EVM tx succeeded but no NewTransaction or CreatedTransaction event was found in the receipt logs." |
| Gas estimation fails | logs a warning, falls back to `200_000n` |
| `waitForTransactionReceipt` timeout | throws `` `Timed out waiting for transaction ${hash} to reach status "${status}" (current status: ${current}).` `` |
| Consensus-decided but contract failed | **no throw** — returns the receipt; check `txExecutionResultName` |
| `readContract` default | `jsonSafeReturn: true`, `latest-nonfinal` state |
| `waitForTransactionReceipt` default | status `ACCEPTED`, interval 3000 ms, retries 10 |

Do **not** blindly retry a timed-out write — the first write may already have executed.
Re-read state, or query by a stable key, instead of re-submitting.

---

## 9. Custom RPC methods available

Via `client.request({ method, params })` (typed union `GenLayerMethod`):
`sim_fundAccount`, `eth_getTransactionByHash`, `eth_call`, `eth_sendRawTransaction`,
`gen_getContractSchema`, `gen_getContractSchemaForCode`, `gen_getContractCode`,
`sim_getTransactionsForAddress`, `eth_getTransactionCount`, `eth_estimateGas`, `gen_call`,
`sim_cancelTransaction`.

Higher-level: `getContractSchema`, `getContractSchemaForCode`, `getContractCode`,
`getTriggeredTransactionIds`, `debugTraceTransaction`, `getTransactionQueuePosition`,
`cancelTransaction`, `getRoundNumber`, `getRoundData`, `getLastRoundData`, `canAppeal`,
`appealTransaction`, `finalizeTransaction`, `finalizeIdlenessTxs`, `getMinAppealBond`,
`getCurrentNonce`, `estimateTransactionGas`, `metamaskClient`, `connect`,
plus the full `StakingActions` surface (validator/delegator join/exit/claim, `fundAccount`, etc.).

---

## 10. Recommended install

```bash
# stable (documented API differs — see §4a)
npm i genlayer-js@1.1.8

# documented API, but a release candidate
npm i genlayer-js@2.0.0-rc.1

# wallet stack — wagmi MUST be 2.x for RainbowKit 2.2.11
npm i wagmi@2 viem@2 @rainbow-me/rainbowkit@2 @tanstack/react-query@5
```

```json
{
  "dependencies": {
    "genlayer-js": "1.1.8",
    "wagmi": "^2.19.5",
    "viem": "^2.57.2",
    "@rainbow-me/rainbowkit": "^2.2.11",
    "@tanstack/react-query": "^5.104.1",
    "react": "^19.3.0",
    "react-dom": "^19.3.0"
  }
}
```

Pin `genlayer-js` exactly (no `^`) — its minor line is in active flux and 1.x/2.x have incompatible
method surfaces.

---

## Verification notes
- Enum values, method signatures, chain ids/URLs and polling defaults were read directly from the
  published tarballs, not paraphrased from docs.
- Absence claims (`waitForFinalization` in 1.1.8, `signerAddress`, `stateStatus`, `sendTransaction`,
  `getTxHash`, `pollForTransactionReceipt`, `UNDEFINED`) were established by grepping both the
  `.d.ts` sets and the runtime JS bundles of each version.
- Two known **documentation defects** to ignore: `stateStatus: "accepted"` on `readContract`
  (option doesn't exist), and `value: 0` / `network:` as a number instead of `BigInt` in some snippets.
- `1.2.0` being non-`latest` is a real npm registry state, not a typo.
- RainbowKit/WalletConnect Node-polyfill caveat in §1 is general ecosystem knowledge, not verified
  against GenLayer specifically.