# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security vulnerability.**

Use GitHub's private reporting on the repository:

**Security → Report a vulnerability** at
<https://github.com/0xbardia/ForkReason/security/advisories/new>

Please include:

- what an attacker can achieve, not just what you found;
- the exact repository inputs or API calls involved;
- reproduction steps, ideally with a fixture repository;
- the ForkReason version or commit you tested.

### What to expect

| Stage | Target |
|---|---|
| Acknowledgement | 72 hours |
| Initial assessment | 7 days |
| Fix or mitigation plan | 14 days |
| Public disclosure | Coordinated with you, after a fix ships |

We will tell you if a report is out of scope or a duplicate, and we will credit
you in the advisory unless you prefer otherwise.

## Supported versions

V1 is the only supported line. Fixes land on `main` and are released as patch
tags.

## Threat model in one paragraph

Analyzed repositories are **hostile input**. They are fetched with `git archive`
of tracked blobs at a pinned commit and are never executed: no working tree, no
hooks, no `npm install`, no submodule content, no symlink traversal out of the
sandbox. All subprocess calls use argument arrays with `shell=False`. There is no
fetch-arbitrary-URL capability, so ForkReason cannot be used as an SSRF proxy.

The second-order threat is **prompt injection**: a repository whose README, code
comments or commit messages instruct the model to return a particular verdict.
Consensus does not solve this — if every validator obeys the same instruction,
they agree on the wrong answer. ForkReason's defences are deterministic
preprocessing, bounded excerpts, explicit delimiters, strict typed parsing,
deterministic guards in code, independent validator re-derivation, and failing
closed.

Full details: [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md) and
[`docs/SECURITY-FINDINGS.md`](docs/SECURITY-FINDINGS.md).

## Trust boundaries

| Boundary | Rule |
|---|---|
| Browser → API | Untrusted. Every field is validated and length-bounded. |
| Repository → analysis engine | Untrusted. Nothing from a repository is executed or trusted as instructions. |
| Repository content → model | Untrusted data, never instructions. |
| API → database | Parameterized queries only. |
| Backend → chain | Read-only. The server holds no key that can sign for a user. |
| User → chain | Every write is signed by the user's own wallet. |

## What we will not accept

- Reports that require a malicious *server* rather than a malicious repository.
- Missing rate limits on public read endpoints that do not enable abuse beyond
  ordinary use.
- Findings that depend on a user signing a transaction they were tricked into.
- Theoretical prompt-injection variants that do not survive the deterministic
  guards (these are still welcome as discussion — open an issue).

## Security posture

- No server-side custodian of user keys; no `PRIVATE_KEY` in any request path.
- CSP with a per-request nonce; `frame-ancestors 'none'`; HSTS with preload.
- PostgreSQL, the API and the worker are bound to loopback and are not publicly
  reachable.
- Dependabot and `npm audit` run with zero known critical or high advisories at
  V1.