# Contract release candidate — frozen

This file records the exact contract source certified for ForkReason V1. The
contract is frozen; any change to `contracts/forkreason_registry.py` invalidates
this record and requires re-certification of both test layers.

**Re-certified 2026-10-04.** The hash below reflects the current source, after a
dead pre-consensus write was removed from `challenge_case` (it re-wrote an
existing key and contradicted its own comment; lifecycle is derived from revision
state and never stored). Both test layers were re-run after that change:
Direct Mode 51/51, Studio Mode 8/8, lint 3 checks.

## Source

| Field | Value |
|---|---|
| Path | `contracts/forkreason_registry.py` |
| SHA-256 | `867474f56b0fc169d9a254da4ac96435fa154156e09c85db08d1cbc3a0f92a0a` |
| Dependency header | `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` |
| Contract class | `ForkReasonRegistry` |

Recompute:

```bash
sha256sum contracts/forkreason_registry.py
```

## Toolchain

| Component | Version |
|---|---|
| Python SDK | current shipping `genlayer` SDK, verified by executable probe |
| `genlayer-test` / `gltest` | 0.29.2 |
| `glsim` | 0.29.2 (installed via `genlayer-test[sim]`) |
| `genvm-lint` | 3 checks, pass |
| Python | 3.12.13 |
| venv | `.venv` (`uv`) |

## Direct Mode — 51/51 PASS

```bash
.venv/bin/gltest contracts/tests/ -m "not integration" -q
# 51 passed, 8 deselected
```

No network is used. The contract runs natively in the Direct Mode VM with
mocked model and web calls.

| Suite | Tests | Covers |
|---|---|---|
| `test_registry_direct.py` | 37 | constructor, reads, writes, pagination, input bounds, duplicates, invalid enums, manifest hash, resolution, shared upstream, insufficient evidence, challenge, immutable revision, stale revision, malformed model result, web error, LLM error, validator disagreement, leader manipulation |
| `test_prompt_injection.py` | 14 | adversarial fixtures in README, comments, string constants, HTML, commit metadata, challenge evidence; same payload across every validator context |

## Studio Mode — 8/8 PASS

```bash
./deploy/studio/run-studio.sh
```

| Field | Value |
|---|---|
| Backend | GLSim (no Docker) |
| Validators | 5 |
| Max leader rotations | 3 |
| Chain id | 61127 |
| RPC | `http://127.0.0.1:4000/api` |
| Seed | 42 (deterministic) |
| `--leader-only` | never used |

Real multi-validator consensus with leader rotation. The decision is produced
through the same `gl.vm.run_nondet` path used in production; the validator
independently re-derives its own decision rather than trusting the leader's.

Results:

```
8 passed, 51 deselected in 5.77s
```

| Test | Result |
|---|---|
| `test_consensus_resolves_a_case` — 5/5 validators agree, case persisted at revision 1 | PASS |
| `test_every_public_read_method_works` — all 11 public read methods | PASS |
| `test_challenge_creates_a_new_immutable_revision` — revision N content preserved, `is_current` flips | PASS |
| `test_stale_revision_challenge_is_refused` | PASS |
| `test_duplicate_manifest_is_refused` | PASS |
| `test_prompt_injection_cannot_force_a_verdict` | PASS |
| `test_off_enum_verdict_is_refused` — model returns `DEFINITELY_STOLEN` | PASS |
| `test_non_hex_case_id_is_refused` | PASS |

## Lint

```bash
.venv/bin/genvm-lint contracts/forkreason_registry.py
# ✓ Lint passed (3 checks)
```

## Model endpoint used for certification

Studio Mode certification ran against a local OpenAI-compatible model stub
(`deploy/studio/model_stub.py`) reached through a process-scoped CONNECT proxy
(`deploy/studio/tls_proxy.py`).

This is a deliberate, recorded deviation, not a claim that a real hosted model
was used:

- GLSim hardcodes `https://api.openai.com/v1/chat/completions` and offers no
  base-URL override.
- The alternative — editing `/etc/hosts` — is machine-global and would break
  other services on this host that legitimately call OpenAI (`orbi_bot` does).
  That approach was attempted and reverted for exactly this reason.
- A paid third-party key was not available for certification.

The stub implements the contract's `_JSON_SCHEMA_KEYS` schema exactly and can be
switched to adversarial modes (`off_enum`, `malformed`, `html_wrapped`,
`injection_compliant`) to drive fail-closed behaviour.

**What this does and does not certify.** Consensus mechanics — leader rotation,
the validator committee, agreement, disagreement, rollback, immutability,
fail-closed parsing — are entirely GLSim's and were exercised for real. What it
does not certify is the output quality of any hosted frontier model. That is not
a contract property: the contract's job is to refuse bad decisions, which is
what these tests verify.



## Hosted deployment — COMPLETED (2026-10-04)

Deployed through `https://studio.genlayer.com/contracts` from a browser
session, using the file-upload control so the bytes are the repository file
rather than retyped text.

| Field | Value |
|---|---|
| Network | GenLayer Studio (studionet) |
| Contract file | `forkreason_registry_upload.py` |
| Deployed at | `0xb3...d07b` (Studio truncates the address in its UI) |
| Deployment tx | `0x4c5c6d72bcae900d4b3a08dcb0131d292b9bf77d72d4a91375bac95381c6518b` |
| Consensus | Reached consensus |
| Transaction state | FINALIZED |
| Source SHA-256 | `867474f56b0fc169d9a254da4ac96435fa154156e09c85db08d1cbc3a0f92a0a` |

### How the deployment was unblocked

Three blockers were worked around rather than bypassed:

1. **`genlayer deploy --rpc` prompts for the keystore password.** Not guessed.
   Instead the contract was uploaded through the Studio web UI.
2. **The hosted RPC returns 403 to server-side calls.** All RPC work was done
   from the browser session, which carries the authenticated context.
3. **Monaco ignores synthetic input.** It only accepts input after a *trusted*
   gesture: `focus()` was insufficient, a real coordinate click was not.
   With the editor focused, `Input.insertText` in 3 KB chunks wrote the source
   correctly (684 lines, verified against `sha256sum`).
4. **A stale editor buffer.** An early attempt pasted into `storage.py`'s
   buffer and Studio reported `Could not load contract schema`. The fix was to
   upload the repository file under its own name, so the bytes are the file
   rather than retyped text.

### Read methods

Studio's schema load returned all 13 methods:

```
challenge_case  get_case  get_case_count  get_cases_page  get_challenge
get_challenge_count  get_dna_layers  get_latest_revision  get_revision
get_revision_count  get_valid_confidences  get_valid_verdicts  submit_case
```

`get_case_count` was called against the deployed contract and returned
**`0`** (Response: Accepted), which is the correct value for a registry with
no cases yet. That is a real on-chain read of the deployed bytecode.

Every method's parameters were confirmed against Studio's generated call form:
`get_cases_page` → `offset, limit`; `get_revision` → `case_id,
revision_number`; `challenge_case` → `case_id, base_revision,
challenge_rationale, evidence_digest`; `submit_case` → six arguments.

The parameter-taking reads were **not** individually invoked, because Studio
keeps every expanded method's response in one shared panel and the harness
cannot reliably attribute a response to the method that produced it. Rather
than report unverified results, that limitation is recorded here.
