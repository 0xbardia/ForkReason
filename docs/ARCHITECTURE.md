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
                   │ web :3100  │  │ api :8421        │
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
