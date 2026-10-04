# Feature Specification: ForkReason V1

**Feature Branch:** `001-forkreason-v1`
**Created:** 2026-10-03
**Status:** Draft
**Constitution:** `.specify/memory/constitution.md` v1.0.0

**Input:** Product mandate — "Trace where software really came from." A software
provenance and repository lineage dApp on GenLayer.

---

## Summary

ForkReason accepts two public GitHub repositories, reconstructs meaningful
development lineage between them using a deterministic forensic pipeline,
actively evaluates competing explanations for observed similarity, and records
an evidence-backed lineage decision as an immutable revision through GenLayer
consensus.

V1 delivers a complete product: ingestion, forensic analysis, an evidence model,
a GenLayer Intelligent Contract, a premium web experience, documentation,
security hardening, production deployment, and an open-source release.

## Terminology

**Domain terms**

- **Origin repository** — the repository treated as the candidate source.
- **Target repository** — the repository being explained.
- **Lineage** — the developmental relationship between repositories, including
  direction and, where applicable, a shared ancestor.
- **Common upstream** — a third repository from which both origin and target
  plausibly descend.
- **Repo DNA** — the six-layer evidence model (code, architecture, history, bug,
  test, language) whose signals are individually weighted.
- **Evidence item** — one finding, bound to a pinned commit, a file path, a
  bounded excerpt, and a strength.
- **Evidence Manifest** — the canonical, deterministically serialized set of
  evidence submitted to consensus, identified by a content hash.
- **Revision** — one immutable, ordered lineage decision on chain.
- **Challenge** — new evidence submitted against a resolved revision, which may
  produce revision N+1.

**Terms used as ordinary language, not domain terms**

This specification uses ordinary words such as *bug*, *test*, *sign*, *page*,
*link*, *table*, and *login*. Where such a word is technically significant it is
defined above.

---

## Constitution Check

*GATE: must pass before Phase 1 planning. Verified against v1.0.0.*

| Principle | Risk if ignored | Mitigation in this spec |
|---|---|---|
| I. Product Truth | Product reads as an accusation engine; legally unsupportable | Verdict enum excludes all accusatory values; `INSUFFICIENT_EVIDENCE` is a first-class outcome; banned words are a test assertion |
| II. Evidence Integrity | Evidence without provenance is unfalsifiable; boilerplate masquerades as lineage | Every evidence item requires commit+path+excerpt; rarity-weighted strength; contradictions stored and rendered |
| III. Untrusted Input | Repository analysis becomes RCE | No execution of analyzed code; explicit intake limits; injection fixtures as release gate |
| IV. Consensus Integrity | A single model decides; injection wins by unanimity | Independent validator evaluation; fail-closed; append-only revisions |
| V. Chain Boundary | Custodial signing of user actions | All user writes signed in browser; backend only prepares payloads |
| VI. Engineering | Architecture theatre, fabricated claims | Smallest architecture that satisfies V1; evidence-only reporting |

**Complexity justification:** V1 has three processes (web, API, worker) rather
than a monolith because long repository analysis must not block HTTP. The job
queue is PostgreSQL-backed rather than Redis-backed because the server already
runs PostgreSQL and one fewer dependency is one fewer failure mode.

---

## User Scenarios

### US-1 — First-time visitor (P1, primary journey)

A developer lands on ForkReason from a link about a suspected repository
relationship. They do not know what GenLayer is.

1. Within 10 seconds they understand ForkReason compares repositories and
   reports lineage.
2. They paste two GitHub repository URLs directly into the hero.
3. They see both repositories validated with owner/name, default branch, and
   the exact commit that will be analyzed.
4. They press **Trace lineage** without connecting a wallet.
5. They watch real pipeline stages complete.
6. They receive a lineage report with verdict, confidence, direction, and the
   strongest evidence.
7. They inspect Repo DNA, Lineage Timeline, Evidence Graph, conflicting
   evidence, alternative explanations, and GenLayer consensus.
8. They share a permanent case URL that resolves for anyone.
9. They challenge the case with additional evidence, sign with a browser
   wallet, and see a new immutable revision.

**Why this matters:** No developer knowledge of GenLayer is required.

### US-2 — Technical reviewer (P1)

An engineer opens a shared case URL and verifies the result independently.

1. Every evidence item shows its exact file, commit, and bounded excerpt.
2. They read the evidence manifest hash and confirm it.
3. They inspect the contract read methods and the transaction.
4. They read the security and limitations documentation.
5. They check the public source repository.

**Why this matters:** A forensic verdict must be checkable by an adversary.

### US-3 — Challenger who disagrees (P2)

A user believes the verdict is wrong and has new evidence.

1. They open the challenge surface for a resolved case.
2. They submit bounded evidence with a stated reason.
3. The backend prepares a challenge payload; their wallet signs the write.
4. The case resolves to revision N+1, and revision N remains readable.

**Why this matters:** A conclusion that cannot be contested is not credible.

---

## Requirements

### Section A — Repository Ingestion

**User value:** I can point ForkReason at any two public GitHub repositories and
trust that what gets analyzed is exactly what I named.

**FR-A-001** The system SHALL accept GitHub repository identifiers in the forms
`owner/repo`, `https://github.com/owner/repo`, and
`https://github.com/owner/repo/tree/<ref>`.

**FR-A-002** The system SHALL reject identifiers that are not public GitHub
repositories, enforcing: `https` scheme, hostname `github.com`, valid owner, valid
repository name, bounded total URL length, and no credential/userinfo component.

**FR-A-003** The system SHALL resolve and pin an immutable commit for each
repository before analysis, and SHALL display the pinned commit to the user.

**FR-A-004** The system SHALL enforce configurable intake limits: maximum
repository size, maximum single-file size, maximum file count, maximum history
depth, maximum evidence items, analysis wall-clock timeout, and worker
concurrency.

**FR-A-005** The system SHALL never execute repository content: no package
installation, no build, no test execution, no shell sourcing, no repo binaries,
no repository-provided plugins.

**FR-A-006** The system SHALL invoke external tools with argument arrays only,
and SHALL never interpolate repository-derived values into a shell command
string.

**FR-A-007** The system SHALL refuse to follow symlinks resolving outside the
analysis sandbox, and SHALL skip oversized, binary, and malformed-encoding files
rather than failing the entire analysis.

**FR-A-008** The system SHALL cache repository snapshots by immutable commit so
repeated analysis of the same commit does not re-clone.

**FR-A-009** The system SHALL surface an actionable, non-fatal message when a
repository is unsupported, private, missing, empty, or exceeds limits.

*Non-goal for A:* private repositories and non-GitHub hosts are out of V1 scope.

### Section B — Forensic Analysis (Repo DNA)

**User value:** The report explains a relationship using multiple independent
kinds of evidence rather than a single similarity score.

**FR-B-001** The system SHALL compute six deterministic DNA layers: CODE,
ARCHITECTURE, HISTORY, BUG, TEST, and LANGUAGE.

**FR-B-002** CODE DNA SHALL derive normalized token/structure fingerprints,
uncommon fragments, uncommon constants, and implementation patterns.

**FR-B-003** ARCHITECTURE DNA SHALL derive directory topology, module boundaries,
dependency relationships, and subsystem organization.

**FR-B-004** HISTORY DNA SHALL derive commit chronology, first-occurrence points,
deletion/rewrite events, implementation order, and temporal direction.

**FR-B-005** BUG DNA SHALL derive historically traceable defect signatures from
code present at specific commits, bug/fix commit pairs, regression scenarios,
and distinctive erroneous behaviour.

**FR-B-006** TEST DNA SHALL derive uncommon tests, fixtures, regression
scenarios, and distinctive test structure.

**FR-B-007** LANGUAGE DNA SHALL derive naming conventions, comment style, unusual
terminology, documentation structure, distinctive phrases, and rare
typo/signature evidence.

**FR-B-008** The system SHALL weight signal strength by rarity so that common
framework boilerplate cannot become strong lineage evidence through matching
alone.

**FR-B-009** The system SHALL establish temporal direction: a signal that first
appears in origin before target is directional evidence; a signal appearing
simultaneously or earlier in target is not.

**FR-B-010** The system SHALL preserve evidence that contradicts the working
hypothesis rather than discarding it.

**FR-B-011** The system SHALL be deterministic: identical pinned commits and
identical configuration SHALL produce an identical evidence manifest hash.

*Clarification: "direction" is the ordered (origin → target) relationship the
report asserts; where lineage is not directional (independent or shared
upstream) the report states that explicitly instead of inventing a direction.*

### Section C — Alternative Explanations

**User value:** I see the innocent explanations for the match, not only the
guilty one.

**FR-C-001** The system SHALL actively evaluate at least six alternative
explanations: derivation, shared upstream, independent same-specification
implementation, insufficient history, declared fork, and heavy
post-derivation divergence.

**FR-C-002** Each alternative explanation SHALL carry a support score derived
from evidence, not from prose.

**FR-C-003** The system SHALL compute shared-upstream candidates by comparing
each repository against candidates that predate the later repository.

**FR-C-004** The system SHALL select the best-supported explanation and SHALL
report runner-up explanations with their support levels.

**FR-C-005** When no explanation is adequately supported, the system SHALL return
`INSUFFICIENT_EVIDENCE` rather than choosing the least-bad option.

### Section D — Evidence Model & Manifest

**User value:** I can verify that the evidence is what was actually found.

**FR-D-001** Each evidence item SHALL carry: stable identifier, category (DNA
layer), evidence type, strength, plain-language explanation, and bounded
source references for origin and target (repository, commit, path, excerpt).

**FR-D-002** Each evidence item SHALL have a deterministic identifier derived
from its content.

**FR-D-003** The system SHALL produce a canonical Evidence Manifest containing:
schema version, case identifier, origin repository and commit, target repository
and commit, chronology timestamps, evidence items, evidence categories, strength
totals, conflicting signals, alternative explanations, common-upstream
candidates, and manifest creation version.

**FR-D-004** The manifest SHALL be canonicalized deterministically (sorted keys,
bounded and sorted collections, fixed numeric formatting) before hashing.

**FR-D-005** The manifest hash SHALL be the identifier bound to the on-chain
revision.

**FR-D-006** The system SHALL NOT place full repository content on chain or in
any model prompt.

**FR-D-007** Each evidence excerpt SHALL be bounded to a configured maximum
character length.

### Section E — Verdicts

**User value:** I get a defensible answer, or an honest "not enough".

**FR-E-001** The system SHALL support exactly six verdicts: `INDEPENDENT`,
`SHARED_UPSTREAM`, `DECLARED_FORK`, `LIKELY_DERIVED`, `HEAVILY_DERIVED`,
`INSUFFICIENT_EVIDENCE`.

**FR-E-002** The system SHALL report confidence as one of `LOW`, `MEDIUM`,
`HIGH`.

**FR-E-003** The system SHALL NOT present confidence as a calibrated
probability.

**FR-E-004** A result SHALL include verdict, confidence, direction where
applicable, strongest evidence, conflicting evidence, alternative explanations,
source repository, target repository, pinned commits, evidence manifest hash,
GenLayer transaction, and revision.

**FR-E-005** The system SHALL NOT emit any accusatory verdict or legal
conclusion; a test SHALL assert the banned vocabulary is absent from the
product surface.

### Section F — GenLayer Intelligent Contract

**User value:** The decision is recorded publicly and cannot be quietly edited.

**FR-F-001** The system SHALL provide a GenLayer Intelligent Contract written in
Python using the current official SDK, declared as `ForkReasonRegistry`,
retaining the canonical `# { "Depends": ... }` metadata header.

**FR-F-002** The contract SHALL expose explicit `@gl.public.view` and
`@gl.public.write` methods and SHALL NOT expose unbounded "return everything"
reads.

**FR-F-003** The contract SHALL store cases, ordered immutable revisions, verdict,
confidence, direction, shared upstream, pinned repository identifiers and
commits, manifest hash, submitter, creation order and time, challenge
references, a current-revision pointer, and revision history.

**FR-F-004** Lifecycle SHALL be `SUBMITTED` → `CONSENSUS_PENDING` →
`RESOLVED`; a challenge SHALL move `RESOLVED` → `CHALLENGED` →
`CONSENSUS_PENDING` → `RESOLVED` with revision N+1.

**FR-F-005** Revision N SHALL NEVER be overwritten.

**FR-F-006** The contract SHALL bound every input length and SHALL reject
malformed enum values, malformed identifiers, and stale-revision challenges.

**FR-F-007** The contract SHALL reject duplicate submissions and replays.

**FR-F-008** The contract SHALL expose read methods sufficient for the full
frontend and QA suite, including at minimum: `get_case`, `get_case_count`,
`get_latest_revision`, `get_revision`, `get_revision_count`, `get_challenge`,
`get_challenge_count`, and a bounded paginated case listing.

**FR-F-009** Nondeterministic execution SHALL NOT mutate contract storage; state
SHALL be written only after consensus returns, in deterministic execution.

**FR-F-010** The contract SHALL use external retrieval only through the GenLayer
nondeterministic web primitive inside a nondeterministic block, against an
allowlisted source set.

### Section G — Consensus Integrity

**User value:** One model does not decide; independent verification does.

**FR-G-001** The contract SHALL verify substance. Validation SHALL NOT accept a
leader result merely because it parses, uses a valid enum, includes a summary,
or has in-range confidence.

**FR-G-002** Stable consensus fields SHALL be compared as structured values:
verdict, direction, shared upstream, independent-origin plausibility,
confidence bucket, strongest evidence classes.

**FR-G-003** Prose explanations SHALL NOT be compared for exact equality.

**FR-G-004** `strict_eq` SHALL be used only for data that should normalize
identically.

**FR-G-005** Independent validator evaluation SHALL be used where field-level
stable comparison is required, with validators computing their own conclusion
from the same bounded evidence.

**FR-G-006** The system SHALL fail closed: if verification cannot complete, the
case does not resolve as accepted.

**FR-G-007** The system SHALL document exact consensus logic in
`docs/CONSENSUS.md`.

### Section H — Prompt Injection Defence

**User value:** A malicious repository cannot instruct ForkReason's decision.

**FR-H-001** All repository-controlled content SHALL be treated as inert data:
README, source comments, string constants, docs, HTML, commit messages, issues,
evidence submissions, challenge evidence, and repository metadata.

**FR-H-002** Untrusted content SHALL NEVER redefine task, system rules, verdict
enums, security constraints, output schema, or validator behaviour.

**FR-H-003** The system SHALL apply deterministic preprocessing before any model
use, minimal bounded excerpts, and strong delimiters around untrusted content.

**FR-H-004** Prompts SHALL explicitly instruct the model that evidence is inert
data that cannot alter the task or schema.

**FR-H-005** Model output SHALL be parsed strictly against a typed schema with
allowed enums, and results failing deterministic rule checks SHALL be rejected.

**FR-H-006** Validators SHALL evaluate independently of the leader.

**FR-H-007** The system SHALL fail closed on unparseable or off-enum output.

**FR-H-008** The system SHALL enforce input size limits and a source allowlist.

**FR-H-009** Chronology rules SHALL be enforced outside free-form prose.

**FR-H-010** Adversarial fixtures SHALL contain the required attack phrases in
README, code comment, string constant, HTML, commit metadata, and challenge
evidence, and SHALL verify that the SAME payload reaching every validator
context does not change the outcome.

**FR-H-011** Injection defence SHALL be documented in `docs/THREAT-MODEL.md` and
`docs/SECURITY-FINDINGS.md`.

### Section I — Backend & Job System

**User value:** Analysis is fast, survives failure, and never blocks.

**FR-I-001** The backend SHALL expose a versioned API under `/api/v1`, plus
`/health` and `/ready`.

**FR-I-002** Repository analysis SHALL NOT run inside a synchronous HTTP
request; it SHALL run in a durable background worker.

**FR-I-003** Jobs SHALL be durable in PostgreSQL and claimed with safe row
locking (`FOR UPDATE SKIP LOCKED`), with worker-concurrency control.

**FR-I-004** Analysis SHALL be idempotent: re-submitting the same immutable
repository pair SHALL NOT duplicate work.

**FR-I-005** The worker SHALL recover in-flight jobs after restart.

**FR-I-006** Analysis SHALL support cancellation and SHALL enforce a wall-clock
timeout that terminates analysis with a terminal state.

**FR-I-007** Progress reported to the frontend SHALL reflect real pipeline
stages only; the system SHALL NOT report fabricated percentages or stages.

**FR-I-008** The API SHALL validate requests, return stable error codes, and
SHALL NOT expose stack traces or internal paths.

**FR-I-009** Logs SHALL be structured and correlated by a request ID.

**FR-I-010** GitHub rate limits SHALL be handled with bounded retry and
backoff, degrading gracefully.

**FR-I-011** Configuration SHALL be read from the environment, validated at
startup with a concise actionable error, and backend secrets SHALL NEVER be
exposed through `NEXT_PUBLIC_*` variables.

**FR-I-012** The application database SHALL NOT become the authority over on-chain
revision or verdict state; chain-derived state SHALL be recorded with its
transaction reference.

### Section J — Frontend Product Experience

**User value:** The product is credible and pleasant to use on any device.

**FR-J-001** The system SHALL provide these routes: `/`, `/trace`,
`/analysis/[id]`, `/case/[id]`, `/case/[id]/evidence`, `/case/[id]/challenge`,
`/explore`, `/docs`, `/docs/[...slug]`, `/security`, `/roadmap`, and a custom
not-found surface.

**FR-J-002** The landing page SHALL contain two repository inputs in the hero
with a primary **Trace lineage** action and a secondary **Explore cases**
action, plus an interactive lineage visual reacting to pointer and focus.

**FR-J-003** The landing page SHALL include clearly labelled fixture-derived
proof, a Repo DNA explanation, a "Similarity is not lineage" section, a lineage
timeline demonstration, a "Why GenLayer" section, a challenge/revision section,
an open-source section, and a final CTA.

**FR-J-004** Fixture-derived content SHALL be labelled as such and SHALL NOT be
presented as live production history.

**FR-J-005** The analysis view SHALL display real pipeline stage states
(pending / working / complete / failed) and SHALL NOT animate fake consensus or
invent progress.

**FR-J-006** The case report SHALL answer, above the fold: what relationship was
found, how confident, in which direction, and why.

**FR-J-007** The case report SHALL progressively disclose: verdict explanation,
Repo DNA, Lineage Timeline, Evidence Graph, strongest evidence, conflicting
evidence, alternative explanations, shared upstream, GenLayer consensus,
revision history, challenge action, and share/export.

**FR-J-008** Each evidence card SHALL display evidence type, strength, why it
matters, and bounded provenance for both repositories.

**FR-J-009** The evidence graph SHALL be interactive, keyboard and screen-reader
accessible, SHALL provide a non-graph equivalent representation, and SHALL
degrade to a list/timeline representation on small screens.

**FR-J-010** `/explore` SHALL provide browsable public cases and search.

**FR-J-011** The design system SHALL use vivid semantic colour (not
grayscale-dominant, not purple/pink neon), controlled liquid-glass surfaces,
Instrument Sans for UI, and a monospace face for commits, hashes, and addresses.

**FR-J-012** Motion SHALL be restrained, fast, non-blocking, and SHALL respect
`prefers-reduced-motion`.

**FR-J-013** All surfaces SHALL provide loading, empty, error, degraded-dependency,
wallet-disconnected, wrong-chain, transaction-rejected, transaction-pending,
consensus-pending, challenged, and insufficient-evidence states.

**FR-J-014** The UI SHALL meet WCAG-oriented practice: semantic markup, keyboard
operability, visible focus, labels, descriptive errors, and readable contrast.

**FR-J-015** Heavy visualization code SHALL be lazy-loaded so unrelated surfaces
do not pay for it.

### Section K — Wallet & Chain Writes

**User value:** I approve and sign every state change with my own wallet.

**FR-K-001** Wallet UX SHALL use RainbowKit with Wagmi and Viem; GenLayer
operations SHALL use `genlayer-js`.

**FR-K-002** Reads SHALL use an account-free client where appropriate.

**FR-K-003** Every user state-changing GenLayer action SHALL be signed by the
user's browser wallet.

**FR-K-004** The system SHALL NOT hold a production server private key that signs
user actions, SHALL NOT use a hidden custodial signer, SHALL NOT sign as the
user from the backend, and SHALL NOT use a `PRIVATE_KEY` variable to silently
sign user transactions.

**FR-K-005** Before a write, the system SHALL verify wallet connection, correct
address, and correct chain, and SHALL request or handle a network switch.

**FR-K-006** The user SHALL see transaction intent, and fee/transaction errors
SHALL be understandable.

**FR-K-007** The UI SHALL display real transaction lifecycle state from the
actual client API and SHALL NOT fake consensus progression with timers.

**FR-K-008** The backend MAY prepare challenge payloads but SHALL NOT duplicate
user chain writes.

### Section L — Documentation

**FR-L-001** The repository SHALL contain README, LICENSE, CONTRIBUTING,
SECURITY, and CHANGELOG.

**FR-L-002** The repository SHALL contain `docs/ARCHITECTURE.md`,
`docs/CONSENSUS.md`, `docs/EVIDENCE-MODEL.md`, `docs/REPO-DNA.md`,
`docs/THREAT-MODEL.md`, `docs/SECURITY-FINDINGS.md`, `docs/TESTING.md`,
`docs/DEPLOYMENT.md`, `docs/DEPENDENCIES.md`, `docs/ROADMAP.md`, and
`docs/LIMITATIONS.md`.

**FR-L-003** An in-app documentation product SHALL exist under `/docs` covering
the listed V1 topics, deep-linkable, responsive, and technically accurate.

**FR-L-004** README SHALL NOT contain placeholder or stale text.

### Section M — Security

**FR-M-001** A real security review SHALL cover SSRF, command injection, path
traversal, symlink escape, git abuse, resource exhaustion, race conditions, job
replay, SQL injection, unsafe deserialization, oversized payloads, CORS, CSRF
where applicable, rate limiting, error leakage, secret leakage, unsafe logging,
and dependency risk on the backend; and XSS, unsafe markdown/HTML, unsafe
external links, wallet spoofing, wrong network, wrong account, duplicate
transaction, transaction rejection, secret bundling, CSP, clickjacking, and
mixed content on the frontend; and input bounds, unbounded storage, replays,
stale revisions, nondeterminism misuse, pre-consensus state mutation,
leader-only trust, malformed results, prompt injection, web failure, validator
divergence, and unexpected result types on the contract.

**FR-M-002** `SECURITY.md`, `docs/THREAT-MODEL.md`, and
`docs/SECURITY-FINDINGS.md` SHALL exist.

**FR-M-003** Release SHALL require zero open CRITICAL and zero open HIGH
findings; any accepted MEDIUM risk SHALL carry written rationale.

**FR-M-004** The findings report SHALL record ID, severity, component, finding,
impact, fix, status, and evidence.

### Section N — Testing

**FR-N-001** Backend unit tests SHALL cover URL normalization, input
constraints, commit pinning, repository bounds, sandboxing, fingerprinting,
chronology, bug-history signals, common upstream, alternative explanations,
evidence ranking, canonical manifest, hashing, job lifecycle, revision model,
and error paths.

**FR-N-002** Backend integration tests SHALL cover PostgreSQL, migrations,
worker, API, recovery, idempotency, rate-limit handling, and analysis timeout.

**FR-N-003** Fixture scenarios SHALL cover: real derivation with rename and
refactor; both sides deriving from a common upstream; independent
implementations of the same specification; insufficient history; prompt
injection; a declared fork; and a challenge that changes the revision.
Fixtures SHALL be non-trivial, not 20-line repositories.

**FR-N-004** Direct Mode SHALL be green before Studio Mode is attempted.

**FR-N-005** Direct Mode SHALL test every public method and cover: constructor,
reads, writes, pagination, input bounds, duplicates, invalid enums, manifest
hash, resolution, shared upstream, insufficient evidence, challenge, immutable
revision, stale revision, malformed model result, web error, LLM error,
validator disagreement, leader manipulation, prompt injection, and the same
injection reaching all validators.

**FR-N-006** Studio Mode SHALL exercise real multi-validator consensus and
SHALL NOT be replaced by mocks.

**FR-N-007** The security-critical test SHALL verify that a leader returning a
valid-looking but substantively incorrect verdict is REJECTED by validators.

**FR-N-008** Playwright SHALL test release-critical flows on Chromium, Firefox,
and WebKit across desktop, tablet, and 390/360/320px viewports, asserting no
console errors, no unhandled rejections, no 5xx, no hydration errors, no
horizontal overflow, sane focus order, and reduced-motion support.

**FR-N-009** A visual review loop SHALL capture screenshots at the required
viewports and rate surfaces against the stated rubric, iterating until the
honest score reaches 9.0/10.

### Section O — Deployment & Release

**FR-O-001** The application SHALL be deployed to `https://forkreason.bydx.fun`
behind nginx with TLS, HTTP→HTTPS redirect, an `/api` proxy, security headers,
compression, and correct proxy headers.

**FR-O-002** Web, API, and worker SHALL run as separate durable processes that
survive restart.

**FR-O-003** The exact final contract source SHALL be deployed to the official
GenLayer Studio flow, and network, contract address, deployment transaction
hash, git commit, and contract source hash SHALL be recorded.

**FR-O-004** Every public read method of the deployed contract SHALL be tested
and recorded with arguments, result, and PASS/FAIL; representative write
lifecycle transactions SHALL be exercised and their hashes recorded.

**FR-O-005** Where browser login or funding is genuinely unavailable, work SHALL
stop at that external boundary and SHALL NOT fabricate deployment evidence.

**FR-O-006** The repository SHALL be published publicly at
`github.com/0xbardia/ForkReason` on `main`, tagged `v1.0.0`, with a real release,
homepage, description, and topics where permitted.

**FR-O-007** Publication SHALL follow a secret scan, `.env` absence check, and
artifact cleanup; the working tree SHALL be clean.

**FR-O-008** A fresh clone into a new directory SHALL install, configure,
migrate, run backend, worker, frontend, backend tests, frontend tests,
contract Direct Mode tests, and a production build, following documentation
only.

**FR-O-009** The final remote `main` commit SHALL match the production release
candidate.

**FR-O-010** `FINAL_V1_REPORT.md` SHALL be produced with real measured values.

---

## Out of Scope for V1

These are explicitly NOT V1 and go to `docs/ROADMAP.md`:

- Private repositories and authenticated repository access.
- Non-GitHub hosts (GitLab, Bitbucket).
- Package-registry lineage (npm, PyPI) and CI integration.
- Team workspaces, organizational API, reusable attestations.
- Automated ownership or authorship verification.
- Any legal determination of infringement.

## Dependencies

- **GitHub REST API** — repository metadata, commit resolution, contents.
- **Git (plumbing commands, argument arrays only)** — snapshot and history.
- **PostgreSQL** — application state and durable job queue.
- **GenLayer Studio** — Direct Mode, Studio Mode, and contract deployment.
- **RainbowKit / Wagmi / Viem / genlayer-js** — wallet and chain access.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Repository analysis becomes RCE | Critical | No execution, argument arrays, explicit limits, path/symlink containment (FR-A-005..007) |
| Prompt injection steers consensus | Critical | Data-inert framing, bounded excerpts, strict parsing, independent validators, adversarial fixtures (FR-H-*) |
| Leader-only trust yields one model's opinion | High | Substance verification, independent validator evaluation, fail-closed (FR-G-*) |
| Fabricated confidence | High | Bucket confidence, no calibrated probability, document absence of calibration (FR-E-002/003) |
| Boilerplate matches masquerade as lineage | High | Rarity weighting, weak signals stay weak (FR-B-008) |
| Worker crash loses analysis | Medium | Durable jobs, recovery on start, idempotency (FR-I-003..005) |
| Server becomes custodial for user writes | Critical | Browser-only signing, no server signer (FR-K-003/004) |
| GitHub rate limits stall analysis | Medium | Cached snapshots, bounded retry with backoff (FR-A-008, FR-I-010) |
| Chain consensus unavailable in environment | High | Stop at the external boundary; never fabricate (FR-O-005) |

## Clarifications Resolved

1. **Direction** — the ordered origin→target relationship a verdict asserts.
   Non-directional verdicts state no direction.
2. **Confidence** — a bucket only; no probability is displayed anywhere.
3. **Authority** — chain state is authoritative for revision/verdict; the
   database indexes and caches it.
4. **Fixture labelling** — fixture-derived content is always labelled and never
   presented as live history.
5. **Deployment gap** — if Studio deployment requires unavailable browser
   credentials, the report stops at that boundary and says so.

## Requirements Traceability

Every FR maps to at least one verification method and is exercised by the
acceptance scenarios described in `tasks.md`.