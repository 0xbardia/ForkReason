# ForkReason V1 — independent verification (PARTIAL)

Verification run: 2026-10-04. Executed, not asserted.

This is NOT a final certification. Several mandatory phases were not completed,
and one known defect class is documented below as open.

## Commits produced by this verification

| Commit | Defect found | Root cause |
|---|---|---|
| `5a3e2c1` | Test TLS private key pushed to public history | `deploy/studio/certs/*.pem` committed at `1149af9`, deleted at `b8a5386`, but retrievable from history |
| `e24a0b8` | Startup config gate was dead code | `validate_startup()` was never called; `database_url` had a hardcoded DSN masking the missing variable |
| `27ee738` | Fresh-clone install failed outright | hatchling rejects a git direct reference in an optional-dependency group; `tls_proxy.py` hardcoded `/root/ForkReason` |
| `27ee738` | Undeclared dependency | `genvm-linter` was installed but declared in no extra, so a clone could not run a documented gate |
| `1d936e0` | Commit-message vocabulary carried derivation verdicts | 151 shared English words scored 0.80 HIGH |

## Gates executed and passing at `1d936e0`

| Gate | Result |
|---|---|
| Repository integrity | clean tree, no tracked secrets |
| Backend tests | **225 passed** |
| Backend lint (pyflakes) | clean |
| Contract Direct Mode | **51 passed** |
| Prompt injection | **14 passed** |
| genvm-lint | 3 checks |
| Studio Mode (GLSim, 5 validators) | **8 passed** |
| Fresh-clone Studio Mode | **8 passed** |
| Fresh-clone backend | **225 passed** |
| Fresh-clone Direct Mode | **51 passed** |
| Fresh-clone frontend build | 107 chunks, 4 stylesheets verified |
| Source routes | **11/11** page.tsx |
| Production routes | **11/11** HTTP 200 |
| Forensic scenarios A–E | correct |
| Argument-order symmetry | chronology correct both directions |

## OPEN — blocks certification

### 1. Asymmetric verdict on the canonical sanity pair (HIGH)

`pallets/werkzeug` vs `psf/requests` returns:

- `psf/requests` -> `pallets/werkzeug` : INDEPENDENT / HIGH, 7 conflicting
- `pallets/werkzeug` -> `psf/requests` : **HEAVILY_DERIVED / HIGH**, 0 conflicting

Chronology is correct and verified against the GitHub API (werkzeug created
2010-10-18, requests 2011-02-13). The driver is now `shared_uncommon_constants`
at 0.95, whose top terms are `/get`, `0123456789`, `<local>`,
`Content-Length`, `Transfer-Encoding`, together with
`shared_module_boundaries` at 0.90 (`.precommitconfig`, `.readthedocs`,
`auth`, `conftest`).

These are HTTP and repository-convention values. The same class of defect as
the empty-`__init__.py` and pytest-name false positives already fixed, one layer
up. Partially mitigated: `commit_message_vocabulary` was demoted from 0.80 to
0.30 as a result of this investigation, but the verdict has not changed.

### 2. Private key in published git history (MEDIUM, bounded)

Self-signed `CN=api.openai.com` interception certificate. Not in any trust
store, no `/etc/hosts` redirect, not the key in use today, and confers no
OpenAI access. Hardened by rotating per run with 1-day validity. The blob is
still retrievable from history; purging it requires a force-push to an external
ref and explicit authorisation.

## NOT VERIFIED in this run

Phases 11 through 16 and 22 were not executed. Specifically, no evidence was
gathered in this run for:

- deployed contract full address (the API still reports `deployed: false`
  because the truncated Studio address is not wired in)
- deployed read-method invocation table
- deployed write lifecycle
- wallet security matrix
- Playwright across Chromium, Firefox and WebKit
- honest visual scoring
- final regression matrix against one commit

Earlier sessions recorded Studio deployment tx
`0x4c5c6d72bcae900d4b3a08dcb0131d292b9bf77d72d4a91375bac95381c6518b` with one
verified read (`get_case_count` -> 0). That is prior evidence, not evidence
from this run, and is not sufficient for certification.
