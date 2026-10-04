# Repo DNA

A repository is measured across six independent dimensions. No single layer can
establish lineage; the combination is what discriminates copying from
coincidence.

## Why six layers

Any one signal is defeatable:

- **Code** can be shared by a framework.
- **Architecture** can be shared by convention.
- **History** is truncated by rebases and squashes.
- **Bug** evidence needs enough history to contain a fix.
- **Test** evidence needs the tests to have travelled.
- **Language** evidence needs distinctive phrasing.

Requiring agreement across layers is what makes a false positive expensive.

## CODE

Normalized token structure, uncommon constants, implementation patterns,
ordered token sequences (shingles).

The most valuable signal here is a **rare constant**: a magic number or
identifier that is neither framework vocabulary nor common to the ecosystem.
`CHECKPOINT_MAGIC = 0x5F3759DF` appearing in both repositories is far stronger
evidence than any structural similarity score.

Ordered sequences beat unordered ones. Two files containing the same words in a
different order are different code.

## ARCHITECTURE

Directory topology, module boundaries, dependency relationships, unusual
abstractions, subsystem organization.

The signal is the *decomposition*: which concepts got their own module, and
what they were named. Two projects that independently arrived at
`parsers/`, `transport/`, `codec/` with the same internal boundaries are more
likely related than two that merely both parse JSON.

## HISTORY

Commit chronology, first occurrence, deleted and reworked code, implementation
order, temporal direction.

This is the layer that turns similarity into direction, because it is the only
one that knows *when*.

**Bug DNA** is the sharpest tool available here: a specific defect that exists
in one repository and is later fixed there, and is present *already* in the other
repository's earliest commit, is a timestamp that cannot be fabricated. Nobody
independently writes the same unusual mistake.

## BUG

Historically traceable unusual defects, bug and fix commits, regression cases,
distinctive erroneous behaviour.

ForkReason reads code at specific points in history, not only at HEAD. That is
what makes "the target's first commit already contains the buggy behaviour"
answerable at all.

## TEST

Uncommon tests, fixtures, regression scenarios, distinctive test structure.

A regression test added alongside a bug fix is unusually good evidence, because
the test encodes the *mistake*, not just the behaviour. Two repositories
carrying the same regression test for the same off-by-one is strong.

## LANGUAGE

Naming, comments, unusual terminology, docs structure, distinctive examples,
rare typo and phrase evidence.

Typo evidence is included deliberately. Typos are not invented twice.

## Weak signals stay weak

Common framework vocabulary is removed before it can become evidence:

```python
COMMON_BOILERPLATE_TOKENS: frozenset[str] = frozenset({...})

def is_common(token: str) -> bool:
    return token in COMMON_BOILERPLATE_TOKENS
```

Structural and shingle comparisons filter through `is_common` before scoring.
This is a correctness requirement, not a tuning knob: an engine that scores
`import os` as lineage evidence is not slightly wrong, it is useless.

## Layer balance

A verdict drawing entirely from one layer is suspicious and is treated as such.
Real derivation shows up as a pattern across layers, weighted toward History and
Bug — the layers that carry time.

## What Repo DNA is not

It is not authorship. Two people can share a codebase, one person can write
similar code twice, and an AI can reproduce a style without copying history.
ForkReason reports development relationships, never who wrote what or why.
