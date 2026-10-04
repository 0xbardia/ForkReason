# Dependencies

Versions are recorded with the reason they were chosen and what they were
verified against. Executable probes outrank documentation: where the shipped
SDK and `docs.genlayer.com` disagree, this project follows the SDK.

## Runtime

| Component | Version | Verified |
|---|---|---|
| Python | 3.12.13 | Local runs, full test suite green |
| PostgreSQL | 18 | Migrations applied, queue exercised |
| Node.js | 22.23.3 (frontend), 20.20.2 (PM2) | Production build, `next start` |
| nginx | system | TLS termination verified live |
| PM2 | system (Node 20) | Three production processes supervised |

## Backend

Declared in `pyproject.toml` as lower bounds; these are the versions resolved
in the release venv:

| Package | Resolved |
|---|---|
| `fastapi` | 0.142.2 |
| `uvicorn[standard]` | 0.54.0 |
| `pydantic` | 2.13.5 |
| `pydantic-settings` | 2.15.0 |
| `sqlalchemy` | 2.1.3 |
| `alembic` | 1.20.0 |
| `psycopg[binary]` | 3.3.6 |
| `requests` | 2.34.2 |
| `python-dotenv` | 1.2.4 |
| `pytest` (dev) | 9.1.1 |

**No Redis.** The durable queue is PostgreSQL with `FOR UPDATE SKIP LOCKED`. The
server already runs PostgreSQL; one fewer broker is one fewer failure mode.

**No model SDK in the backend.** The forensic engine is deterministic Python.
A model is consulted only inside GenLayer consensus, where the Equivalence
Principle governs it. Keeping the decision logic out of the backend is what makes
verdicts reproducible.

## Contract

Resolved in the release venv:

| Distribution | Version | Notes |
|---|---|---|
| `genlayer-test` | 0.29.2 | Direct Mode and Studio Mode |
| `genvm-linter` | 0.11.1-rc.2 | 3 checks |
| `glsim` | from `genlayer-test[sim]` | GLSim simulator, no Docker |

```bash
uv pip install --python .venv/bin/python 'genlayer-test[sim]'
```

The GenLayer Python SDK is used from source. Verified by executable probe inside
the Direct Mode VM:

| Symbol | Status |
|---|---|
| `gl.Contract` | **Verified** — compiles and runs in the real VM |
| `gl.vm.run_nondet` | **Verified** — the sandboxed leader+validator path used here |
| `gl.vm.UserError` | **Verified** |
| `gl.vm.unpack_result` | **Verified** |
| `gl.public.view` / `gl.public.write` | **Verified** |
| `TreeMap` storage | **Verified** |
| `@allow_storage` | **Does not exist** in the shipped surface |
| `run_nondet_default` | **Not present** in the installed SDK |
| `gl.contract.Contract` | Not required; `gl.Contract` works |

### Why this section exists

Secondary reference material was produced during this build that stated
`run_nondet` was unsafe, that `run_nondet_default` existed, and that
`gl.contract.Contract` must replace `gl.Contract`. Every one of those claims
contradicts an executed probe against the shipping SDK, and none could be
reproduced here.

**Policy:** executable probes outrank unexecuted documentation. A secondary
reference that disagrees with the shipping SDK is not adopted. Those files were
deleted rather than shipped.

Documented facts that *are* corroborated: `docs.genlayer.com` may diverge from
the shipping SDK; `@allow_storage` does not exist; `UserError.message` is not
the accessor (`UserError.data` is).

### Studio Mode model endpoint

Studio Mode certification runs against a local OpenAI-compatible stub
(`deploy/studio/model_stub.py`) reached through a process-scoped CONNECT proxy
(`deploy/studio/tls_proxy.py`). GLSim hardcodes `api.openai.com` and offers no
base-URL override; an `/etc/hosts` redirect was rejected because it is
machine-global and breaks other services on this host.

The stub implements the contract's exact schema and supports adversarial modes.
It certifies consensus mechanics, not hosted-model output quality — see
`contracts/RELEASE_CANDIDATE.md`.

## Frontend

Exact versions in `apps/web/package.json`:

| Package | Version | Reason |
|---|---|---|
| `next` | 15.5.27 | App Router, per-request CSP nonce support |
| `react` / `react-dom` | 19.3.0 | Current stable |
| `@rainbow-me/rainbowkit` | 2.2.11 | Wallet UX |
| `wagmi` | **2.19.5** | RainbowKit 2.2.11 peers `wagmi ^2.9.0`; `wagmi@latest` is 3.x and breaks it |
| `viem` | 2.57.2 | Wallet transport |
| `genlayer-js` | 1.1.8 | Chain reads and transaction lifecycle |
| `@tanstack/react-query` | 5.104.1 | Server-state caching |
| `@fontsource-variable/instrument-sans` | 5.3.0 | Self-hosted UI type |
| `@fontsource-variable/jetbrains-mono` | 5.3.0 | Self-hosted mono for commits/hashes |
| `@playwright/test` | 1.63 | Browser QA |
| `typescript` | 5.9.3 | Typecheck |

**Pinning `wagmi` to 2.x is load-bearing.** `npm i wagmi` installs 3.x, which is
outside RainbowKit 2.2.11's peer range.

**`genlayer-js`** is used for chain reads and transaction lifecycle. Verified
traps: `genlayer-js@latest` (1.1.8) does **not** have `waitForFinalization`,
`isSuccessful` or `estimateTransactionFeesForWrite` — those live in the `rc` tag.
The repo does not depend on those APIs.

**GenLayer is not in viem's chain registry**, so the network is defined
explicitly.

First-load JS is ~360 kB, dominated by the wallet SDK. Documentation routes
avoid the wallet bundle where practical.

## Security posture

`npm audit`: 0 critical, 0 high at release.
