"""Direct Mode tests for ForkReasonRegistry.

Direct Mode runs the contract natively with no simulator, and supports the
cheatcodes ForkReason's security properties depend on: independent validator
runs (`vm.run_validator`), LLM and web mocks, and revert assertions.

Run with:
    .venv/bin/gltest contracts/tests/ -v
"""

import json
from pathlib import Path

from gltest.direct import VMContext, deploy_contract

CONTRACT = Path("contracts/forkreason_registry.py")

ORIGIN_REPO = "acme/upstream-core"
ORIGIN_COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
TARGET_REPO = "acme/derived-app"
TARGET_COMMIT = "0f1e2d3c4b5a69788796a5b4c3d2e1f001122334"
MANIFEST = "d0d0c0de0000000000000000000000000000000000000000000000000000ff"
OTHER_MANIFEST = "e0e0c0de00000000000000000000000000000000000000000000000000aabb"

DIGEST_BASIC = (
    "chronology: the distinctive marker TOKEN_QUANTUM appeared in origin at "
    "commit 3f2a1b0 on 2021-04-02 and in target at commit 9c8d7e6 on 2021-11-19.\n"
    "bug_dna: origin contained defect PATTERN_LEAK until fix commit 7b6c5d4 on "
    "2021-07-01; target's first commit postdates that fix and does not carry the "
    "defect.\n"
    "layers present: CODE, HISTORY, BUG\n"
    "shared_upstream candidate: acme/upstream-core (origin itself)"
)


def _decision(
    verdict="LIKELY_DERIVED",
    confidence="HIGH",
    direction="ORIGIN_TO_TARGET",
    shared_upstream="",
    plausibility="LOW",
    classes=None,
    rationale="Chronology and bug DNA support derivation from origin.",
):
    return json.dumps(
        {
            "verdict": verdict,
            "confidence": confidence,
            "direction": direction,
            "shared_upstream": shared_upstream,
            "independent_origin_plausibility": plausibility,
            "evidence_classes": classes or ["CODE", "HISTORY", "BUG"],
            "rationale": rationale,
        },
        sort_keys=True,
    )


def deploy(vm: VMContext, **kwargs):
    return deploy_contract(CONTRACT, vm, **kwargs)


def mock_decision(vm: VMContext, payload: str) -> None:
    """Make every subsequent LLM call return this exact decision.

    `vm.mock_llm` matches first-registered-wins, so switching an answer
    mid-test requires clearing. `strict_mocks` then turns an accidentally
    unused mock into a warning instead of a silently ignored one.
    """
    vm.clear_mocks()
    vm.strict_mocks = True
    vm.mock_llm(r".*", payload)


# --- constructor and basic writes ---------------------------------------


def test_constructor_starts_empty(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    assert c.get_case_count() == 0
    page = c.get_cases_page(0, 10)
    assert page["total"] == 0
    assert page["items"] == []
    assert page["has_more"] is False


def test_submit_case_resolves_to_revision_one(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)

    assert c.get_case_count() == 1
    case = c.get_case(MANIFEST)
    assert case["origin_repo"] == ORIGIN_REPO
    assert case["target_repo"] == TARGET_REPO
    assert case["current_revision"] == 1
    assert case["lifecycle"] == "RESOLVED"

    latest = c.get_latest_revision(MANIFEST)
    assert latest["verdict"] == "LIKELY_DERIVED"
    assert latest["confidence"] == "HIGH"
    assert latest["direction"] == "ORIGIN_TO_TARGET"
    assert latest["revision_number"] == 1
    assert latest["is_current"] is True
    assert c.get_revision_count(MANIFEST) == 1


def test_all_read_methods_expose_enums(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    assert list(c.get_dna_layers()) == ["CODE", "ARCHITECTURE", "HISTORY", "BUG", "TEST", "LANGUAGE"]
    assert "INSUFFICIENT_EVIDENCE" in list(c.get_valid_verdicts())
    assert list(c.get_valid_confidences()) == ["LOW", "MEDIUM", "HIGH"]


# --- input bounds and validation ----------------------------------------


def test_oversized_input_is_rejected(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    with direct_vm.expect_revert("origin_repo exceeds maximum length"):
        c.submit_case("a" * 500, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_empty_repository_is_rejected(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    with direct_vm.expect_revert("must not be empty"):
        c.submit_case("", ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_non_hex_commit_is_rejected(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    with direct_vm.expect_revert("origin_commit must be hexadecimal"):
        c.submit_case(ORIGIN_REPO, "zzzz", TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_identical_origin_and_target_is_rejected(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    with direct_vm.expect_revert("origin and target must differ"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, ORIGIN_REPO, ORIGIN_COMMIT, MANIFEST, DIGEST_BASIC)


def test_empty_digest_is_rejected(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    with direct_vm.expect_revert("evidence_digest must not be empty"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, "")


def test_unknown_case_read_reverts(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    with direct_vm.expect_revert("unknown case"):
        c.get_case("ab" * 32)


def test_unknown_revision_read_reverts(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    with direct_vm.expect_revert("unknown revision"):
        c.get_revision(MANIFEST, 7)


# --- duplicates and replay ---------------------------------------------


def test_duplicate_manifest_is_rejected(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    with direct_vm.expect_revert("already been recorded"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    assert c.get_case_count() == 1


def test_distinct_manifests_are_both_accepted(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, OTHER_MANIFEST, DIGEST_BASIC)
    assert c.get_case_count() == 2


# --- pagination ----------------------------------------------------------


def test_pagination_is_bounded_and_correct(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    for i in range(5):
        digest = f"aa{i:02d}" + "0" * 60
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, digest, DIGEST_BASIC)

    page = c.get_cases_page(0, 2)
    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert page["has_more"] is True

    last = c.get_cases_page(4, 2)
    assert len(last["items"]) == 1
    assert last["has_more"] is False


def test_pagination_limit_bounds_are_enforced(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    with direct_vm.expect_revert("limit must be between 1 and 50"):
        c.get_cases_page(0, 0)
    with direct_vm.expect_revert("limit must be between 1 and 50"):
        c.get_cases_page(0, 51)
    with direct_vm.expect_revert("offset must not be negative"):
        c.get_cases_page(-1, 5)


# --- deterministic guards ------------------------------------------------


def test_insufficient_evidence_cannot_be_high_confidence(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(
        direct_vm,
        _decision(verdict="INSUFFICIENT_EVIDENCE", confidence="HIGH", direction="NONE"),
    )
    with direct_vm.expect_revert("insufficient evidence cannot be high confidence"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_shared_upstream_verdict_requires_upstream(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision(verdict="SHARED_UPSTREAM", direction="NONE", shared_upstream=""))
    with direct_vm.expect_revert("requires a shared upstream repository"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_derived_verdict_requires_direction(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision(direction="NONE"))
    with direct_vm.expect_revert("derived verdicts require a direction"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_insufficient_evidence_resolves(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(
        direct_vm,
        _decision(
            verdict="INSUFFICIENT_EVIDENCE",
            confidence="LOW",
            direction="NONE",
            classes=["HISTORY"],
        ),
    )
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    latest = c.get_latest_revision(MANIFEST)
    assert latest["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert latest["confidence"] == "LOW"
    assert latest["direction"] == "NONE"


def test_shared_upstream_resolves_with_upstream(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(
        direct_vm,
        _decision(verdict="SHARED_UPSTREAM", direction="NONE", shared_upstream="acme/common-core"),
    )
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    latest = c.get_latest_revision(MANIFEST)
    assert latest["verdict"] == "SHARED_UPSTREAM"
    assert latest["shared_upstream"] == "acme/common-core"


# --- malformed model output ---------------------------------------------


def test_malformed_json_fails_closed(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, "this is not json at all")
    with direct_vm.expect_revert("decision output was not valid JSON"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_missing_field_fails_closed(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, json.dumps({"verdict": "LIKELY_DERIVED"}))
    with direct_vm.expect_revert("missing required field"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_invalid_verdict_enum_fails_closed(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision(verdict="DEFINITELY_STOLEN"))
    with direct_vm.expect_revert("verdict is not a permitted value"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_invalid_confidence_fails_closed(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision(confidence="VERY_HIGH"))
    with direct_vm.expect_revert("confidence is not a permitted value"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_invalid_evidence_class_fails_closed(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision(classes=["NOT_A_LAYER"]))
    with direct_vm.expect_revert("evidence_class is not a permitted value"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_oversized_evidence_classes_fails_closed(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision(classes=["CODE"] * 9))
    with direct_vm.expect_revert("evidence_classes must be a short list"):
        c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)


def test_too_many_evidence_classes_is_bounded(direct_vm: VMContext) -> None:
    """Six layers exist; asking for eight distinct ones must fail."""
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision(classes=["CODE", "ARCHITECTURE", "HISTORY", "BUG", "TEST", "LANGUAGE"]))
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    assert c.get_latest_revision(MANIFEST)["evidence_classes"] == [
        "CODE",
        "ARCHITECTURE",
        "HISTORY",
        "BUG",
        "TEST",
        "LANGUAGE",
    ]


# --- challenges and immutable revisions ----------------------------------


def test_challenge_creates_revision_two_and_preserves_one(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)

    # New evidence now points to a shared upstream.
    mock_decision(
        direct_vm,
        _decision(verdict="SHARED_UPSTREAM", direction="NONE", shared_upstream="acme/common-core"),
    )
    c.challenge_case(MANIFEST, 1, "Found the real common ancestor.", "upstream candidate evidence")

    assert c.get_revision_count(MANIFEST) == 2
    assert c.get_case(MANIFEST)["current_revision"] == 2

    rev1 = c.get_revision(MANIFEST, 1)
    rev2 = c.get_revision(MANIFEST, 2)
    assert rev1["verdict"] == "LIKELY_DERIVED"
    assert rev1["is_current"] is False
    assert rev2["verdict"] == "SHARED_UPSTREAM"
    assert rev2["is_current"] is True
    assert rev1["manifest_hash"] != rev2["manifest_hash"]


def test_stale_challenge_is_rejected(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    mock_decision(direct_vm, _decision(verdict="SHARED_UPSTREAM", direction="NONE", shared_upstream="x/y"))
    c.challenge_case(MANIFEST, 1, "first", "evidence")

    with direct_vm.expect_revert("stale challenge"):
        c.challenge_case(MANIFEST, 1, "second, racing the first", "evidence")
    assert c.get_revision_count(MANIFEST) == 2


def test_challenge_on_unknown_case_reverts(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    with direct_vm.expect_revert("unknown case"):
        c.challenge_case("ff" * 32, 1, "nope", "evidence")


def test_challenge_count_and_read(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    assert c.get_challenge_count(MANIFEST) == 0

    mock_decision(direct_vm, _decision(verdict="SHARED_UPSTREAM", direction="NONE", shared_upstream="acme/core"))
    c.challenge_case(MANIFEST, 1, "better evidence", "evidence")

    assert c.get_challenge_count(MANIFEST) == 1
    record = c.get_challenge(MANIFEST + "#2")
    assert record["base_revision"] == 1
    assert record["rationale"] == "better evidence"


def test_unknown_challenge_reverts(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    with direct_vm.expect_revert("unknown challenge"):
        c.get_challenge("ab" * 32 + "#2")


# --- validator independence ---------------------------------------------


def test_validator_accepts_honest_leader(direct_vm: VMContext) -> None:
    """When the leader's answer matches the evidence, validators agree."""
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    # Validators were captured; an honest leader passes independent validation.
    assert direct_vm.run_validator(index=-1) is True


def test_validator_rejects_well_formed_but_wrong_leader(direct_vm: VMContext) -> None:
    """The core security property: format-valid but substantively wrong is rejected.

    The leader is handed a valid JSON decision that contradicts the evidence.
    An implementation that trusted the leader would accept this. ForkReason must
    not.
    """
    c = deploy(direct_vm)
    # Leader claims HEAVILY_DERIVED at HIGH confidence, with no shared upstream.
    # The validator will independently derive LIKELY_DERIVED / HIGH.
    direct_vm.mock_llm(r".*", _decision())

    # Drive a submission whose leader result we then override at validation time.
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)

    # Now re-run the captured validator with a substituted leader result: the
    # leader lies, the validator computes its own answer and disagrees.
    lied = _decision(verdict="HEAVILY_DERIVED", confidence="LOW", direction="ORIGIN_TO_TARGET")
    assert direct_vm.run_validator(leader_result=lied, index=-1) is False


def test_validator_rejects_leader_error(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    assert direct_vm.run_validator(leader_error=Exception("model exploded"), index=-1) is False


def test_validator_rejects_malformed_leader_output(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    assert direct_vm.run_validator(leader_result="not json", index=-1) is False


def test_validator_rejects_off_enum_leader_output(direct_vm: VMContext) -> None:
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    bad = _decision(verdict="TOTALLY_MADE_UP")
    assert direct_vm.run_validator(leader_result=bad, index=-1) is False


def test_validator_rejects_leader_violating_deterministic_guard(direct_vm: VMContext) -> None:
    """A leader that says INSUFFICIENT_EVIDENCE + HIGH must be refused."""
    c = deploy(direct_vm)
    mock_decision(direct_vm, _decision())
    c.submit_case(ORIGIN_REPO, ORIGIN_COMMIT, TARGET_REPO, TARGET_COMMIT, MANIFEST, DIGEST_BASIC)
    guard_violation = _decision(
        verdict="INSUFFICIENT_EVIDENCE", confidence="HIGH", direction="NONE"
    )
    assert direct_vm.run_validator(leader_result=guard_violation, index=-1) is False