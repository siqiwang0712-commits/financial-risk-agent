from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..enterprise.decision import canonical_hash
from ..enterprise.domain import Decision
from ..enterprise.integrity import CalibrationStatus
from .domain import (
    AssuranceResult,
    AssuranceStatus,
    DistributionValidityState,
    EvidenceAssuranceState,
    EvidenceFragilityState,
    FinancialFeatureVector,
    PolicyMaturity,
    ReportingObservabilityVector,
)
from .evidence import assess_evidence, dependencies_from_paths
from .fragility import analyze_fragility, decision_sufficient_evidence
from .policy import AssurancePolicy
from .reason_codes import AssuranceReasonCode
from .semantics import verify_structures, verify_transition
from .shift import ReferenceProfile, assess_distribution_validity


@dataclass(frozen=True)
class AssuranceInput:
    proposed_decision: str
    risk_score: float | None
    evidence_paths: tuple[dict[str, Any], ...]
    financial_features: FinancialFeatureVector
    reporting_observability: ReportingObservabilityVector
    sector: str | None = None
    disagreement: float = 0.0
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED
    reliability: float | None = None
    reference_profile: ReferenceProfile | None = None
    runtime_failures: tuple[str, ...] = ()
    fusion_policy: dict[str, float] | None = None


class AssuranceEngine:
    """The sole runtime authority allowed to issue a final decision."""

    def __init__(self, policy: AssurancePolicy | None = None):
        self.policy = policy or AssurancePolicy()

    def authorize(self, result: AssuranceResult | None) -> str:
        """Authorize only results bound to this engine's checked policy."""

        return authorized_final_decision(result, self.policy)

    def evaluate(self, value: AssuranceInput) -> AssuranceResult:
        proposed = Decision(value.proposed_decision)
        paths = [dict(path) for path in value.evidence_paths]
        evidence = assess_evidence(paths, self.policy.minimum_verified_coverage)
        dependencies = dependencies_from_paths(paths)
        fragility = analyze_fragility(
            dependencies,
            value.risk_score,
            proposed.value,
            self.policy,
            value.fusion_policy,
        )
        sufficient = decision_sufficient_evidence(
            dependencies, proposed.value, self.policy, value.fusion_policy
        )
        distribution = assess_distribution_validity(
            value.financial_features,
            value.reporting_observability,
            value.sector,
            value.reference_profile,
        )
        reasons: list[str] = []
        blockers: list[str] = []
        abstain = False

        if evidence.state in {
            EvidenceAssuranceState.INSUFFICIENT,
            EvidenceAssuranceState.UNKNOWN,
        }:
            reasons.append(AssuranceReasonCode.INSUFFICIENT_VERIFIED_EVIDENCE.value)
            blockers.append("evidence")
            abstain = evidence.verified_path_count == 0
        elif evidence.state is EvidenceAssuranceState.PARTIAL:
            reasons.append(AssuranceReasonCode.INSUFFICIENT_VERIFIED_EVIDENCE.value)
            blockers.append("evidence")

        if fragility.state is EvidenceFragilityState.FRAGILE:
            reasons.append(AssuranceReasonCode.EVIDENCE_FRAGILITY_HIGH.value)
            blockers.append("fragility")
        elif (
            fragility.state is EvidenceFragilityState.NOT_ESTIMABLE
            and self.policy.review_on_fragility_not_estimable
        ):
            reasons.append(AssuranceReasonCode.EVIDENCE_FRAGILITY_NOT_ESTIMABLE.value)
            blockers.append("fragility_unknown")

        if distribution.state is DistributionValidityState.OUTSIDE_REFERENCE:
            reasons.append(AssuranceReasonCode.OUTSIDE_VALIDATED_DISTRIBUTION.value)
            blockers.append("distribution")
        elif (
            distribution.state is DistributionValidityState.UNKNOWN
            and self.policy.require_distribution_reference
        ):
            reasons.append(AssuranceReasonCode.DISTRIBUTION_VALIDITY_UNKNOWN.value)
            if self.policy.review_on_unknown_distribution:
                blockers.append("distribution_unknown")
        elif distribution.state is DistributionValidityState.WARNING:
            reasons.append(AssuranceReasonCode.REPORTING_OBSERVABILITY_ANOMALY.value)
            blockers.append("distribution_warning")

        if value.disagreement >= self.policy.maximum_disagreement:
            reasons.append(AssuranceReasonCode.HIGH_MODEL_DISAGREEMENT.value)
            blockers.append("disagreement")
        if value.runtime_failures:
            reasons.append(AssuranceReasonCode.RUNTIME_FAILURE_REQUIRES_REVIEW.value)
            blockers.append("runtime_failure")
            if any(
                name in {"parser_failure", "stale_data", "missing_evidence"}
                for name in value.runtime_failures
            ):
                abstain = True

        policy_status = self.policy.maturity
        if value.calibration_status is CalibrationStatus.UNCALIBRATED:
            reasons.append(AssuranceReasonCode.ASSURANCE_POLICY_UNCALIBRATED.value)
        elif policy_status is PolicyMaturity.HEURISTIC_POLICY:
            reasons.append(AssuranceReasonCode.CALIBRATION_SCOPE_MISMATCH.value)

        if proposed is Decision.ABSTAIN:
            final = Decision.ABSTAIN
            reasons.append(AssuranceReasonCode.PROPOSED_DECISION_WITHHELD.value)
        elif abstain:
            final = Decision.ABSTAIN
        elif blockers:
            final = Decision.REVIEW
        else:
            final = proposed

        calibrated = value.calibration_status in {
            CalibrationStatus.CALIBRATED_INTERNAL,
            CalibrationStatus.VALIDATED_EXTERNAL,
        }
        policy_mature = policy_status in {
            PolicyMaturity.CALIBRATED_INTERNAL,
            PolicyMaturity.VALIDATED_EXTERNAL,
        }
        automation_allowed = bool(
            not blockers
            and final in {Decision.PASS, Decision.FLAG}
            and policy_mature
            and (calibrated or not self.policy.require_calibration_for_automation)
        )
        if final != proposed:
            status = AssuranceStatus.FAILED
        elif automation_allowed:
            status = AssuranceStatus.PASSED
        else:
            status = AssuranceStatus.RESTRICTED

        reason_codes = tuple(dict.fromkeys(reasons))
        diagnostics = {
            "authorization_blockers": tuple(blockers),
            "runtime_failures": value.runtime_failures,
            "reliability": value.reliability if calibrated else None,
            "probability": None,
        }
        content = {
            "proposed_decision": proposed.value,
            "final_decision": final.value,
            "automation_allowed": automation_allowed,
            "assurance_status": status.value,
            "evidence_assurance": evidence.to_dict(),
            "evidence_fragility": fragility.to_dict(),
            "distribution_validity": distribution.to_dict(),
            "decision_sufficient_evidence": sufficient.to_dict(),
            "policy_status": policy_status.value,
            "calibration_status": value.calibration_status.value,
            "reason_codes": reason_codes,
            "policy_version": self.policy.version,
            "policy_hash": self.policy.policy_hash,
            "diagnostics": diagnostics,
        }
        return AssuranceResult(
            proposed_decision=proposed.value,
            final_decision=final.value,
            automation_allowed=automation_allowed,
            assurance_status=status,
            evidence_assurance=evidence,
            evidence_fragility=fragility,
            distribution_validity=distribution,
            decision_sufficient_evidence=sufficient,
            policy_status=policy_status,
            calibration_status=value.calibration_status.value,
            reason_codes=reason_codes,
            policy_version=self.policy.version,
            policy_hash=self.policy.policy_hash,
            certificate_hash=canonical_hash(content),
            diagnostics=diagnostics,
        )


def _authorization_content(result: AssuranceResult) -> dict[str, Any]:
    return {
        "proposed_decision": result.proposed_decision,
        "final_decision": result.final_decision,
        "automation_allowed": result.automation_allowed,
        "assurance_status": result.assurance_status.value,
        "evidence_assurance": result.evidence_assurance.to_dict(),
        "evidence_fragility": result.evidence_fragility.to_dict(),
        "distribution_validity": result.distribution_validity.to_dict(),
        "decision_sufficient_evidence": result.decision_sufficient_evidence.to_dict(),
        "policy_status": result.policy_status.value,
        "calibration_status": result.calibration_status,
        "reason_codes": result.reason_codes,
        "policy_version": result.policy_version,
        "policy_hash": result.policy_hash,
        "diagnostics": result.diagnostics,
    }


def verify_assurance_result(
    result: AssuranceResult, expected_policy: AssurancePolicy | None = None
) -> bool:
    return verify_assurance_payload(result.to_dict(), expected_policy)


def verify_assurance_payload(
    value: Mapping[str, Any] | None,
    expected_policy: AssurancePolicy | None = None,
) -> bool:
    """Verify a serialized AssuranceResult at persistence/publication boundaries."""

    if not isinstance(value, Mapping):
        return False
    required = {
        "proposed_decision",
        "final_decision",
        "automation_allowed",
        "assurance_status",
        "evidence_assurance",
        "evidence_fragility",
        "distribution_validity",
        "decision_sufficient_evidence",
        "policy_status",
        "calibration_status",
        "reason_codes",
        "policy_version",
        "policy_hash",
        "certificate_hash",
        "diagnostics",
    }
    if set(value) != required:
        return False
    if (not isinstance(value["policy_version"], str) or not value["policy_version"]
            or not isinstance(value["policy_hash"], str) or len(value["policy_hash"]) != 64
            or any(c not in "0123456789abcdef" for c in value["policy_hash"])):
        return False
    if not isinstance(value["automation_allowed"], bool):
        return False
    content = {key: value[key] for key in required - {"certificate_hash"}}
    try:
        if not verify_structures(value, expected_policy):
            return False
        if canonical_hash(content) != value["certificate_hash"]:
            return False
        proposed = Decision(value["proposed_decision"])
        final = Decision(value["final_decision"])
        status = AssuranceStatus(value["assurance_status"])
        evidence_state = EvidenceAssuranceState(value["evidence_assurance"]["state"])
        fragility_state = EvidenceFragilityState(value["evidence_fragility"]["state"])
        distribution_state = DistributionValidityState(
            value["distribution_validity"]["state"]
        )
        maturity = PolicyMaturity(value["policy_status"])
        calibration = CalibrationStatus(value["calibration_status"])
        reason_codes = {AssuranceReasonCode(code) for code in value["reason_codes"]}
        evidence = value["evidence_assurance"]
        material = evidence["material_path_count"]
        verified = evidence["verified_path_count"]
        coverage = evidence["coverage"]
        if (type(material) is not int or type(verified) is not int
                or not 0 <= verified <= material
                or type(coverage) not in {int, float} or not isfinite(coverage)
                or coverage != round(verified / material if material else 0.0, 6)):
            return False
        expected_evidence_state = (
            EvidenceAssuranceState.UNKNOWN if material == 0 else
            EvidenceAssuranceState.INSUFFICIENT if verified == 0 else
            EvidenceAssuranceState.PARTIAL if verified < material or (
                expected_policy is not None
                and verified / material < expected_policy.minimum_verified_coverage
            ) else EvidenceAssuranceState.VERIFIED
        )
        if evidence_state is not expected_evidence_state:
            return False
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        return False
    if expected_policy is not None and (
        value["policy_version"] != expected_policy.version
        or value["policy_hash"] != expected_policy.policy_hash
        or maturity is not expected_policy.maturity
    ):
        return False
    if status is AssuranceStatus.PASSED and not value["automation_allowed"]:
        return False
    diagnostics = value["diagnostics"]
    if not isinstance(diagnostics, Mapping):
        return False
    blockers = diagnostics.get("authorization_blockers")
    failures = diagnostics.get("runtime_failures")
    if not isinstance(blockers, (list, tuple)) or not isinstance(failures, (list, tuple)):
        return False
    # A restricted (non-automated) PASS/FLAG is still a final decision. It must
    # satisfy the same evidence and runtime blockers as the engine's evaluator.
    if final in {Decision.PASS, Decision.FLAG} and (
        evidence_state is not EvidenceAssuranceState.VERIFIED
        or blockers or failures
        or distribution_state in {
            DistributionValidityState.WARNING, DistributionValidityState.OUTSIDE_REFERENCE,
        }
        or (distribution_state is DistributionValidityState.UNKNOWN
            and expected_policy is not None
            and expected_policy.require_distribution_reference
            and expected_policy.review_on_unknown_distribution)
    ):
        return False
    if verified == 0 and final is not Decision.ABSTAIN and proposed is not Decision.ABSTAIN:
        return False
    if proposed is Decision.ABSTAIN and final is not Decision.ABSTAIN:
        return False
    fragility_blocks = fragility_state is EvidenceFragilityState.FRAGILE or (
        fragility_state is EvidenceFragilityState.NOT_ESTIMABLE
        and expected_policy is not None
        and expected_policy.review_on_fragility_not_estimable
    )
    if fragility_blocks and (value["automation_allowed"] or final in {Decision.PASS, Decision.FLAG}):
        return False
    if value["automation_allowed"] and (
            final is not proposed
            or final not in {Decision.PASS, Decision.FLAG}
            or status is not AssuranceStatus.PASSED
            or evidence_state is not EvidenceAssuranceState.VERIFIED
            or maturity is PolicyMaturity.HEURISTIC_POLICY
            or (calibration is CalibrationStatus.UNCALIBRATED
                and expected_policy is not None
                and expected_policy.require_calibration_for_automation)
    ):
        return False
    if final is not proposed and status is not AssuranceStatus.FAILED:
        return False
    if status is AssuranceStatus.RESTRICTED and (
        final is not proposed or value["automation_allowed"]
    ):
        return False
    expected_status = (
        AssuranceStatus.FAILED if final is not proposed else
        AssuranceStatus.PASSED if value["automation_allowed"] else AssuranceStatus.RESTRICTED
    )
    if status is not expected_status or (final is not proposed and final not in {Decision.REVIEW, Decision.ABSTAIN}):
        return False
    if calibration is CalibrationStatus.UNCALIBRATED:
        if (
            diagnostics.get("probability") is not None
            or diagnostics.get("reliability") is not None
        ):
            return False
        if AssuranceReasonCode.ASSURANCE_POLICY_UNCALIBRATED not in reason_codes:
            return False
    return verify_transition(value, expected_policy)


def authorized_final_decision(
    result: AssuranceResult | None, expected_policy: AssurancePolicy
) -> str:
    """Enforce the v0.4 authority invariant at every publication boundary."""

    if not isinstance(result, AssuranceResult) or not verify_assurance_result(
        result, expected_policy
    ):
        raise ValueError("no valid AssuranceResult; final decision is not authorized")
    return result.final_decision
