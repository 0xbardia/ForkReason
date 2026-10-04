# Evidence model

Every evidence item is bound to a pinned commit, a file path, a bounded excerpt
and a strength. Evidence without a source is not evidence.

## Anatomy of an evidence item

```json
{
  "id": "ev_7f3a91c2",
  "layer": "BUG",
  "type": "shared_defect_signature",
  "strength": "HIGH",
  "why": "Both repositories introduced the same off-by-one in chunked transfer; "
         "the target's first commit already contains the buggy code.",
  "conflicting": false,
  "sources": [
    {
      "repo": "acme/original",
      "path": "src/transfer.py",
      "commit": "3f9c1ab...",
      "excerpt": "def chunk(data, n):\n    return [data[i:i+n] for i in range(0, len(data), n)]"
    }
  ]
}
```

Deterministic IDs are derived from content, so the same evidence produces the
same id across runs and machines.

## Weighting by rarity

Signals are weighted by rarity, not by how many tokens matched.

A three-token shingle of common identifiers is worth almost nothing. A rare
domain term, a distinctive constant, an ordered sequence of uncommon tokens, or
a specific defect signature is worth a great deal.

Concretely, `fingerprint.py` exposes `COMMON_BOILERPLATE_TOKENS` with
`is_common(token)` and `rarity(token)`. Structural tokens and shingles are
filtered through them before any score is computed, so `import`, `def`, `class`,
`self` and `return` contribute nothing. This is deletion of the evidence itself,
not a lowered threshold, which is why it does not drift when scores are retuned.

An early version of the engine scored two unrelated twenty-line Python projects
at `structural_similarity = 1.000` because they shared only stdlib imports. The
fix was to delete the evidence, not to lower the score.

## Strength buckets

| Strength | Meaning |
|---|---|
| `HIGH` | Strong **and** rare. Discriminative on its own. |
| `MEDIUM` | Suggestive, but has an innocent explanation. |
| `LOW` | Mostly indicates a shared ecosystem. |

Strength is a property of the signal, not of how confident the engine happens
to be.

## Layers

`CODE` · `ARCHITECTURE` · `HISTORY` · `BUG` · `TEST` · `LANGUAGE`

No single layer may carry a verdict. Derivation requires substantive evidence
across multiple layers, including at least one discriminative signal.

## Conflicting evidence is preserved

Evidence that weakens the selected verdict is stored and displayed with equal
prominence. It is never filtered out to make a result look cleaner.

A case that resolved to `INDEPENDENT` still shows the `target_predates_origin`
and overlapping-structure signals, marked as conflicting. If a reviewer
disagrees with the verdict, the case for disagreement is right there.

## The Evidence Manifest

The manifest is the canonical, bounded set submitted to consensus.

```
schema_version · case_id
origin (canonical repo + pinned commit)
target (canonical repo + pinned commit)
repository timestamps relevant to chronology
evidence items with category and strength
conflicting signals
alternative explanations
common-upstream candidates
manifest creation version
canonical hash
```

Canonicalization before hashing:

1. sort object keys;
2. order every collection deterministically;
3. quantize floating-point plausibility values;
4. serialize canonically;
5. SHA-256 the bytes.

```python
# apps/api/forkreason/analysis/manifest.py
def manifest_hash(manifest: dict[str, Any]) -> str:
    return content_hash(canonical_json(manifest))
```

`canonical_json` sorts keys and orders collections; `content_hash` is SHA-256
over those canonical bytes. Case and evidence ids are content-derived the same
way (`case_id_for`, `evidence_id` in `ids.py`), so identical input produces
identical ids across runs and machines.

Anyone with the same two commits can recompute the hash and confirm nothing was
altered between analysis and record. That property is the reason determinism is
a hard constraint on the engine — a manifest that varied run to run would make
the hash meaningless.

### Verifying a manifest yourself

Fetch it and re-hash it. The rule is domain-separated canonical JSON, so it
needs no project code — only a SHA-256 and sorted-key JSON:

```bash
curl -s https://forkreason.bydx.fun/api/v1/cases/<case-id>/manifest \
  | jq -S -c '.manifest'
```

```python
import hashlib, json
manifest = json.load(open("manifest.json"))
salt = "forkreason/v1"                       # domain separator, published in ids.py
canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True)
print(hashlib.sha256(f"{salt}\n{canonical}".encode()).hexdigest())
```

That value must equal `manifest_hash`. The case id is derived the same way from
the two pinned repositories and commits, so the pair
`(case_id, manifest_hash)` is independently checkable.

Two properties make this meaningful and are covered by
`test_manifest_hash_is_verifiable_by_an_outsider`:

- **Tamper-evident.** Changing any evidence item changes the hash.
- **Order-independent.** Reordering findings does not change the hash, because
  the order of a set of findings is an artifact of analysis, not meaning.

The manifest itself is stored per revision and served from
`GET /api/v1/cases/{id}/manifest`.

## Bounded by construction

- Whole repositories are never stored on-chain or sent to a model.
- Excerpts are truncated to a configured maximum.
- Evidence count is capped; truncation is reported rather than hidden.
- Intake limits bound repository size, file size, file count and history depth.

## Ranking

Evidence is ranked to decide what a reader sees first, not to compute a
probability. The report leads with the strongest discriminative signals and
keeps the conflicting ones immediately reachable.
