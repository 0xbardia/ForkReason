# Dependencies

Every version here was chosen deliberately. Where the obvious choice is wrong,
the reason is recorded.

## Frontend

| Package | Version | Why this version |
|---|---|---|
| `next` | **15.5.27** | 15.5.4 is inside the RCE range `<15.5.7` (GHSA-9qr9-h5gf-34mp, CVSS 10). 15.5.27 is the patched 15.x line. Staying on 15 avoids the wagmi/RainbowKit churn in 16. |
| `react` / `react-dom` | 19.3.0 | RainbowKit peer is `>=18`; React 19 is supported. |
| `wagmi` | **2.19.5** | **Must be 2.x.** `@rainbow-me/rainbowkit@2.2.11` declares peer `wagmi ^2.9.0`; `npm i wagmi` resolves to 3.7.7, an unsatisfiable peer that breaks the build. |
| `viem` | 2.57.2 | `genlayer-js` depends on `viem ^2.29.0`. |
| `@rainbow-me/rainbowkit` | 2.2.11 | Current 2.x line. |
| `@tanstack/react-query` | 5.104.1 | RainbowKit peer `>=5`; peer allows React 19. |
| `genlayer-js` | **1.1.8** | The `latest` line. **Do not use `2.0.0-rc.1`**: it is a release candidate and its documented API (`waitForFinalization`, `isSuccessful`, `estimateTransactionFeesForWrite`, `waitUntil`) is absent from 1.1.8. See the API notes below. |
| `typescript` | 5.9.3 | wagmi 3 needs `>=5.9.3`; 5.9.3 also satisfies wagmi 2. |
| `@playwright/test` | 1.56.1 | Chromium + Firefox + WebKit. |

### Transitive advisories resolved via `overrides`

`npm audit` reports **0 critical, 0 high** after these. Each one otherwise
required a breaking major upgrade that would break RainbowKit.

| Package | Override | Advisory |
|---|---|---|
| `postcss` | `8.5.23` | `<8.5.23` (high); pulled in by Next |
| `sharp` | `0.35.4` | `<0.35.4` (high) |
| `ws` | `8.21.0` | `<8.21.0` (high); arrives via viem |

Remaining `moderate` advisories are in WalletConnect/Reown SDK code reachable
only through a WalletConnect project id, which is optional and unset by default.
See `docs/SECURITY-FINDINGS.md`.

## Backend

| Package | Version | Notes |
|---|---|---|
| Python | 3.12.13 | Contract SDK requires 3.12+. |
| `fastapi` | ≥0.115 | |
| `uvicorn[standard]` | ≥0.32 | Serves the API. |
| `pydantic` | ≥2.9 | |
| `pydantic-settings` | ≥2.6 | Env loading with alias support. |
| `sqlalchemy` | 2.1.3 | |
| `alembic` | ≥1.14 | |
| `psycopg[binary]` | 3.3.6 | PostgreSQL driver. |
| `pytest` | 9.1.1 | |

## GenLayer contract SDK

Verified empirically, not from prose. Full detail in
`docs/GENLAYER-SDK-VERIFIED.md`.

| Package | Version | Source |
|---|---|---|
| `genlayer-py` | v0.18 | `git+https://github.com/genlayerlabs/genlayer-py@v0.18` |
| `genlayer-test` | 0.29.2 | `git+https://github.com/genlayerlabs/genlayer-testing-suite@v0.29` |
| `genvm-linter` | 0.11.1rc2 | `git+https://github.com/genlayerlabs/genvm-linter@main` |
| `genlayer` (CLI) | 0.40.0-rc.3 | `npm install -g genlayer` |

**The PyPI package named `genlayer` is a 0.0.1 placeholder with no entry points.**
It is not the SDK. The real distributions come from the `genlayerlabs` git URLs
above, which is what the official project boilerplate pins.

### Contract dependency header

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

This is a runtime pin resolved by the VM, not documentation. It must not be
removed.

## GenLayerJS API notes (the traps)

Verified against the published 1.1.8 tarball.

- **Chain exports** come from `genlayer-js/chains`: `localnet` (61127),
  `studionet` (61999), `testnetAsimov` (4221), `testnetBradbury` (4221).
  Asimov and Bradbury share a chain id, so only one can be active at a time.
- **RPC override** is the `endpoint` client option, not a mutated chain.
- `writeContract` in 1.1.8 requires `value: bigint` and returns the **GenLayer
  transaction id**, not the EVM hash.
- `waitForTransactionReceipt` defaults to `status: "ACCEPTED"`, `interval:
  3000ms`, `retries: 10` (~30s ceiling).
- **A decided transaction is not a successful one.** `ACCEPTED` means the
  committee agreed on the receipt. `ExecutionResult.FINISHED_WITH_RETURN` must
  also be checked.
- Wallet binding is viem-style: `createClient({ chain, account: address,
  provider })`. There is no `signerAddress` field.
- `readContract` uses `transactionHashVariant`, not the `stateStatus` option the
  docs show.

## Tooling

| Tool | Version |
|---|---|
| `uv` | 0.12.19 |
| Node.js | 22.23.3 |
| PostgreSQL | 18.6 |
| nginx | 1.28.3 |
| PM2 | 0.11.22 (Node 20 runtime) |