from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from finrisk.agent import FinancialRiskAgent
from finrisk.assurance import (
    AssuranceEngine,
    AssuranceInput,
    AssurancePolicy,
    DistributionValidityState,
    FinancialFeatureVector,
    PolicyMaturity,
    ReferenceProfile,
    ReportingObservabilityVector,
    authorized_final_decision,
    load_reference_profile,
    separate_financial_and_reporting_features,
    verify_assurance_payload,
    verify_assurance_result,
    verify_decision_certificate,
)
from finrisk.assurance.evidence import (
    assess_evidence,
    dependencies_from_paths,
    evidence_identifier,
)
from finrisk.assurance.fragility import (
    analyze_fragility,
    decision_sufficient_evidence,
)
from finrisk.domain import Evidence
from finrisk.enterprise.decision import canonical_hash, replay_diff
from finrisk.enterprise.decision_bundle import (
    DecisionBundle,
    build_decision_bundle,
    verify_decision_bundle,
)
from finrisk.enterprise.domain import AnalysisSnapshot
from finrisk.enterprise.fusion import hierarchical_escalation
from finrisk.enterprise.integrity import CalibrationStatus

ROOT = Path(__file__).resolve().parents[1]


def path(identifier: str, score: float = 70.0, verified: bool = True) -> dict:
    evidence = {
        "id": identifier,
        "document": "10-K",
        "source_hash": "source-hash",
        "page": 8,
        "source_text": f"supporting evidence {identifier}",
        "fiscal_year": 2025,
        "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "unit": "USD",
        "raw_value": 10,
        "normalized_value": 10,
        "verification_status": "verified" if verified else "unverified",
    }
    return {
        "reason_code": f"LIQ_{identifier}",
        "risk_domain": "liquidity",
        "evidence_path_status": "VERIFIED" if verified else "UNVERIFIED",
        "source_evidence": [evidence],
        "input_provenance": {"cash": [evidence]},
        "fusion_contribution": {
            "method": "hierarchical_escalation",
            "dimension_score": score,
            "role": "supporting",
        },
    }


def calibrated_engine() -> AssuranceEngine:
    return AssuranceEngine(
        AssurancePolicy(
            maturity=PolicyMaturity.CALIBRATED_INTERNAL,
            require_distribution_reference=True,
            require_calibration_for_automation=True,
        )
    )


def input_for(
    *paths: dict,
    reference: ReferenceProfile | None = None,
    cash: float = 10,
    availability: bool = True,
    calibration: CalibrationStatus = CalibrationStatus.CALIBRATED_INTERNAL,
) -> AssuranceInput:
    return AssuranceInput(
        proposed_decision="FLAG",
        risk_score=70,
        evidence_paths=paths,
        financial_features=FinancialFeatureVector({"cash": cash}),
        reporting_observability=ReportingObservabilityVector(
            {"cash": availability}
        ),
        sector="industrial",
        disagreement=0.1,
        calibration_status=calibration,
        reliability=0.8 if calibration is not CalibrationStatus.UNCALIBRATED else None,
        reference_profile=reference,
        fusion_policy={"minimum_coverage": 0.4},
    )


REFERENCE = ReferenceProfile(
    "v0.4 deterministic test reference",
    "test-v1",
    feature_bounds={"cash": (0, 100)},
    allowed_sectors=("industrial",),
    required_features=("cash",),
    minimum_reporting_availability=1.0,
)


def test_only_valid_assurance_result_can_authorize_final_decision():
    proposal = hierarchical_escalation({"liquidity": 70}, 1.0, 1.0)
    assert proposal.proposed_decision == "FLAG"
    assert "final_decision" not in proposal.to_dict()
    engine = calibrated_engine()
    with pytest.raises(ValueError, match="no valid AssuranceResult"):
        authorized_final_decision(None, engine.policy)
    result = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE)
    )
    assert verify_assurance_result(result, engine.policy)
    assert authorized_final_decision(result, engine.policy) == "FLAG"
    altered = replace(result, final_decision="PASS")
    assert not verify_assurance_result(altered, engine.policy)
    with pytest.raises(ValueError, match="not authorized"):
        authorized_final_decision(altered, engine.policy)


def test_certificate_builder_rejects_an_assurance_bypass():
    with pytest.raises(ValueError, match="valid AssuranceResult"):
        build_decision_bundle(
            "org", "entity", {}, {}, {}, {}, [], {}, [], {}, "PASS"
        )


def test_rehashed_assurance_mutations_fail_structural_and_policy_checks():
    engine = calibrated_engine()
    result = engine.evaluate(input_for(path("a"), path("b"), reference=REFERENCE))

    def rehash(payload: dict) -> dict:
        content = {key: value for key, value in payload.items() if key != "certificate_hash"}
        payload["certificate_hash"] = canonical_hash(content)
        return payload

    mutations = (
        lambda value: value.update(proposed_decision="PASS"),
        lambda value: value.update(final_decision="PASS"),
        lambda value: value.update(policy_hash="0" * 64),
        lambda value: value["evidence_assurance"].update(state="PARTIAL"),
        lambda value: value["distribution_validity"].update(
            state="OUTSIDE_REFERENCE"
        ),
        lambda value: value.update(automation_allowed=False),
    )
    for mutate in mutations:
        payload = result.to_dict()
        mutate(payload)
        assert not verify_assurance_payload(rehash(payload), engine.policy)

    forged = rehash(
        {
            **result.to_dict(),
            "final_decision": "FLAG",
            "automation_allowed": True,
        }
    )
    with pytest.raises(ValueError, match="no valid AssuranceResult"):
        authorized_final_decision(forged, engine.policy)  # type: ignore[arg-type]


def test_missing_assurance_data_fails_closed():
    result = calibrated_engine().evaluate(input_for(reference=None))
    assert result.final_decision == "ABSTAIN"
    assert not result.automation_allowed
    assert {
        "INSUFFICIENT_VERIFIED_EVIDENCE",
        "DISTRIBUTION_VALIDITY_UNKNOWN",
    }.issubset(result.reason_codes)


def test_removing_verified_evidence_never_improves_assurance():
    paths = [path("a"), path("b", verified=False)]
    baseline = assess_evidence(paths, 0.4)
    evidence_id = evidence_identifier(paths[0]["source_evidence"][0])
    reduced = assess_evidence(paths, 0.4, {evidence_id})
    assert reduced.verified_path_count <= baseline.verified_path_count
    assert reduced.coverage <= baseline.coverage
    assert reduced.state != "VERIFIED"


def test_fragility_is_deterministic_and_uses_only_frozen_dependencies():
    dependencies = dependencies_from_paths([path("a"), path("b")])
    policy = AssurancePolicy()
    first = analyze_fragility(dependencies, 70, "FLAG", policy)
    second = analyze_fragility(dependencies, 70, "FLAG", policy)
    assert first == second
    assert first.state == "STABLE"
    assert first.decision_flip_count == 0
    assert all("evidence_id" in row for row in first.ablations)


def test_fragility_classifies_redundant_sensitive_and_critical_evidence():
    policy = AssurancePolicy()
    stable = analyze_fragility(
        dependencies_from_paths([path("a", 70), path("b", 70)]),
        70,
        "FLAG",
        policy,
    )
    sensitive = analyze_fragility(
        dependencies_from_paths([path("critical", 70), path("backup", 60)]),
        70,
        "FLAG",
        policy,
    )
    fragile = analyze_fragility(
        dependencies_from_paths([path("only", 70)]), 70, "FLAG", policy
    )
    assert stable.state == "STABLE"
    assert sensitive.state == "SENSITIVE"
    assert sensitive.largest_single_evidence_impact == 10
    assert fragile.state == "FRAGILE"
    assert fragile.decision_flip_count == 1


def test_decision_sufficient_evidence_is_exact_when_graph_is_small():
    dependencies = dependencies_from_paths([path("a"), path("b")])
    result = decision_sufficient_evidence(dependencies, "FLAG", AssurancePolicy())
    assert result.method == "EXACT"
    assert result.exact
    assert result.preserves_proposed_decision
    assert len(result.evidence_ids) == 1


def test_large_sufficient_evidence_result_is_explicitly_approximate():
    dependencies = dependencies_from_paths(
        [path(f"node-{index}") for index in range(13)]
    )
    result = decision_sufficient_evidence(dependencies, "FLAG", AssurancePolicy())
    assert result.method == "GREEDY_APPROXIMATION"
    assert not result.exact
    assert result.preserves_proposed_decision


def test_distribution_worsening_cannot_increase_automation_eligibility():
    engine = calibrated_engine()
    in_reference = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE, cash=10)
    )
    outside = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE, cash=1000)
    )
    assert in_reference.distribution_validity.state == "IN_REFERENCE"
    assert in_reference.automation_allowed
    assert outside.distribution_validity.state == "OUTSIDE_REFERENCE"
    assert not outside.automation_allowed
    assert outside.final_decision == "REVIEW"


def test_all_distribution_states_are_fail_closed_or_monotone():
    engine = calibrated_engine()
    inside = engine.evaluate(input_for(path("a"), path("b"), reference=REFERENCE))
    warning = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE, availability=False)
    )
    outside = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE, cash=1000)
    )
    unknown = engine.evaluate(input_for(path("a"), path("b"), reference=None))
    assert [
        item.distribution_validity.state
        for item in (inside, warning, outside, unknown)
    ] == ["IN_REFERENCE", "WARNING", "OUTSIDE_REFERENCE", "UNKNOWN"]
    assert inside.automation_allowed
    assert not any(item.automation_allowed for item in (warning, outside, unknown))


def test_development_reference_is_hash_bound_and_explicitly_scoped(tmp_path):
    source = ROOT / "research" / "v040_development" / "development_reference.json"
    reference = load_reference_profile(source)
    assert reference.scope == "DEVELOPMENT_REFERENCE_ONLY"
    assert reference.source_commit == "69cafe6a8afbb35aceec27a8e27660419d401b57"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["feature_bounds"]["cash"][1] += 1
    tampered = tmp_path / "tampered-reference.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact hash"):
        load_reference_profile(tampered)


def test_reporting_observability_is_separate_from_financial_severity():
    engine = calibrated_engine()
    complete = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE, availability=True)
    )
    missing = engine.evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE, availability=False)
    )
    assert complete.proposed_decision == missing.proposed_decision == "FLAG"
    assert complete.distribution_validity.state is DistributionValidityState.IN_REFERENCE
    assert missing.distribution_validity.state is DistributionValidityState.WARNING
    assert not missing.automation_allowed

    financial, observability = separate_financial_and_reporting_features(
        {"cash": 10}, {"cash", "revenue"}
    )
    assert financial.values == {"cash": 10.0}
    assert "revenue" not in financial.values
    assert observability.availability == {"cash": True, "revenue": False}


def test_uncalibrated_policy_never_exposes_probability_or_automation():
    policy = AssurancePolicy(
        require_distribution_reference=False,
        require_calibration_for_automation=True,
    )
    result = AssuranceEngine(policy).evaluate(
        input_for(
            path("a"),
            path("b"),
            reference=None,
            calibration=CalibrationStatus.UNCALIBRATED,
        )
    )
    assert result.calibration_status == "UNCALIBRATED"
    assert result.diagnostics["probability"] is None
    assert result.diagnostics["reliability"] is None
    assert not result.automation_allowed


@pytest.mark.parametrize("mutation", [
    {"automation_allowed": "false"}, {"automation_allowed": 1},
    {"evidence_fragility": {"state": "FRAGILE"}},
    {"evidence_fragility": {"state": "NOT_ESTIMABLE"}},
])
def test_rehashed_malformed_authorization_still_fails_closed(mutation):
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path("a"), path("b"), reference=REFERENCE)).to_dict()
    assert payload["automation_allowed"] is True
    payload.update(mutation)
    payload["certificate_hash"] = canonical_hash({
        key: value for key, value in payload.items() if key != "certificate_hash"
    })
    assert not verify_assurance_payload(payload, engine.policy)


def test_decision_certificate_hash_covers_assurance_content():
    assurance = calibrated_engine().evaluate(
        input_for(path("a"), path("b"), reference=REFERENCE)
    )
    bundle = build_decision_bundle(
        "org",
        "entity",
        {"10-K": "document-hash"},
        {"cash": 10},
        {"final_decision": assurance.final_decision},
        {"score": 70},
        [path("a"), path("b")],
        {"metric": "current_ratio"},
        [],
        {"assurance": "v0.4"},
        assurance.final_decision,
        proposed_decision=assurance.proposed_decision,
        assurance=assurance.to_dict(),
        decision_sufficient_evidence=assurance.decision_sufficient_evidence.to_dict(),
        policy_version=assurance.policy_version,
        policy_hash=assurance.policy_hash,
        calibration_status=assurance.calibration_status,
        assurance_policy=calibrated_engine().policy,
    )
    assert bundle.bundle_hash == bundle.certificate_hash
    assert verify_decision_certificate(bundle, calibrated_engine().policy)
    payload = bundle.to_dict()
    payload["assurance"]["final_decision"] = "PASS"
    assert not verify_decision_certificate(payload, calibrated_engine().policy)


@pytest.mark.parametrize("state", ["PARTIAL", "INSUFFICIENT", "UNKNOWN"])
def test_restricted_final_decision_cannot_bypass_evidence_blockers(state):
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path("a"), path("b"), reference=REFERENCE)).to_dict()
    payload.update(automation_allowed=False, assurance_status="RESTRICTED")
    evidence = payload["evidence_assurance"]
    evidence.update(state=state, verified_path_count=0, coverage=0)
    payload["certificate_hash"] = canonical_hash({
        key: value for key, value in payload.items() if key != "certificate_hash"
    })
    assert not verify_assurance_payload(payload, engine.policy)


@pytest.mark.parametrize("mutation", [
    {"verified_path_count": 0}, {"material_path_count": -1},
    {"coverage": 0.5}, {"verified_path_count": True},
])
def test_rehashed_evidence_counters_must_match_verified_state(mutation):
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path("a"), path("b"), reference=REFERENCE)).to_dict()
    payload["evidence_assurance"].update(mutation)
    payload["certificate_hash"] = canonical_hash({
        key: value for key, value in payload.items() if key != "certificate_hash"
    })
    assert not verify_assurance_payload(payload, engine.policy)


@pytest.mark.parametrize("final,status", [("FLAG", "FAILED"), ("PASS", "FAILED")])
def test_failed_assurance_cannot_authorize_a_pass_or_flag(final, status):
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path("a"), path("b"), reference=REFERENCE)).to_dict()
    payload.update(final_decision=final, assurance_status=status, automation_allowed=False)
    payload["certificate_hash"] = canonical_hash({
        key: value for key, value in payload.items() if key != "certificate_hash"
    })
    assert not verify_assurance_payload(payload, engine.policy)


def test_valid_restricted_and_optional_reference_policies_remain_verifiable():
    for maturity, calibration, require_calibration in [
        (PolicyMaturity.HEURISTIC_POLICY, CalibrationStatus.UNCALIBRATED, True),
        (PolicyMaturity.CALIBRATED_INTERNAL, CalibrationStatus.CALIBRATED_INTERNAL, True),
        (PolicyMaturity.CALIBRATED_INTERNAL, CalibrationStatus.UNCALIBRATED, False),
    ]:
        engine = AssuranceEngine(AssurancePolicy(
            maturity=maturity, require_distribution_reference=False,
            require_calibration_for_automation=require_calibration,
        ))
        result = engine.evaluate(input_for(path("a"), path("b"), calibration=calibration))
        assert result.final_decision == "FLAG"
        assert verify_assurance_result(result, engine.policy)


def test_legacy_bundle_integrity_is_not_v04_authorization():
    bundle = DecisionBundle(
        "legacy", "org", "entity", "historical", {}, "i", "o", {}, None,
        (), {}, (), {}, None, "PASS", {}, (), "",
    )
    content = bundle.to_dict()
    for key in ("bundle_id", "created_at", "bundle_hash", "certificate_hash",
                "proposed_decision", "assurance", "decision_sufficient_evidence",
                "policy_version", "policy_hash", "calibration_status", "replay", "certificate_version"):
        content.pop(key)
    bundle = replace(bundle, bundle_hash=canonical_hash(content))
    assert verify_decision_bundle(bundle)
    assert not verify_decision_certificate(bundle, calibrated_engine().policy)
    assert not verify_decision_certificate(replace(bundle, certificate_version="decision-certificate-v0.4"))


def test_certificate_hash_removal_cannot_downgrade_v04_bundle():
    state = FinancialRiskAgent(ROOT).run("Certificate downgrade", 2025, {"cash": 10})
    payload = dict(state.decision_bundle)
    assert verify_decision_certificate(payload)
    payload.update(certificate_hash="", assurance={}, final_decision="PASS")
    from finrisk.enterprise.decision import material_decision_payload

    payload["bundle_hash"] = canonical_hash(material_decision_payload({
        key: value for key, value in payload.items()
        if key not in {"bundle_id", "created_at", "bundle_hash", "certificate_hash"}
    }))
    assert not verify_decision_bundle(DecisionBundle(**payload))
    assert not verify_decision_certificate(payload)


def test_rehashed_certificate_cannot_lose_its_evidence_paths():
    engine = calibrated_engine()
    paths = [path("a"), path("b")]
    result = engine.evaluate(input_for(*paths, reference=REFERENCE))
    bundle = build_decision_bundle(
        "org", "entity", {}, {}, {}, {}, paths, {}, [], {}, result.final_decision,
        assurance=result.to_dict(), assurance_policy=engine.policy,
    )
    assert verify_decision_certificate(bundle, engine.policy)
    payload = bundle.to_dict()
    payload["evidence_paths"] = []
    from finrisk.enterprise.decision import material_decision_payload

    digest = canonical_hash(material_decision_payload({
        key: value for key, value in payload.items()
        if key not in {"bundle_id", "created_at", "bundle_hash", "certificate_hash"}
    }))
    payload.update(bundle_hash=digest, certificate_hash=digest)
    assert not verify_decision_certificate(payload, engine.policy)


def test_optional_policy_verification_without_policy_is_integrity_only():
    engine = AssuranceEngine(AssurancePolicy(
        maturity=PolicyMaturity.CALIBRATED_INTERNAL,
        require_distribution_reference=False, require_calibration_for_automation=False,
    ))
    result = engine.evaluate(input_for(path("a"), path("b"), calibration=CalibrationStatus.UNCALIBRATED))
    bundle = build_decision_bundle(
        "org", "entity", {}, {}, {}, {}, [path("a"), path("b")], {}, [], {}, result.final_decision,
        assurance=result.to_dict(), assurance_policy=engine.policy,
    )
    assert verify_decision_bundle(bundle)
    assert verify_decision_bundle(bundle, engine.policy)
    assert not verify_decision_bundle(bundle, calibrated_engine().policy)


def test_synthetic_end_to_end_certificate_is_replayable_and_deterministic():
    fixture = json.loads((ROOT / "examples" / "synthetic_company.json").read_text())
    reference = load_reference_profile(
        ROOT / "research" / "v040_development" / "development_reference.json"
    )
    source_map = {}
    for name, value in fixture["current"].items():
        source_map[name] = [
            Evidence(
                "synthetic filing",
                1,
                f"{name}={value}",
                fixture["fiscal_year"],
                verified=True,
                verification_status="verified",
                company=fixture["company"],
                value=value,
                unit="USD",
            )
        ]
        if name in fixture["previous"]:
            previous = fixture["previous"][name]
            source_map[name].append(
                Evidence(
                    "synthetic filing",
                    1,
                    f"{name}={previous}",
                    fixture["fiscal_year"] - 1,
                    verified=True,
                    verification_status="verified",
                    company=fixture["company"],
                    value=previous,
                    unit="USD",
                )
            )
    agent = FinancialRiskAgent(ROOT)

    def run():
        return agent.run(
            fixture["company"],
            fixture["fiscal_year"],
            fixture["current"],
            fixture["previous"],
            {int(key): value for key, value in fixture["pages"].items()},
            source_map=source_map,
            assurance_reference=reference,
        )

    first, second = run(), run()
    assert first.assurance["distribution_validity"]["state"] == "IN_REFERENCE"
    assert first.assurance["distribution_validity"]["reference_scope"] == (
        "DEVELOPMENT_REFERENCE_ONLY"
    )
    assert first.decision_certificate["certificate_hash"] == (
        second.decision_certificate["certificate_hash"]
    )
    serialized = json.loads(json.dumps(first.decision_certificate))
    assert verify_decision_certificate(serialized, agent.pipeline.assurance.policy)
    snapshot = AnalysisSnapshot(**first.analysis_snapshot)
    assert replay_diff(snapshot, second.assessment)["classification"] == "IDENTICAL"
    serialized["policy_hash"] = "0" * 64
    assert not verify_decision_certificate(serialized, agent.pipeline.assurance.policy)
