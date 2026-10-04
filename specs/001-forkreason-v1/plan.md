# Implementation Plan: ForkReason V1

**Branch:** `001-forkreason-v1`
**Spec:** `specs/001-forkreason-v1/spec.md`
**Constitution:** `.specify/memory/constitution.md` v1.0.0

---

## Summary

Build ForkReason V1 as three processes plus a GenLayer contract:

- **`apps/web`** — Next.js (App Router) frontend, the product surface.
- **`apps/api`** — FastAPI backend, versioned API, intake, jobs, cases.
- **`apps/worker`** — durable background forensic analysis worker.
- **`contracts/`** — GenLayer Intelligent Contract (`ForkReasonRegistry`).

Repository snapshots are cached on disk by immutable commit; application state
and the job queue live in PostgreSQL. Chain state is authoritative and is
mirrored into PostgreSQL for indexing only.

---

## Technical Stack

| Concern | Choice | Rationale |
|---|---|---|
| Frontend | Next.js 15 App Router + React 19 | Required surface complexity (docs, evidence graph, wallet) with server-rendered deep links |
| Styling | Tailwind v4 + CSS custom-property token layer | Tokens are the design system; Tailwind is only a token consumer |
| Fonts | Instrument Sans + JetBrains Mono, self-hosted | Required typography direction; self-hosted to avoid third-party requests |
| Wallet | RainbowKit + Wagmi + Viem | Required |
| Chain client | `genlayer-js` | Required for GenLayer reads/writes from browser |
| Backend | Python 3.12 + FastAPI + Pydantic v2 | Required stack |
| DB | PostgreSQL 18 + SQLAlchemy 2 (sync) + Alembic | Required; sync driver keeps the worker simple |
| Jobs | PostgreSQL `FOR UPDATE SKIP LOCKED` | No extra broker dependency |
| Intake | GitHub REST + `git` plumbing via argv arrays | Required safe handling |
| Forensic core | Deterministic Python (hashlib, difflib, tokenizers) | Constitution II.10 |
| Contract | GenLayer Python SDK, current pinned deps | Required |
| Contract tests | `genlayer-test` Direct Mode + Studio Mode | Required |
| Frontend tests | `@playwright/test` | Required |
| Process supervision | PM2 (already systemd-managed on host) | Consistency with existing services |

## Constitution Compliance

| Principle | Implementation |
|---|---|
| II.6 Evidence provenance | `EvidenceItem` requires repo, commit, path, excerpt |
| II.7 Weak stays weak | `scoring.py` rarity weight via shared-vs-unique term frequency |
| II.8 Contradictions preserved | `conflicting_signals` on manifest and report |
| II.10 Determinism first | SHA-256 fingerprints; LLM only for semantic verdict; manifest hash canonical |
| III.11 Data not instructions | `prompts.py` wraps untrusted content in delimiters + inert-data directive |
| III.12 No execution | `intake.py` never runs repo code; only `git` plumbing argv |
| III.13 Bounded | `Settings` limits enforced in intake + analysis |
| IV.15 Substance over format | Custom validator recomputes verdict fields |
| IV.16 Independent | `run_validator` per validator index recomputing |
| IV.17 Fail closed | Non-agreement → no accepted state |
| IV.18 No storage in nondet | Contract: nondet block returns only; storage written after |
| IV.19 Immutable revisions | Contract appends, never overwrites |
| V.20 User signs | Browser signs; no server signer |
| V.21 DB not authority | `ChainTransaction` records tx hash; `CaseRevision` mirrors `revision_number` |
| VI.23 Smallest architecture | No DI container, no ORM repository factories |

## Project Layout

```
/root/ForkReason
├── apps/
│   ├── api/                 # FastAPI service
│   │   └── forkreason/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── logging_setup.py
│   │       ├── db.py
│   │       ├── models.py            # SQLAlchemy ORM (all tables)
│   │       ├── schemas.py           # Pydantic API contracts
│   │       ├── errors.py            # stable error codes
│   │       ├── ids.py               # deterministic ID + hash helpers
│   │       ├── routes/
│   │       │   ├── health.py
│   │       │   ├── repositories.py
│   │       │   ├── analyses.py
│   │       │   ├── cases.py
│   │       │   ├── search.py
│   │       │   └── chain.py
│   │       ├── repos/                # GitHub intake + git plumbing
│   │       │   ├── github_url.py     # URL parse/normalize/validate
│   │       │   ├── github_api.py     # REST client w/ backoff
│   │       │   ├── snapshot.py       # safe clone + file inventory
│   │       │   └── history.py        # commit extraction
│   │       ├── analysis/
│   │       │   ├── pipeline.py       # stage orchestration
│   │       │   ├── dna/
│   │       │   │   ├── code.py
│   │       │   │   ├── architecture.py
│   │       │   │   ├── history_dna.py
│   │       │   │   ├── bug.py
│   │       │   │   ├── test_dna.py
│   │       │   │   └── language.py
│   │       │   ├── chronology.py
│   │       │   ├── upstream.py
│   │       │   ├── alternatives.py
│   │       │   ├── scoring.py
│   │       │   └── manifest.py       # canonical manifest + hash
│   │       └── jobs/
│   │           ├── queue.py          # claim/complete/fail
│   │           └── runner.py         # worker loop
│   ├── web/                 # Next.js app
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── styles/
│   └── worker/              # worker entrypoint (thin)
├── contracts/
│   ├── forkreason_registry.py
│   └── tests/
├── fixtures/                # synthetic repos A-G + injection
├── docs/
├── playwright/
└── deploy/
```

## Backend Module Design

Domain folders map to concepts, not to layers of ceremony:

- `repos/` — everything about getting bytes safely out of GitHub.
- `analysis/` — everything about turning two snapshots into a manifest.
- `jobs/` — durability and the worker loop.
- `routes/` — HTTP only; no business logic.
- `models.py`/`schemas.py` — persistence and transport shapes.

There is no service layer or repository-abstraction layer: `routes` call module
functions directly. That is deliberate — an extra indirection with one
implementation and one consumer is architecture theatre.

### Data Model (SQLAlchemy)

- `RepositorySnapshot` — repo, pinned commit, default branch, size, file
  inventory summary, cached path, created_at.
- `AnalysisJob` — id, origin/target snapshot refs, status, stage, stage states
  JSON, error code, idempotency key, attempts, lease timestamps, created/started/
  finished timestamps.
- `Case` — id, job id, origin/target repo+commit, manifest hash, current
  revision number, lifecycle status.
- `CaseRevision` — case id, revision number, verdict, confidence, direction,
  shared upstream, manifest hash, tx hash, created_at. **Append-only.**
- `EvidenceItem` — deterministic id, case id, revision number, DNA layer,
  evidence type, strength, rationale, origin/target provenance JSON, excerpt.
- `EvidenceRelation` — subject id, object id, relation type.
- `AlternativeExplanation` — case id, kind, support score, rationale.
- `Challenge` — case id, base revision, submitter, evidence refs, status, tx hash.
- `ChainTransaction` — tx hash, case id, kind, status, network, created_at.

Indexes: `cases(current_revision_number)`, `cases(created_at DESC)`,
`case_revisions(case_id, revision_number)` unique,
`analysis_jobs(status)`, `evidence_items(case_id, revision_number)`.

### Analysis Pipeline Stages

Real stages surfaced to the UI (no percentages):

1. `repository_snapshots`
2. `commit_history`
3. `structural_fingerprints`
4. `historical_signals`
5. `shared_upstream`
6. `alternative_explanations`
7. `evidence_manifest`
8. `consensus_preparation`

Each stage writes a terminal or running state to `AnalysisJob.stage_states`.

### Deterministic Fingerprinting

- **Token fingerprint**: shingle file content into 5-gram token hashes after
  identifier normalization; compare set Jaccard.
- **Structure fingerprint**: normalized AST-free structural skeleton (imports,
  function/class names, call names, control keywords) → sorted token multiset
  hash.
- **Constant fingerprint**: numeric/string literals that are uncommon across the
  pair's own corpus.
- **Rare-token weight**: tokens appearing in both repos but rare in a baseline
  set of common framework tokens get higher weight.
- **Path topology**: normalized directory tree signature.

### Chronology Rules (deterministic, outside prose)

- A signal is `directional` only if its first-occurrence commit in origin
  predates its first-occurrence commit in target.
- If the signal appears earlier in target, it is recorded as a *counter-signal*.
- If a pre-fix bug signature present in origin is absent from target while
  target's first commit postdates origin's fix commit, that is *supporting* for
  derivation.
- These rules run in code and cannot be overridden by model output.

### Consensus Design (contract)

Leader path (nondeterministic):
1. Build a bounded evidence digest (top N items, truncated excerpts, delimiters).
2. Model returns typed JSON: verdict, confidence, direction, shared_upstream,
   independent_origin_plausibility, strongest_evidence_classes, rationale.
3. Strict parse; enum validate; deterministic chronology rules applied to the
   digest; if model output contradicts chronology, clamp to the deterministic
   outcome rather than trusting prose.

Validator path (custom, `run_validator` per index):
- Each validator independently receives the same digest and its own model call,
  then compares its own fields to the leader's field by field.
- Agreement = stable field tuple equality on (verdict, confidence, direction,
  shared_upstream, independent_origin_plausibility, strongest evidence
  classes).
- Prose rationale is never compared.
- Any missing/invalid/unknown result → non-agreement → fail closed.

Storage after consensus only.

## Frontend Design System

Tokens in CSS custom properties under `apps/web/styles/tokens.css`:

- Colour: ink `#07110F`, moss `#0B1815`, glass `rgba(244,255,250,.08)`, paper
  `#F4FFF9`, mint `#12E6A7`, aqua `#13CFF4`, volt `#C8FF4A`, amber `#FFC857`,
  coral `#FF6655`, blue `#397BFF`, muted `#94AAA3`.
- Semantic roles: mint = verified/clean; aqua = source relationships; blue =
  consensus/chain; volt = independent/healthy; amber = uncertainty/pending;
  coral = conflict.
- Spacing 4px scale, radius scale, elevation/glass layers, motion durations,
  state colours, focus ring.
- Three motion families: LIQUID (glass edge/pointer light), TRACE (lineage edges
  and chronology), RESOLVE (verdict/revision reveal). All gated behind
  `prefers-reduced-motion`.

Components built only where needed: `GlassPanel`, `RepoInput`, `LineageVisual`,
`DnaRings`, `BranchTimeline`, `EvidenceGraph`, `EvidenceCard`, `VerdictHeadline`,
`ConsensusTimeline`, `RevisionList`, `StageTracker`, `WalletButton`, `ChallengeForm`.

## Contract Lifecycle

```
SUBMIT_CASE     -> SUBMITTED -> CONSENSUS_PENDING -> RESOLVED(rev 1)
CHALLENGE_CASE  -> RESOLVED -> CHALLENGED -> CONSENSUS_PENDING -> RESOLVED(rev N+1)
```

Stale challenge (base_revision != current) reverts. Duplicate manifest hash
reverts. Bounded strings revert. Unknown enum reverts.

## Deployment

nginx `forkreason.bydx.fun`:
- `/api` → `127.0.0.1:8421` (uvicorn)
- everything else → `127.0.0.1:3111` (Next.js standalone)
- TLS via certbot (already issued), HSTS, security headers, gzip.

PM2 processes: `forkreason-api`, `forkreason-worker`, `forkreason-web`.

## Testing Strategy

- **Backend unit**: pytest over pure modules (`github_url`, dna, chronology,
  upstream, alternatives, scoring, manifest, ids, errors, queue logic).
- **Backend integration**: pytest + real PostgreSQL (migrations applied), worker
  recovery, idempotency, timeout.
- **Contract Direct Mode**: `gltest` with Direct Mode fixtures covering the full
  FR-N-005 list, including leader-manipulation rejection and same-payload
  injection across validators.
- **Contract Studio Mode**: real multi-validator consensus for positive
  derivation, shared upstream, insufficient evidence, and challenge/revision.
- **Frontend**: Playwright across Chromium/Firefox/WebKit and the required
  viewports, asserting no console errors / overflow / hydration errors.
- **Security**: adversarial fixtures + contract injection suite + secret scan.

## Implementation Order

1. Scaffolding, config, env, database, migrations.
2. Forensic core (pure, no I/O) with unit tests.
3. Intake layer with URL validation and snapshot safety.
4. Pipeline + job queue + worker + API routes + API tests.
5. Fixtures (A–G incl. injection) and backend fixture scenario tests.
6. GenLayer contract + Direct Mode suite (green) + lint.
7. Studio Mode suite.
8. Frontend design system + routes + wallet/chain integration.
9. Playwright + visual QA loop.
10. Deploy + production QA.
11. Contract deploy to Studio; record real evidence.
12. Docs, open-source release, fresh-clone verification, final report.

## Acceptance Criteria

All constitution gates pass, all FRs verified by real test output, security has
zero open CRITICAL/HIGH, frontend and backend each score an honest ≥9.0/10,
production at `https://forkreason.bydx.fun` passes real-browser QA, and
`github.com/0xbardia/ForkReason` is public with a `v1.0.0` release whose `main`
commit matches the deployed candidate.