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

## Hosted deployment — NOT COMPLETED

The frozen source above was **not** deployed to `studio.genlayer.com`.

Two independent blockers, both requiring credentials or input this session does
not have:

1. **Hosted RPC refuses server-side requests.** `POST https://studio.genlayer.com/api`
   from this host returns **HTTP 403 Forbidden** (and a bare GET returns 405).
   The Studio endpoint is reachable only from a browser session that carries
   the user's authenticated context.
2. **The CLI requires an interactive keystore password.** The documented
   non-interactive path

   ```
   genlayer deploy --contract contracts/forkreason_registry.py \
                   --rpc https://studio.genlayer.com/api
   ```

   prompts `? Enter password to decrypt keystore:` and fails on attempt 1.
   Guessing or bypassing that password is not acceptable.

3. **The web editor could not be driven programmatically.** Monaco is not exposed
   on `window`, the bundle is minified with no React fiber handle on the editor
   node, the page CSP blocks fetching source from the host, and both a synthetic
   `ClipboardEvent` paste and `document.execCommand('insertText')` are ignored.
   Only genuine OS-level keystroke input would load the 27 KB source, which is
   not something this session can emit.

Consequently there is **no contract address, no deployment transaction hash, and
no deployed read-method result**. None is claimed. The API reports this honestly
rather than pretending:

```json
GET /api/v1/chain/contract
{"network":"studionet","address":"","deployed":false,"source_sha256":null}
```

The frontend reflects the same truth: preparing a challenge shows the full
transaction intent and states that the contract is not configured on this
deployment, so signing is refused rather than silently discarded.

### What is verified about the contract

- Direct Mode: 51/51 against the Direct Mode VM.
- Studio Mode: 8/8 against a real 5-validator GLSim network with leader rotation.
- `genvm-lint`: 3 checks pass.
- Source SHA-256 is recorded above and is reproducible with `sha256sum`.

What is **not** verified is behaviour on the hosted Studio network specifically.
