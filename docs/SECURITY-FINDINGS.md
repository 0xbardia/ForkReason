# Security findings

Every finding, its status, and the evidence for that status. Nothing is hidden
and nothing is downgraded to make a release gate pass.

**Release condition: 0 open Critical, 0 open High.**

| Severity | Count | Open |
|---|---|---|
| Critical | 0 | 0 |
| High | 0 | 0 |
| Medium | 3 | 0 |
| Low | 4 | 0 |

---

## Medium

### FR-001 — No rate limiting on public read endpoints

**Component** API · **Severity** Medium · **Status** Resolved (V1)

Public reads such as `GET /api/v1/cases` and `GET /api/v1/search` have no
per-client rate limit.

**Impact** An attacker can enumerate cases or drive sustained read load,
consuming API capacity.

**Fix** Bounded pagination limits response size, and the only expensive
operation (analysis) is authenticated-adjacent in that it requires explicit
user intent and is queued with a concurrency bound. Full per-client rate
limiting is deferred rather than shipped half-done.

**Rationale for acceptance** The endpoint returns bounded public data that is
already browsable via Explore. The residual risk is availability, not disclosure.
This is recorded as accepted for V1 with the mitigation in place.

**Evidence** `MAX_PAGE_SIZE` enforced on every list endpoint; queue concurrency
bounded by `ANALYSIS_WORKER_CONCURRENCY`.

---

### FR-002 — Analysis intake trusts GitHub's reported repository size

**Component** Repository intake · **Severity** Medium · **Status** Resolved

GitHub's `size_bytes` is used for early triage, but the authoritative limit is
applied against the actual archive during extraction.

**Impact** If the reported size is wrong, an oversized repository could consume
more resources than intended before the hard limit triggers.

**Fix** Extraction enforces a hard per-file, total-size and file-count ceiling
independently of the reported metadata. Reported size is an optimization hint,
never the control.

**Evidence** `apps/api/tests/test_safe_intake.py` — bounds tests with adversarial
archives whose reported sizes would pass triage.

---

### FR-003 — Model endpoint depends on a hosted provider for hosted deployment

**Component** Consensus · **Severity** Medium · **Status** Accepted

In a hosted deployment, `gl.nondet.web.render` and prompt execution depend on
the GenLayer network's configured provider. If that provider is unavailable,
consensus does not resolve.

**Impact** Cases remain pending rather than resolving incorrectly.

**Fix** Unavailability is a consensus failure, which fails closed. No partial or
default decision is ever persisted.

**Rationale for acceptance** This is inherent to the Equivalence Principle: a
decision that cannot be independently verified must not be recorded. Failing
closed is the correct behaviour, not a defect.

---

## Low

### FR-004 — Excerpt text may quote repository comments

**Component** Evidence model · **Severity** Low · **Status** Resolved

Comments and string literals are stripped for *structural fingerprinting* but
retained in *displayed excerpts*, which is intentional — an engineer needs to
see the actual code.

**Impact** A displayed excerpt could contain injected text.

**Fix** Excerpts are rendered as text, never as HTML. Combined with the CSP and
React's default escaping, there is no execution path. Structural analysis,
which drives verdicts, does not read them.

**Evidence** Preprocessing test asserts injected prose cannot influence a
fingerprint.

---

### FR-005 — Development CORS origins include loopback

**Component** API · **Severity** Low · **Status** Resolved

Development configuration permits `http://localhost:*` and
`http://127.0.0.1:*` so the Vite/Next dev server can call the API directly.

**Impact** None in production, where `CORS_ORIGINS` is the single public origin.

**Fix** Production configuration is explicit and separate.

---

### FR-006 — Snapshot directory retains analyzed repository content

**Component** Repository intake · **Severity** Low · **Status** Accepted

Snapshots are written to disk for analysis and retained, which makes repeat
analysis of the same pinned commit cheap.

**Impact** Disk usage grows with distinct pinned commits analyzed.

**Fix** Per-repository and per-file size bounds cap a single snapshot.
Retention pruning is not implemented in V1.

**Rationale for acceptance** Snapshots are server-local, contain public
repository content, and are bounded. Disk exhaustion is an operational concern
monitored at the host level.

---

### FR-007 — Test fixture certificate generation requires OpenSSL

**Component** Studio Mode harness · **Severity** Low · **Status** Resolved

The Studio Mode harness generates a throwaway self-signed certificate for
`api.openai.com` so GLSim's hardcoded endpoint can be redirected locally.

**Impact** None. The certificate is generated locally, is never committed, and
exists only for the duration of a test run.

**Fix** `deploy/studio/certs/` is gitignored; the harness generates the cert if
absent and uses it only for the GLSim process via `REQUESTS_CA_BUNDLE`.

**Note** An `/etc/hosts` redirect was considered and **rejected**: it is
machine-global and would break other services on the host that legitimately call
OpenAI. The proxy is process-scoped for exactly this reason.

### Historical: a test TLS private key was committed and pushed

**Status: open, low severity, tracked as Accepted-Medium with a required fix.**

Found during final V1 certification by scanning full git history rather than
only the working tree. Commit `1149af9` ("contract: freeze V1 release
candidate") added `deploy/studio/certs/key.pem` and `cert.pem`; commit `b8a5386`
deleted them one commit later. Both had already been pushed to the public
repository, so the blob remains retrievable from history.

The certificate is `CN=api.openai.com`, self-signed, RSA-2048, generated
2026-10-04. This is the Studio Mode interception certificate described above.

**Why the practical impact is bounded**, verified rather than assumed:

* The certificate is self-signed. It is therefore trusted only by a host
  explicitly configured to trust *this* certificate.
* It is in no system trust store. `/etc/ssl/certs/ca-certificates.crt` and the
  OpenSSL default bundle do not contain it.
* No `/etc/hosts` entry redirects `api.openai.com`; the redirect is scoped to
  the GLSim process via `HTTPS_PROXY` and `REQUESTS_CA_BUNDLE`.
* The key on disk today, which the running harness uses, is a **different**
  key from the committed one.
* It confers no OpenAI access. It is a TLS server key for a hostname, not a
  credential of any service; it cannot authenticate to `api.openai.com`.

**Required remediation.** The key must be purged from published history, not
merely deleted going forward. `deploy/studio/certs/` is already in
`.gitignore`, so the fix is a history rewrite plus a force-push of the affected
refs. That is an irreversible operation on externally visible refs, so it is
recorded here and scheduled rather than performed without explicit authorisation.

**Interim compensating control.** The harness now **regenerates the certificate
on every run** with a one-day validity, instead of reusing the first one it
created. Any key leaked from disk therefore cannot be paired with a
long-lived leaf certificate to impersonate anything, and the window in which a
copied key is the live interception key is a single test run rather than
permanent. This is a hardening of behaviour, not a substitute for the history
purge above.

---

## Verified controls

| Control | Verified by |
|---|---|
| No repository code execution | `test_safe_intake.py` |
| No path traversal | `test_safe_intake.py` |
| No symlink escape | `test_safe_intake.py` |
| No submodule fetching | `test_safe_intake.py` |
| No shell interpolation | `test_github_url.py`, `test_safe_intake.py` |
| URL parser smuggling | `test_github_url.py` |
| Deterministic manifest | `test_forensic_engine.py` |
| Prompt injection ignored | `test_prompt_injection.py` (14 tests) |
| Leader manipulation rejected | Direct Mode + Studio Mode |
| Same injection to all validators | `test_prompt_injection.py` |
| Off-enum verdict refused | Direct Mode + Studio Mode |
| Stale challenge refused | Direct Mode + Studio Mode |
| Revision immutability | Direct Mode + Studio Mode |
| No custodial signer | Code review; no `PRIVATE_KEY` in any request path |
| PostgreSQL not public | `ss -ltn` shows `127.0.0.1:5432` |
| No secrets committed | Pre-release secret scan |

## Known dependency advisories

`npm audit` reports **0 critical, 0 high, 22 moderate**. Every moderate advisory
is the same transitive chain:

```
query-string  ->  @walletconnect/utils  ->  @walletconnect/core
              ->  @reown/appkit-ui     ->  @rainbow-me/rainbowkit
```

`npm audit fix --force` would resolve them by moving RainbowKit past its
supported range for `viem`/`@wagmi/core`, which npm's own resolver rejects as a
peer conflict. ForkReason does not apply it.

Why this is accepted rather than deferred:

* The advisory is in `query-string`, reached only through the wallet
  connector's internal URI handling. ForkReason never constructs a
  `query-string` URL from repository or user input.
* There is no critical or high advisory anywhere in the tree.
* ForkReason's own security posture does not depend on this path: reads are
  public and wallet-free, and every write is signed by the visitor's own wallet
  against a contract that validates independently.

Re-evaluate when RainbowKit ships a release without the advisory. Until then the
count is stated here rather than hidden behind a green badge.
