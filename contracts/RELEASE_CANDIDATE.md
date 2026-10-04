# Contract release candidate — frozen

This file records the exact contract source certified for ForkReason V1. The
contract is frozen; any change to `contracts/forkreason_registry.py` invalidates
this record and requires re-certification of both test layers.

## Source

| Field | Value |
|---|---|
| Path | `contracts/forkreason_registry.py` |
| SHA-256 | `bb80aa8826ea894bbba3a42da4657aea9cb0535cb8514fe75eae185f8016d5ee` |
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