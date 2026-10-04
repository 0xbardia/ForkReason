# Testing

Testing ran continuously during development rather than at the end. Most of the
bugs this project has had were found by executing something, not by reading it.

## Release suite

| Suite | Command | Result |
|---|---|---|
| Backend | `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests/ -q` | **205 passed** |
| Contract, Direct Mode | `.venv/bin/gltest contracts/tests/ -m "not integration" -q` | **51 passed** |
| Contract, Studio Mode | `./deploy/studio/run-studio.sh` | **8 passed** |
| Contract lint | `.venv/bin/genvm-lint contracts/forkreason_registry.py` | 3 checks passed |
| Frontend typecheck | `cd apps/web && npx tsc --noEmit` | clean |
| Frontend build | `cd apps/web && npm run build` | 20 routes |
| Visual QA | `cd apps/web && node scripts/capture.mjs` | 40 captures, 0 overflow, 0 5xx |

## Direct Mode

51 tests across two files. No network is required — the contract runs natively in
the Direct Mode VM with mocked model and web calls.

| File | Tests | Focus |
|---|---|---|
| `test_registry_direct.py` | 37 | Constructor, reads, writes, pagination, bounds, duplicates, invalid enums, manifest hash, resolution, shared upstream, insufficient evidence, challenge, immutable revision, stale revision, malformed model result, web error, LLM error, validator disagreement, leader manipulation |
| `test_prompt_injection.py` | 14 | Adversarial fixtures in README, code comments, string constants, HTML, commit metadata, challenge evidence; the same payload across every validator context |

Direct Mode can prove validator independence without a network at all: swap the
model mock between the leader call and the validator call to show the validator
independently disagrees.

## Studio Mode

Real multi-validator consensus, run through GLSim. No Docker required.

```bash
./deploy/studio/run-studio.sh
```

Which starts:

- a local OpenAI-compatible **model stub** (`deploy/studio/model_stub.py`);
- a **CONNECT proxy** (`deploy/studio/tls_proxy.py`) that redirects GLSim's
  hardcoded `api.openai.com` to the stub, scoped to the GLSim process alone;
- **GLSim** with 5 validators and 3 leader rotations on seed 42.

`--leader-only` is never used: it silently no-ops off Studio-based RPCs and
would bypass the committee, which is the entire point of a Studio Mode run.

| Test | What it proves |
|---|---|
| `test_consensus_resolves_a_case` | 5/5 validators agree; the case persists at revision 1 |
| `test_every_public_read_method_works` | All 11 public read methods |
| `test_challenge_creates_a_new_immutable_revision` | Revision N content preserved; only `is_current` flips |
| `test_stale_revision_challenge_is_refused` | A superseded revision cannot be challenged |
| `test_duplicate_manifest_is_refused` | Replay does not create a second case |
| `test_prompt_injection_cannot_force_a_verdict` | Injected text cannot force a verdict at consensus level |
| `test_off_enum_verdict_is_refused` | A model returning `DEFINITELY_STOLEN` is refused |
| `test_non_hex_case_id_is_refused` | Bounds enforced by the contract, not the caller |

### What the model stub is and is not

The stub implements the contract's exact schema and can be switched to
adversarial modes (`off_enum`, `malformed`, `html_wrapped`,
`injection_compliant`).

It certifies **consensus mechanics**: leader rotation, the validator committee,
agreement, disagreement, rollback, immutability, fail-closed parsing. Those are
GLSim's and were exercised for real. It does **not** certify the output quality
of any hosted frontier model — which is not a contract property. The contract's
job is to refuse bad decisions, and that is what these tests verify.

## Fixture scenarios

| Scenario | Expected | Covered in |
|---|---|---|
| A — real derivation with rename and refactor | `LIKELY_DERIVED` / `HEAVILY_DERIVED` | `test_forensic_engine.py` |
| B — both sides derive from one upstream | `SHARED_UPSTREAM` | `test_forensic_engine.py`, Studio Mode |
| C — independent implementations of one spec | `INDEPENDENT` / `INSUFFICIENT_EVIDENCE` | `test_forensic_engine.py` |
| D — not enough history | `INSUFFICIENT_EVIDENCE` | `test_forensic_engine.py` |
| E — prompt-injection repository | Malicious instructions ignored | `test_prompt_injection.py`, Studio Mode |
| F — declared legitimate fork | `DECLARED_FORK` | contract enum coverage |
| G — conflicting evidence changes the verdict | Revision preserved, new verdict | Studio Mode challenge test |

## Visual QA

`scripts/capture.mjs` captures every required surface at 1440, 1280, 390 and
360 px and fails loudly on console errors, horizontal overflow and 5xx. It also
captures the case report, evidence explorer and challenge against a **real**
case, because the signature screen should never be reviewed against an empty
state.

```
40 captures, 0 overflow, 0 5xx
```

## Bugs that only executing found

Worth recording, because each was invisible in review:

1. **`claim_job` cleared the lease in a `finally`** — a crashed worker left a
   `running` job permanently unrecoverable.
2. **Boilerplate scored `structural_similarity = 1.000`** on two unrelated
   twenty-line Python projects sharing only stdlib imports.
3. **Chronology alone produced `LIKELY_DERIVED`** on two unrelated projects.
4. **GitHub's repo payload has no `default_branch_commit`** — validation failed
   for every real repository.
5. **`POST_DERIVATION_DIVERGENCE` triggered on *low* similarity.**
6. **CSP had no nonce** — the page rendered completely blank.
7. **PM2 inherited the Studio proxy** — every production GitHub call was refused.
8. **`lib/api.ts` baked a localhost origin into production bundles.**
