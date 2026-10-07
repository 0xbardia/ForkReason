# Roadmap

Everything below is **post-V1**. Nothing here is required for V1, and nothing
here is in progress unless marked so.

## SHIPPED — V1.0.1

- Forensic pipeline across six Repo DNA layers
- Canonical, reproducible evidence manifest
- Six verdicts including `INSUFFICIENT_EVIDENCE`
- Shared-upstream discovery
- Safe repository intake via pinned `git archive`
- Durable PostgreSQL job queue with lease recovery
- GenLayer Intelligent Contract with append-only revisions and challenges
- Independent-validator consensus with fail-closed parsing
- Prompt-injection release gate with adversarial fixtures
- Public dApp, Explore, case sharing, twenty documentation pages
- Browser-wallet registration, finalized chain reconciliation, and immutable
  challenge revision history
- Werkzeug/Requests bidirectional false-positive regression fix

## NEXT — V1.1

| Item | Why |
|---|---|
| **Stronger upstream discovery** | Current heuristics miss ancestors when no fork parent is declared. Look at GitHub's fork network more aggressively and at module-level lineage. |
| **Improved historical bug inference** | Bug DNA is the strongest signal available. Widen the set of detectable defect signatures and handle rebased history better. |
| **Richer evidence exports** | Signed, portable evidence bundles so a finding can travel with a bug report or a legal process without losing its manifest hash. |
| **Repository ownership verification** | Tie declared ownership to real accounts, so "declared fork" carries more weight. |
| **Improved shareable reports** | Print-quality and embeddable case reports, and Open Graph cards for shared case URLs. |

## LATER — V1.5

- **GitLab and Bitbucket support.** The intake layer is already host-agnostic in
  design; only the API client and URL validation are GitHub-specific.
- **npm and PyPI lineage.** Package-level provenance: which published versions
  correspond to which commits, and whether a package was republished from
  another.
- **Package provenance.** Tie registry publishing events to repository history.
- **CI integration.** A GitHub Action that runs lineage checks on every push or
  release and fails on a derivation conflict.

## RESEARCH — V2

| Item | Open question |
|---|---|
| **Private repositories** | Requires user-authorized access. The analysis pipeline does not care, but intake safety and secret handling become a much larger problem. |
| **Team workspaces** | Multi-tenant case collections, sharing, and permissions. |
| **Provenance graph** | A persistent graph of repositories, commits and relationships rather than pairwise cases. Queries like "what descends from this commit" become first class. |
| **Organizational API** | Programmatic access, webhooks, and bulk analysis. |
| **Reusable attestations** | Cross-repository attestations that many cases can cite without re-deriving. |

**Calibrated confidence.** ForkReason reports `LOW`/`MEDIUM`/`HIGH` because
there is no calibration methodology. Research direction: build a labelled
corpus of known-derived and known-unrelated pairs, then fit a calibration
function and report a probability *only where one is earned*. Until then,
buckets are the honest answer.

**Authorship.** ForkReason deliberately does not infer who wrote what. Whether
that can be done responsibly — and whether it should be — is unresolved, and any
answer would need to be held to a much higher evidentiary standard than lineage.

## What will not be built

- **Legal conclusions.** ForkReason reports development relationships. It will
  not say a repository was stolen or infringing.
- **Probabilities without calibration.** A number that looks precise and is not
  is worse than a bucket.
- **Provenance claims for code ForkReason cannot read.** Gencode, minified
  output and vendored trees are inventoried, not analyzed, and saying otherwise
  would be a lie.
