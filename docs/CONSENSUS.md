# Consensus

ForkReason's claim is that a lineage finding can be **independently checked**.
That claim is only worth something if the decision itself resists a wrong
answer, so this document describes exactly what GenLayer consensus is asked to
do — and, just as importantly, what it is not asked to do.

## The problem with one model

A lineage decision rests on evidence spread across two repositories' histories.
A single model reading two READMEs is not verifiable: nobody can check whether
it weighed the evidence or pattern-matched it.

GenLayer's Equivalence Principle requires agreement between independently
executed validations. ForkReason uses that, but with a specific shape.

## What is compared

Only **stable fields** participate in equality:

```
verdict
confidence              (bucket, not probability)
direction
shared_upstream
independent_origin_plausibility
strongest evidence classes
```

Prose is **never** compared for equality. Two validators can reach the same
conclusion and describe it differently — that is agreement, not noise.
Comparing explanations verbatim would produce false disagreement, which is
worse than useless.

## The validator re-derives; it does not re-parse

This is the most important design decision in the contract.

A validator that merely re-parses the leader's JSON and checks the enum is
cosmetic: any well-formed output passes. ForkReason's validator forms its **own**
decision from the same evidence, applies the same deterministic guards to it,
and compares the two stable tuples.

```python
def validator_fn(result) -> bool:
    if isinstance(result, (gl.vm.VMError, gl.vm.UserError)):
        return False
    try:
        leader_value = gl.vm.unpack_result(result)
        parsed_leader = _parse_decision(leader_value)
        _deterministic_guard(parsed_leader)
        leader_tuple = _stable_field_tuple(leader_value)

        # The validator's OWN answer, not a re-read of the leader's.
        mine = leader_fn()
        parsed_own = _parse_decision(mine)
        _deterministic_guard(parsed_own)
        own_tuple = _stable_field_tuple(mine)
    except Exception:
        return False                       # fail closed
    return leader_tuple == own_tuple
```

A leader returning a well-formed but substantively wrong verdict is therefore
rejected, and Direct Mode tests exactly that case.

## Deterministic guards run in Python

Some rules must not be negotiable by a model, because a model arguing well
could talk a validator into accepting nonsense:

| Guard | Rejects |
|---|---|
| Enum membership | Off-enum verdicts, confidences, directions, DNA layers |
| `INSUFFICIENT_EVIDENCE` + `HIGH` confidence | A contradiction no validator should accept |
| `SHARED_UPSTREAM` with no upstream named | A verdict that asserts an ancestor without identifying it |
| `INSUFFICIENT_EVIDENCE` with an upstream | Asserting an ancestor while claiming no conclusion |
| Directional verdict with `direction: NONE` | Derivation claimed without a direction |
| Non-directional verdict with a direction | A direction invented for a non-directional outcome |

These live in `_deterministic_guard`, not in the prompt. A prompt rule is
advisory; a code rule is not.

## Chronology cannot be argued around

A target whose earliest commit predates the origin's cannot have been derived
from it. The engine establishes this in Python from real commit dates before any
model is consulted, and a contradictory verdict is refused.

## Nondeterministic execution mutates nothing

`_decide()` computes a decision and returns it. All storage happens afterwards,
in deterministic execution, once consensus has accepted:

```python
decision_json = _decide(evidence_digest)   # nondeterministic, mutates nothing
parsed = _parse_decision(decision_json)
_deterministic_guard(parsed)

self.case_exists[case_id] = True           # deterministic, after consensus
self._append_revision(case_id, 1, manifest_hash, decision_json)
```

## Fail closed

If verification cannot complete — unparseable output, an off-enum value, a
chronology contradiction, a validator exception — the case does **not** resolve
as accepted. There is no default verdict and no "probably fine" path.

## Revisions are append-only

```
SUBMITTED → CONSENSUS_PENDING → RESOLVED
RESOLVED → CHALLENGED → CONSENSUS_PENDING → RESOLVED (revision N+1)
```

Revision N is never overwritten or deleted. A challenge that loses still
records that it was made and what it argued — an unsuccessful challenge is
evidence too.

A challenge must reference the **current** revision. A challenge racing another
is rejected rather than silently overwriting it.

## What this does not claim

Being explicit, because the temptation to overclaim is strong:

- Consensus proves that independent executions agreed. It does **not** prove the
  conclusion is *true*. A committee can agree on a wrong answer.
- What consensus buys here is that a single mistaken model — or a single
  manipulated leader — cannot silently determine the record.
- Validator independence is the load-bearing assumption. If all validators ran
  the same compromised model, consensus would faithfully reproduce the
  compromise.

That is why prompt injection is treated as a first-class security gate rather
than as a model-quality question.
