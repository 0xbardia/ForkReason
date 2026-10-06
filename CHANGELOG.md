# Changelog

All notable changes to ForkReason are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Initial registration is a complete, tested path.** The case page requests
  a typed six-string payload (`buildSubmitCaseArgs`, pinned against the shipping
  `submit_case(origin_repo, origin_commit, target_repo, target_commit,
  manifest_hash, evidence_digest)` ABI), checks wallet, account and network,
  and has the visitor's browser wallet sign it. Analysis is stored as
  provisional revision 0; the public Case becomes chain-backed only after
  reconciliation.
- **Chain reconciliation.** The API records the wallet's transaction id, and the
  worker verifies network, contract, calldata, sender, execution result and
  `LATEST_FINAL` contract state with the read-only GenLayer SDK before one
  atomic database transaction appends revision N+1 and advances the Case
  pointer. Prior revisions are never modified; duplicate, stale, wrong-case,
  wrong-contract and wrong-network observations are rejected.
- Unit, API-integration and real-browser (Playwright, decoding the signed
  GenLayer calldata) tests for both lifecycles.

### Fixed
- **Werkzeug/Requests asymmetric false positive.** Werkzeug → Requests was
  HEAVILY_DERIVED / HIGH while Requests → Werkzeug was INDEPENDENT. Divergence
  is now scored only when a derivation is itself supported, and the evidence
  layer no longer counts HTTP header names, MIME types, bare routes, character
  alphabets, interpreter pseudo-names, example URLs, dotfiles or convention
  module names as lineage. Both directions are INDEPENDENT; see
  `test_requests_werkzeug_lineage_is_stable_in_both_directions`.
- **Stale analyses were replayed forever.** Jobs were keyed on the pinned pair
  alone, so a pair analysed by an older engine kept its old verdict (production
  still served Requests → Werkzeug as LIKELY_DERIVED). The engine version is now
  part of the job key, and an unregistered provisional analysis is replaced by a
  fresh one; registered cases and cases with a registration in flight never are.
- A transaction hash the RPC has not indexed yet is retried for 15 minutes
  instead of being rejected, and unverified claims are bounded per case.

## [1.0.0] — 2026-10-04

First public release. ForkReason reconstructs software lineage from two public
GitHub repositories and records the finding as an immutable revision through
GenLayer consensus.

### Added

**Forensic engine**
- Eight-stage pipeline: repository snapshots, commit history, structural
  fingerprints, historical signals, shared upstream, alternative explanations,
  evidence manifest, consensus preparation.
- Six Repo DNA layers: Code, Architecture, History, Bug, Test, Language.
- Canonical, deterministic Evidence Manifest with a reproducible SHA-256.
- Six verdicts, including `INSUFFICIENT_EVIDENCE` as a first-class outcome.
- Shared-upstream discovery from declared fork parents and distinctive
  vocabulary.
- Boilerplate filtering so common framework tokens cannot become evidence.
- Chronology enforced in Python: a target whose history predates the origin's
  cannot have been derived from it.

**Safe repository intake**
- `git archive` of tracked blobs at a pinned commit. No working tree, no hooks,
  no submodule content, no repository code executed.
- Rejects path traversal, symlink escape, hardlinks, device nodes, FIFOs,
  decompression bombs, oversized files and excessive history depth.
- Argument-array subprocess calls with `shell=False` and a sanitized
  environment.
- Explicit bounds on repository size, file count, file size, commit depth,
  evidence count and wall-clock time.

**GenLayer Intelligent Contract**
- `ForkReasonRegistry` with append-only revisions, challenge support, bounded
  inputs, enum validation, duplicate and replay refusal, and stale-revision
  challenge rejection.
- Consensus via `gl.vm.run_nondet` with a custom validator that independently
  re-derives its decision instead of trusting the leader's.
- Storage written only after consensus returns, in deterministic execution.

**Backend service**
- Versioned API under `/api/v1` with stable error codes.
- PostgreSQL-backed durable job queue using `FOR UPDATE SKIP LOCKED`, leases,
  idempotency keys and stale-lease recovery.
- Alembic migrations, structured logging with correlation IDs, health and
  readiness endpoints.

**Frontend**
- Vivid Liquid Forensics design system with semantic colour roles.
- Landing page with an illustrative lineage-timeline fixture.
- Trace flow, real pipeline progress, case report, evidence explorer with
  filters and facets, challenge flow, Explore and search.
- Twenty deep-linkable documentation pages with a searchable sidebar.
- RainbowKit wallet boundary: reads are walletless, every write is signed by
  the user.

**Security**
- Prompt-injection release gate with adversarial fixtures in README, code
  comments, string constants, HTML, commit metadata and challenge evidence.
- A test that presents the demanded verdict to every validator and asserts none
  accept it.
- Per-request CSP nonce, HSTS, `frame-ancestors 'none'`, strict referrer policy.

### Verification at release

| Suite | Result |
|---|---|
| Backend (`pytest`) | 219 passed |
| Contract, Direct Mode (`gltest`) | 51 passed |
| Contract, Studio Mode (GLSim, 5 validators) | 8 passed |
| `genvm-lint` | 3 checks passed |
| Visual QA | 40 captures, 0 problems |
| `npm audit` | 0 critical, 0 high |

### Security posture

Zero open Critical, zero open High. See
[`docs/SECURITY-FINDINGS.md`](docs/SECURITY-FINDINGS.md).

### Known limitations

Public GitHub repositories only; weak chronology on shallow history; monorepos
analyzed as a single repository; heuristic shared-upstream discovery when no
fork parent is declared; no authorship inference. Full list in
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).
