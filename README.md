<div align="center">

# ForkReason

**Trace where software really came from.**

ForkReason compares two repositories, reconstructs their development lineage
from code, history, bugs and tests, weighs the innocent explanations against the
obvious one, and records the conclusion as an immutable revision through
[GenLayer](https://genlayer.com) consensus.

[Live site](https://forkreason.bydx.fun) · [Documentation](https://forkreason.bydx.fun/docs) · [Security](https://forkreason.bydx.fun/security)

[![contract](https://img.shields.io/badge/contract-verified-12E6A7?style=flat-square)](#genlayer-contract)
[![direct mode](https://img.shields.io/badge/direct%20mode-51%20tests-13CFF4?style=flat-square)](#testing)
[![studio mode](https://img.shields.io/badge/studio%20mode-8%20tests-397BFF?style=flat-square)](#testing)
[![backend](https://img.shields.io/badge/backend-241%20tests-FFC857?style=flat-square)](#testing)
[![license](https://img.shields.io/badge/license-AGPL--3.0-C8FF4A?style=flat-square)](#license)

</div>

---

## The problem

Two repositories share code. That is the beginning of a question, not the
answer.

Shared code has uninteresting explanations: a common framework, a specification
both projects implemented, a shared upstream nobody mentioned, an unfashionable
week in 2014. Deciding between them requires knowing **which came first** and
**what history still remembers** — and almost no tool looks at either.

ForkReason does. It reads both commit histories, finds signals that first appear
in one repository before the other, evaluates every competing explanation
including the ones that exonerate, and refuses to answer when the evidence
does not support an answer.

**ForkReason is not a plagiarism detector.** It never claims a repository was
stolen, infringing, or illegal. It reports development lineage. Those are
different claims and it keeps them apart.

## What it does

- **Pins immutable commits.** Analysis is always against a specific commit, so
  a finding can be recomputed and checked.
- **Reads six evidence layers** — Code, Architecture, History, Bug, Test and
  Language — and refuses to let any single one carry a verdict.
- **Weights by rarity.** Framework boilerplate is filtered to zero before it can
  become evidence, so `import os` never counts as lineage.
- **Enforces chronology in code.** A target whose history predates the origin's
  cannot have been derived from it, whatever the similarity scores say.
- **Evaluates competing explanations** and prefers the one the evidence fits —
  including `SHARED_UPSTREAM`, which exonerates.
- **Returns `INSUFFICIENT_EVIDENCE`** when that is the truth.
- **Records an immutable revision** on GenLayer, and lets anyone challenge it.

## Repo DNA

Every repository is measured across six independent dimensions.

| Layer | Derives | Why it matters |
|---|---|---|
| **Code** | Normalized structure, uncommon constants, ordered tokens | Constants survive refactors that rename everything |
| **Architecture** | Directory topology, module boundaries, subsystem names | The same decomposition implies the same thinking |
| **History** | Commit chronology, first occurrence, implementation order | This is what turns similarity into direction |
| **Bug** | Shared defect signatures, fix timing, pre-fix behaviour | Nobody independently writes the same unusual mistake twice |
| **Test** | Distinctive test names, fixtures, regression scenarios | Tests travel with the implementation they cover |
| **Language** | Naming, comments, unusual terminology, doc phrasing | Shared distinctive phrasing is hard to produce independently |

A bug that existed in one repository before the other appeared is a timestamp
you cannot forge. That is the signal the engine weights most heavily.

## Verdict, not accusation

| Verdict | Means |
|---|---|
| `INDEPENDENT` | Overlap is consistent with two projects implementing the same specification |
| `SHARED_UPSTREAM` | A common ancestor explains the overlap better than derivation does |
| `DECLARED_FORK` | One repository declares the other as its upstream — a legitimate, recorded relationship |
| `LIKELY_DERIVED` | Chronology and historical evidence support origin → target |
| `HEAVILY_DERIVED` | A real lineage, substantially diverged since |
| `INSUFFICIENT_EVIDENCE` | The evidence supports no conclusion either way |

Confidence is reported as `LOW` / `MEDIUM` / `HIGH`, never as a percentage.
There is no calibration methodology, so a number would imply a precision that
does not exist.

## Architecture

```
                  nginx (TLS, security headers)
                     │
        ┌────────────┴────────────┐
        │                         │
  forkreason-web            /api proxy
  Next.js :3112                   │
                            forkreason-api
                            FastAPI :8421 ──┐
                                                │
                            PostgreSQL ────────┤
                            (durable queue)   │
                                                │
                            forkreason-worker
                            (no listener)
```

| Process | Responsibility |
|---|---|
| `forkreason-web` | Next.js frontend |
| `forkreason-api` | Validation, job creation, case and evidence reads |
| `forkreason-worker` | Runs the forensic pipeline, never inside a request |

Analysis runs in a durable PostgreSQL-backed queue claimed with
`FOR UPDATE SKIP LOCKED`. No Redis: the server already runs PostgreSQL, and one
fewer broker is one fewer failure mode. A crashed worker's job is recovered when
its lease expires.

**The chain boundary is strict.** The database indexes chain state; it never
becomes the authority over on-chain revision or verdict state.

## Repo DNA → evidence → consensus

Every analysis produces a canonical, bounded **Evidence Manifest**: pinned
repositories and commits, chronology facts, evidence items with strength,
conflicting signals, every alternative explanation, and shared-upstream
candidates. It is canonicalized and hashed, so anyone with the same two commits
can recompute the hash and confirm nothing changed between analysis and record.

## GenLayer contract

`ForkReasonRegistry` is a GenLayer Intelligent Contract written in Python. Its
ABI is deliberately small:

```python
# Writes
submit_case(origin_repo, origin_commit, target_repo, target_commit,
            manifest_hash, evidence_digest)
challenge_case(case_id, base_revision, challenge_rationale, evidence_digest)

# Reads
get_case · get_case_count · get_latest_revision · get_revision
get_revision_count · get_challenge · get_challenge_count
get_cases_page · get_dna_layers · get_valid_verdicts · get_valid_confidences
```

### Consensus model

A lineage finding is a judgement about the past. One model reading two READMEs is
not verifiable, so the decision goes through GenLayer's Equivalence Principle
with **independent validators**.

The validator does not re-parse the leader's conclusion. It forms its **own**
decision from the same evidence, applies the deterministic guards to it, and
compares the stable field tuple:

```
verdict · confidence bucket · direction · shared_upstream
independent_origin_plausibility · strongest evidence classes
```

Prose explanations are never compared for equality — two validators can reach
the same conclusion and describe it differently. That is agreement, not noise.

A leader is **never** accepted because its output parses. A well-formed but
substantively wrong verdict is rejected. If verification cannot complete, the
case does not resolve as accepted.

```python
def _decide(evidence_digest: str) -> str:
    def leader_fn() -> str:
        return gl.nondet.exec_prompt(_TASK_RULES + _evidence_block(evidence_digest))

    def validator_fn(result) -> bool:
        # Re-derive our own decision; do not trust the leader's.
        try:
            parsed_leader = _parse_decision(gl.vm.unpack_result(result))
            _deterministic_guard(parsed_leader)
            mine = _parse_decision(leader_fn())
            _deterministic_guard(mine)
        except Exception:
            return False                      # fail closed
        return _stable_tuple(parsed_leader) == _stable_tuple(mine)

    return gl.vm.run_nondet(leader_fn, validator_fn)
```

Storage is written **only** after consensus returns, in deterministic execution.

## Wallet transactions

Reads need no wallet. Every user state-changing GenLayer action is signed by the
visitor's own browser wallet through RainbowKit. ForkReason's server holds no
key that can act for a user, and there is no custodial signer.

## Prompt injection is treated as a security gate

Consensus does **not** automatically solve prompt injection. If every validator
reads the same malicious README and obeys it, they agree — and the committee
reports success while producing the wrong answer.

ForkReason treats all repository-controlled content as inert data:

1. Deterministic preprocessing strips comments and string literals before any
   structural comparison.
2. Only bounded excerpts reach the model — never a whole repository.
3. Untrusted content is fenced inside explicit delimiters.
4. The inert-data instruction is stated as an absolute rule above the evidence.
5. Strict typed parsing against an allowed enum set.
6. Deterministic guards (chronology, verdict/confidence contradictions) run in
   Python, not prose.
7. Independent validator evaluation.
8. Fail closed on anything unparseable or off-enum.

The adversarial suite places the mandated attack phrases in a README, a code
comment, a string constant, HTML, commit metadata and challenge evidence — then
asserts the verdict is refused. A separate test hands the demanded verdict to
**every** validator and asserts none of them accept it.

## Installation

Requires Python 3.12+, Node.js 20+, and PostgreSQL 14+.

```bash
git clone https://github.com/0xbardia/ForkReason.git
cd ForkReason

python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env      # then edit DATABASE_URL
```

Database migrations:

```bash
.venv/bin/python -m alembic upgrade head
```

### Running it

```bash
# API
PYTHONPATH=apps/api .venv/bin/python -m uvicorn forkreason.main:app \
  --host 127.0.0.1 --port 8421

# Worker
PYTHONPATH=apps/api .venv/bin/python -m forkreason.jobs.runner

# Frontend
cd apps/web && npm ci && npm run dev
```

In production, `ecosystem.config.cjs` runs all three under PM2 and nginx
terminates TLS.

## Environment

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `GITHUB_TOKEN` | Optional; raises the API rate limit |
| `ANALYSIS_MAX_REPO_MB` / `_MAX_FILE_MB` / `_MAX_FILES` / `_MAX_COMMITS` | Intake bounds |
| `ANALYSIS_TIMEOUT_SECONDS` | Per-analysis wall clock ceiling |
| `ANALYSIS_WORKER_CONCURRENCY` | Parallel analyses per worker |
| `NEXT_PUBLIC_GENLAYER_NETWORK` / `_RPC_URL` / `_CONTRACT_ADDRESS` | Chain config for the wallet |

`NEXT_PUBLIC_*` values are inlined into the client bundle at build time.
Backend secrets are never exposed there.

## Testing

```bash
# Backend — 241 tests
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests/ -q

# Contract, Direct Mode — 51 tests, no network needed
.venv/bin/gltest contracts/tests/ -m "not integration" -q

# Contract, Studio Mode — 8 tests, real multi-validator consensus
./deploy/studio/run-studio.sh
```

Studio Mode runs a real 5-validator GLSim network with leader rotation. It
never uses `--leader-only`, which would bypass the committee entirely. See
[`contracts/RELEASE_CANDIDATE.md`](contracts/RELEASE_CANDIDATE.md) for the
frozen source hash and full results.

## Deployment

`https://forkreason.bydx.fun` runs nginx → Next.js, with `/api` proxied to
FastAPI. The API, worker and PostgreSQL are loopback-only.

- HTTP redirects to HTTPS
- Per-request CSP nonce; no `unsafe-inline` for scripts
- HSTS, `nosniff`, `frame-ancestors 'none'`, strict referrer policy
- Immutable caching for content-hashed assets, `no-store` for HTML
- 1 MB request body limit; analysis is queued, never run inline

## Security

Report a vulnerability privately via GitHub Security Advisories on the
repository. See [`SECURITY.md`](SECURITY.md) for the disclosure process and
[`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md) for adversaries and controls.

**Repositories are treated as hostile input.** ForkReason never executes
analyzed repository code, never runs `npm install` inside a repository, never
follows symlinks out of the sandbox, and shells out only with argument arrays
and `shell=False`. Intake is `git archive` of tracked blobs at a pinned commit —
no working tree, no hooks, no submodule content.

## Limitations

Real limits, stated plainly:

- Public GitHub repositories only in V1.
- Squashed or shallow history weakens chronology; the report says so.
- Monorepos are analyzed as one repository.
- Shared-upstream discovery is heuristic when no fork parent is declared.
- Authorship, ownership and intent are never inferred.
- Gencode, minified output and vendored trees are inventoried, not analyzed.
- No legal conclusions, ever.

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Contributing

Bug fixes and additional fixture scenarios are the most useful contributions. A
change to evidence scoring should include the fixture it was tuned against.

```bash
# Fixtures live in apps/api/tests/; add a scenario and its expected verdict.
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests/ -q
```

## License

[AGPL-3.0](LICENSE). The copyleft matters here: a forensic tool that claims to
be verifiable should not be forkable into something unverifiable.
