# ForkReason Constitution

**Version:** 1.0.0
**Ratified:** 2026-10-03
**Last Amended:** 2026-10-03

Governing principles for every change to ForkReason. When a decision and this
document disagree, this document wins until it is amended on purpose.

---

## I. Product Truth

ForkReason reconstructs **software lineage**. It is not a plagiarism detector and
must never present itself as one.

1. **Banned verdicts.** `STOLEN`, `ILLEGAL`, `COPYRIGHT INFRINGEMENT`,
   `PLAGIARIZED` must not appear anywhere in code, UI, copy, or docs.
2. **Permitted language.** lineage, provenance, derived, common ancestor, shared
   upstream, declared fork, evidence, competing explanation, uncertain,
   consensus, insufficient evidence.
3. **Similarity is not lineage.** Code that matches may be copied, generated, or
   coincidental. Chronology is required to distinguish them.
4. **Insufficient is a real answer.** When evidence does not support a
   conclusion, `INSUFFICIENT_EVIDENCE` is returned. A boring, defensible result
   is a success. Dramatic outcomes must never be manufactured.
5. **Confidence is a bucket**, not a calibrated probability. We publish
   `LOW`/`MEDIUM`/`HIGH` and never render a bare numeric probability, because no
   calibration methodology exists for this problem.

## II. Evidence Integrity

6. **Evidence carries provenance.** Every evidence item must be traceable to a
   pinned commit, a file path, and a bounded excerpt. Evidence without a source
   is not evidence.
7. **Weak signals stay weak.** Common framework boilerplate must never be
   promoted to strong lineage evidence merely because it matches. Rarity
   weighting governs strength.
8. **Contradictions are preserved.** Evidence that weakens the selected verdict
   is stored and displayed. The report must be able to argue against itself.
9. **Alternative explanations are actively evaluated**, not merely listed. At
   minimum: derivation, shared upstream, independent same-spec implementation,
   insufficient history, declared fork, heavy post-derivation divergence.
10. **Determinism first.** Analysis uses deterministic algorithms wherever a
    deterministic answer exists. LLM judgement is reserved for genuinely
    semantic decisions and is always bounded to small evidence excerpts.

## III. Untrusted Input

11. **Repositories are hostile.** Repository content is DATA. It never
    redefines the task, verdict enums, output schema, or validator behaviour.
12. **Never execute analyzed code.** No build, no install, no test execution, no
    sourcing of shell files, no repo binaries, no plugins from the repo.
13. **Bounded by construction.** Every intake has explicit limits on size, file
    count, file size, history depth, candidate count, and wall-clock time.
    Limits are configuration, not implicit.
14. **Prompt injection is a release gate.** Adversarial fixtures must exist and
    must pass. Consensus does not defend against injection — unanimity on a
    wrong answer is still wrong.

## IV. Consensus Integrity

15. **Substance over format.** A leader is never approved because JSON parses,
    the enum is valid, or a summary exists. Validators verify the reasoning.
16. **Independent evaluation.** Validators reach their own conclusion from the
    same bounded evidence; they do not rubber-stamp the leader.
17. **Fail closed.** If verification cannot complete, resolution fails or
    returns the inconclusive outcome. Never default to acceptance.
18. **No storage mutation in nondeterministic code.** State is written only
    after consensus returns, in deterministic execution.
19. **Revisions are immutable.** A revision is never overwritten. A challenge
    appends revision N+1 and preserves N forever.

## V. Chain Boundary

20. **The user signs.** Every state-changing GenLayer action is signed by the
    user's browser wallet. There is no server-side user signer and no
    `PRIVATE_KEY` that silently signs user transactions.
21. **The backend is not the authority.** The application database may index and
    cache chain state. On-chain revision and verdict state is authoritative.
    The database must never silently diverge.
22. **Reads may be account-free.** Write paths must check wallet connection,
    correct address, correct network, and show transaction intent.

## VI. Engineering

23. **Smallest architecture that works.** Prefer deleting an abstraction over
    justifying it. No speculative extension points, no duplicate helpers, no
    wrappers that add nothing.
24. **Typed, bounded, explicit.** Public functions and API surfaces have
    explicit types and bounds. Errors are predictable.
25. **No silent failure.** No swallowed exceptions, no fake progress, no
    invented metrics. If it failed, say so and log it.
26. **Tests are evidence.** A test is never weakened to pass. Report actual
    command output, never expectation.
27. **Frontend is a release gate, not a skin.** Visual quality is engineering.
    No generic AI-gradient dark SaaS aesthetic.
28. **No fabricated claims.** Transaction hashes, addresses, screenshots, test
    results, ratings, and publication status must be real or absent.

---

## Governance

This constitution supersedes AGENTS.md guidance and any model-specific prompting
scaffolding. Amendments require a rationale, an impact note on existing
verdicts/evidence, and an explicit version bump.

Every release review must verify: banned verdicts absent, evidence carries
provenance, contradictions preserved, limits explicit, no server-side user
signer, revisions immutable, and no fabricated claims.

**Version:** 1.0.0 | **Ratified:** 2026-10-03 | **Last Amended:** 2026-10-03