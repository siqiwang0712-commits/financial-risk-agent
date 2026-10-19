"""Evidence flags alone cannot replace missing provenance at authorization."""

from copy import deepcopy

import pytest
from finrisk.assurance.evidence import assess_evidence
from test_assurance_runtime import path


@pytest.mark.parametrize("evidence", [[], [{}], None])
def test_missing_source_cannot_count_as_verified(evidence):
    value = path("a")
    value["source_evidence"] = evidence
    value["input_provenance"] = {}
    result = assess_evidence([value], 0.4)
    assert result.verified_path_count == 0
    assert result.coverage == 0


def test_duplicate_paths_do_not_inflate_material_coverage():
    verified, missing = path("a"), path("b", verified=False)
    baseline = assess_evidence([verified, missing], 0.4)
    repeated = assess_evidence([verified, deepcopy(verified), missing], 0.4)
    assert repeated == baseline


def test_duplicate_telemetry_does_not_change_dependencies_or_authorization():
    from finrisk.assurance.evidence import dependencies_from_paths
    from test_assurance_runtime import REFERENCE, calibrated_engine, input_for

    first, second = path("a"), path("b")
    duplicate = deepcopy(first)
    duplicate["latency_ms"] = 100
    assert dependencies_from_paths(
        [first, duplicate, second]
    ) == dependencies_from_paths([first, second])
    engine = calibrated_engine()
    assert engine.evaluate(
        input_for(first, duplicate, second, reference=REFERENCE)
    ) == engine.evaluate(input_for(first, second, reference=REFERENCE))


def test_missing_evidence_abstains_even_when_unknown_fragility_is_permitted():
    from dataclasses import replace

    from finrisk.assurance import AssuranceEngine
    from test_assurance_runtime import REFERENCE, calibrated_engine, input_for

    engine = AssuranceEngine(
        replace(calibrated_engine().policy, review_on_fragility_not_estimable=False)
    )
    missing = path("a")
    missing.update(source_evidence=[], input_provenance={})
    result = engine.evaluate(input_for(missing, reference=REFERENCE))
    assert result.final_decision == "ABSTAIN"
    assert not result.automation_allowed
    assert engine.authorize(result) == "ABSTAIN"


def test_rehashed_verified_paths_require_source_identities():
    from dataclasses import replace

    from finrisk.assurance import AssuranceEngine, verify_assurance_payload
    from finrisk.enterprise.decision import canonical_hash
    from test_assurance_runtime import REFERENCE, calibrated_engine, input_for

    engine = AssuranceEngine(
        replace(calibrated_engine().policy, review_on_fragility_not_estimable=False)
    )
    payload = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE)
    ).to_dict()
    payload["evidence_assurance"]["verified_evidence_ids"] = ()
    payload["evidence_fragility"].update(
        state="NOT_ESTIMABLE",
        largest_single_evidence_impact=None,
        decision_flip_count=0,
        decision_flip_rate=None,
        severity_change_count=0,
        affected_dimensions=(),
        affected_claims=(),
        ablations=(),
    )
    payload["decision_sufficient_evidence"].update(
        evidence_ids=(),
        method="NOT_ESTIMABLE",
        exact=False,
        preserves_proposed_decision=False,
        evaluated_subsets=0,
    )
    payload["certificate_hash"] = canonical_hash(
        {k: v for k, v in payload.items() if k != "certificate_hash"}
    )
    assert not verify_assurance_payload(payload, engine.policy)
