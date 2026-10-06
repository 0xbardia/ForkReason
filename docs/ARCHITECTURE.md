# Architecture

ForkReason is three durable processes and one database, with a hard boundary at
the chain.

```
                    ┌──────────────────────────┐
   browser ────────▶│  nginx                   │
                    │  TLS · security headers  │
                    │  /api → 8421             │
                    └───────┬──────────┬───────┘
                            │          │
                   ┌────────▼───┐  ┌───▼──────────────┐
                   │ web :3112  │  │ api :8421        │
                   │ Next.js    │  │ FastAPI          │
                   └────────────┘  └───┬──────────────┘
                                         │
                          ┌──────────────┼───────────────┐
                          │              │               │
                    ┌─────▼─────┐  ┌─────▼─────┐  ┌──────▼─────┐
                    │PostgreSQL │  │ snapshots │  │  GenLayer  │
                    │state+queue│  │  on disk  │  │  (read)    │
                    └─────┬─────┘  └───────────┘  └────────────┘
                          │ SKIP LOCKED
                    ┌─────▼──────────┐
                    │ worker         │
                    │ no listener    │
                    └────────────────┘
```

## Why three processes

Repository analysis takes seconds to minutes. Running it inside an HTTP request
would tie up a web worker, produce no progress, and lose the work on any
restart. The worker therefore has **no listener at all** and takes jobs from the
database.

Separating it also means a worker crash cannot take the API down. It can.

## The job queue

No Redis. PostgreSQL already exists here, and one fewer broker is one fewer
failure mode.

```sql
SELECT ... FROM analysis_jobs
 WHERE status = 'queued'
   AND (lease_expires_at IS NULL OR lease_expires_at < now())
 ORDER BY created_at
 FOR UPDATE SKIP LOCKED
 LIMIT 1;
```

- **Lease** — a claimed job gets `lease_expires_at`. If the worker dies, the
  lease expires and the job becomes claimable again. This is why the lease is
  cleared only on *normal* completion: clearing it in a `finally` would strand a
  crashed job forever.
- **Idempotency** — a unique key over the pinned pair plus options means
  resubmitting the same request returns the existing job instead of duplicating
  work.
- **Backoff** — repeated failure stops after a bound instead of retrying forever.
- **Cancellation** — cooperative, checked at stage boundaries.

## Data model

| Model | Notes |
|---|---|
| `RepositorySnapshot` | Immutable: a repository pinned at one commit |
| `AnalysisJob` | Durable work with real stage states |
| `Case` | Points at the current revision; holds no mutable verdict fields |
| `CaseRevision` | Append-only, unique `(case_id, revision)` |
| `EvidenceItem` | Bound to commit, path, bounded excerpt, strength |
| `EvidenceRelation` | Edges for the evidence graph |
| `AlternativeExplanation` | Competing explanations and their plausibility |
| `Challenge` | Challenge record and its resolution |
| `ChainTransaction` | Recorded GenLayer transaction references |

## The chain boundary

The database **indexes** chain state. It must never become the authority over
on-chain revision or verdict state.

If the database says revision 2 and the chain says revision 1, the chain wins
and the database row is treated as stale cache to be corrected. This is the
single most important invariant in the system, because the product's claim is
that a finding is *checkable by anyone*.

## Registration and revision projection

Repository analysis creates a provisional database revision 0. It is visible as
an analysis preview, but it is not represented as an accepted GenLayer case.
The case page requests a typed six-string `submit_case` payload from the API,
checks that its repositories, pinned commits and manifest still match the
selected preview, then creates the GenLayer write client in the browser from
the connected RainbowKit wallet. The wallet signs the ordered arguments:

```text
origin_repo, origin_commit, target_repo, target_commit, manifest_hash, evidence_digest
```

The browser stores the returned transaction id locally and posts it to the API
before it waits for consensus. The API and existing worker use the read-only
GenLayer SDK to verify the transaction's network, contract, calldata, sender,
execution result and finalized contract state. Pending writes remain pending;
the public Case pointer advances only after the accepted on-chain revision is
verified. An atomic PostgreSQL transaction appends revision 1 and advances the
pointer from 0. If that transaction rolls back, the submitted chain id remains
indexed and the worker retries it; the browser's local copy covers an API
outage before indexing. The browser polls indexed status and the public Case;
it never supplies verdict data to the reconciler.

A challenge follows the same boundary: current revision N → browser-wallet
`challenge_case` write for the stable initial manifest id and base revision N →
consensus → verified `get_challenge` and `get_revision(N+1)` reads → one atomic
database append and pointer update. Revision N is never changed. The browser
polls indexed status, and the worker polls persisted transaction ids so closing
the page does not stop reconciliation.

### Reconciliation trigger

The smallest mechanism that is reliable without new infrastructure: **the
browser reports, the worker verifies.** After the wallet returns a transaction
id the browser posts it to `POST /api/v1/chain/transactions`, which stores a
`chain_transactions` row (`submitted`). The existing worker process polls those
rows (`status in submitted, consensus_pending`) from a dedicated thread, so
closing the page does not stop reconciliation and a restart loses nothing.
Nothing the browser sends is trusted beyond the id: the verdict, revision and
challenge come from the chain.

| Property | Behaviour |
|---|---|
| Verified per write | network, contract address, sender, method, the exact calldata arguments (decoded from the binary form), execution result, `LATEST_FINAL` `get_case` / `get_revision` / `get_challenge` |
| Pending | stays `consensus_pending`; the public Case does not change |
| Atomicity | one transaction appends revision N+1 and moves `current_revision`; a rollback leaves the id `submitted` and the next poll retries |
| Idempotency / races | the Case row is locked; a second transaction for an existing revision is rejected; a stale observation cannot move the pointer back |
| Unseen hash | retried for 15 minutes (RPC lag), then `rejected` |
| Flooding | at most 8 unverified ids per case |
| RPC budget | contract reads happen only after a successful execution is accepted; rows are polled at most every 10 s; a rate limit backs a row off for 5 minutes (Studio allows 500 `gen_call` per hour) |

GenLayer is authoritative for accepted verdicts and revision order. PostgreSQL
is the application projection used for fast public Case reads; it cannot
override chain state. Public chain reads need no wallet, and no server signer
exists.

## The API's role

The API validates inputs, pins commits, enqueues jobs, and serves reads. It
prepares challenge payloads. It does **not** sign anything for a user — every
state-changing GenLayer action is signed by the visitor's own wallet. There is
no custodial signer and no `PRIVATE_KEY` in any request path.

## Module boundaries

```
apps/api/forkreason/
├── analysis/     fingerprint · dna · chronology · scoring · alternatives
│                 manifest · pipeline          (pure functions, no I/O)
├── repos/        github_url · github_api · snapshot
├── jobs/         queue · runner · profile_store
├── routes/       repositories · analyses · cases · explore · search · chain
├── domain.py     shared types and error codes
├── config.py     environment settings
├── models.py     SQLAlchemy models
└── main.py       app factory, middleware, exception handlers
```

The `analysis/` package is deliberately I/O-free and takes snapshots in, returns
a manifest out. That is what makes the forensic engine testable without a
database, a network, or a repository.

## Why the analysis engine is pure

A verdict must be reproducible. If scoring read global state, consulted a clock,
or depended on iteration order, the same two commits could produce two different
manifest hashes — and the hash is the product's central claim.

Determinism is therefore a design constraint, not a nicety:

- no clock reads inside scoring;
- sets are sorted before hashing;
- floats are quantized before canonicalization;
- JSON is canonicalized (sorted keys, ordered collections) before SHA-256.

The test `test_manifest_is_deterministic` asserts this directly.
