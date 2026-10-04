# Limitations

A tool that claims to measure provenance has to state where it is not measuring
it. These are real constraints on V1, not hedging.

## Technical limitations

**Public GitHub repositories only.** Private repositories require user-authorized
access, which changes the security model substantially. Non-GitHub hosts are not
supported: intake is built around `git archive` against GitHub's API, and the
URL validation is deliberately fail-closed to `https://github.com/...`.

**Squashed and shallow history weakens chronology.** Chronology is ForkReason's
most decisive signal, and a repository with one squashed commit has almost none.
The report states when history was limited rather than quietly downgrading
confidence.

**Monorepos are analyzed as one repository.** They are not decomposed into
independently versioned packages, so a finding about a monorepo is about the
whole tree.

**Shared-upstream discovery is heuristic without a declared parent.** When a
repository does not declare a fork parent, ForkReason looks for distinctive
shared vocabulary. It can miss a common ancestor that renamed everything, and it
can occasionally propose a candidate that is not a real ancestor. Candidates are
presented as candidates.

**Evidence from `HEAD` only, except for Bug DNA.** Most layers read the pinned
commit rather than the full history, because full-history analysis is expensive.
Bug DNA reads specific historical points, which is what makes it the strongest
signal — and also what makes it unavailable when history is absent.

**Vendored trees and generated code are inventoried, not analyzed.** Minified
output, generated clients and vendored dependencies carry no authorship signal,
so analyzing them would produce noise. They appear in the inventory and are
excluded from scoring.

**Language coverage is narrower than file coverage.** Fingerprinting is tuned for
Python, JavaScript/TypeScript, Go, Rust, Java, C/C++, Ruby and shell. Exotic
languages are inventoried but contribute little.

**Binary content is inventoried only.** Files are hashed and listed; no attempt
is made to find structural similarity inside them.

## Deliberate non-goals

**No legal conclusions.** ForkReason never says a repository was stolen,
infringing or illegal. Those are legal determinations requiring a standard of
proof and a legal framework, and this is neither.

**No ownership or authorship inference.** ForkReason reports relationships
between repositories, never who wrote what or with what intent.

**No probability.** Confidence is `LOW`/`MEDIUM`/`HIGH` because no calibration
methodology exists. A percentage would imply a precision that has not been
earned.

**No hidden custodial action.** ForkReason cannot record a finding on your
behalf. If you want it on chain, your wallet signs it. This is a feature.

**No forced conclusions.** `INSUFFICIENT_EVIDENCE` is a real answer. Most
similar-looking repository pairs are not related, and a large fraction of real
relationships leave too little trace to distinguish from coincidence. Returning a
verdict in those cases would make the tool worse, not better.

## Operational limitations

**Rate limits on public reads.** `GET /api/v1/cases` and `/search` have no
per-client rate limit. Bounded pagination limits response size; availability is
the residual risk.

**Snapshot retention.** Analyzed repository snapshots are kept on disk to make
repeat analysis cheap, with per-snapshot size bounds but no pruning policy.

**Consensus depends on the configured provider.** On a hosted deployment, model
availability affects whether a case resolves. It fails closed: an unverifiable
decision is never recorded.
