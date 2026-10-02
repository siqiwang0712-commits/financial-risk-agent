from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .decision import canonical_hash, material_decision_payload

if TYPE_CHECKING:
    from ..assurance.policy import AssurancePolicy


@dataclass(frozen=True)
class DecisionBundle:
    bundle_id: str
    organization_id: str
    entity_id: str
    created_at: str
    document_hashes: dict[str, str]
    input_hash: str
    output_hash: str
    risk_state: dict[str, Any]
    risk_delta: dict[str, Any] | None
    evidence_paths: tuple[dict[str, Any], ...]
    calculations: dict[str, Any]
    agent_trace: tuple[dict[str, Any], ...]
    component_versions: dict[str, str]
    human_review: dict[str, Any] | None
    final_decision: str
    epistemics: dict[str, Any]
    component_telemetry: tuple[dict[str, Any], ...]
    bundle_hash: str
    proposed_decision: str = "ABSTAIN"
    assurance: dict[str, Any] = field(default_factory=dict)
    decision_sufficient_evidence: dict[str, Any] = field(default_factory=dict)
    policy_version: str = "UNSPECIFIED"
    policy_hash: str = "UNSPECIFIED"
    calibration_status: str = "UNCALIBRATED"
    replay: dict[str, Any] = field(default_factory=dict)
    certificate_version: str = "decision-certificate-v0.4"
    certificate_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_decision_bundle(
    organization_id: str,
    entity_id: str,
    document_hashes: dict[str, str],
    frozen_input: dict[str, Any],
    frozen_output: dict[str, Any],
    risk_state: dict[str, Any],
    evidence_paths: list[dict[str, Any]],
    calculations: dict[str, Any],
    agent_trace: list[dict[str, Any]],
    component_versions: dict[str, str],
    final_decision: str,
    risk_delta: dict[str, Any] | None = None,
    human_review: dict[str, Any] | None = None,
    epistemics: dict[str, Any] | None = None,
    component_telemetry: list[dict[str, Any]] | None = None,
    proposed_decision: str | None = None,
    assurance: dict[str, Any] | None = None,
    decision_sufficient_evidence: dict[str, Any] | None = None,
    policy_version: str = "UNSPECIFIED",
    policy_hash: str = "UNSPECIFIED",
    calibration_status: str = "UNCALIBRATED",
    replay: dict[str, Any] | None = None,
    assurance_policy: AssurancePolicy | None = None,
) -> DecisionBundle:
    # Import locally to keep the Assurance domain independent from the legacy
    # bundle module while making v0.4 certificate creation fail closed.
    from ..assurance.engine import verify_assurance_payload

    document_hashes = deepcopy(document_hashes)
    frozen_input = deepcopy(frozen_input)
    frozen_output = deepcopy(frozen_output)
    risk_state = deepcopy(risk_state)
    risk_delta = deepcopy(risk_delta)
    evidence_paths = deepcopy(evidence_paths)
    calculations = deepcopy(calculations)
    agent_trace = deepcopy(agent_trace)
    component_versions = deepcopy(component_versions)
    human_review = deepcopy(human_review)
    epistemics = deepcopy(epistemics)
    component_telemetry = deepcopy(component_telemetry)
    assurance = deepcopy(assurance)
    decision_sufficient_evidence = deepcopy(decision_sufficient_evidence)
    replay = deepcopy(replay)
    proposed_decision = proposed_decision or final_decision
    if assurance_policy is None or not verify_assurance_payload(
        assurance, assurance_policy
    ):
        raise ValueError("a valid AssuranceResult is required for a Decision Certificate")
    if assurance["proposed_decision"] != proposed_decision:
        raise ValueError("certificate proposal does not match AssuranceResult")
    if assurance["final_decision"] != final_decision:
        raise ValueError("certificate final decision does not match AssuranceResult")
    decision_sufficient_evidence = (
        decision_sufficient_evidence
        or deepcopy(assurance["decision_sufficient_evidence"])
    )
    if policy_version == "UNSPECIFIED":
        policy_version = assurance["policy_version"]
    if policy_hash == "UNSPECIFIED":
        policy_hash = assurance["policy_hash"]
    if calibration_status == "UNCALIBRATED":
        calibration_status = assurance["calibration_status"]
    created_at = datetime.now(UTC).isoformat()
    input_hash = canonical_hash(material_decision_payload(frozen_input))
    output_hash = canonical_hash(material_decision_payload(frozen_output))
    content = {
        "organization_id": organization_id,
        "entity_id": entity_id,
        "document_hashes": document_hashes,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "risk_state": risk_state,
        "risk_delta": risk_delta,
        "evidence_paths": evidence_paths,
        "calculations": calculations,
        "agent_trace": agent_trace,
        "component_versions": component_versions,
        "human_review": human_review,
        "final_decision": final_decision,
        "epistemics": epistemics or {},
        "component_telemetry": component_telemetry or [],
        "proposed_decision": proposed_decision,
        "assurance": assurance or {},
        "decision_sufficient_evidence": decision_sufficient_evidence or {},
        "policy_version": policy_version,
        "policy_hash": policy_hash,
        "calibration_status": calibration_status,
        "replay": replay or {},
        "certificate_version": "decision-certificate-v0.4",
    }
    digest = canonical_hash(material_decision_payload(content))
    return DecisionBundle(
        bundle_id=f"bundle_{digest[:20]}",
        organization_id=organization_id,
        entity_id=entity_id,
        created_at=created_at,
        document_hashes=document_hashes,
        input_hash=input_hash,
        output_hash=output_hash,
        risk_state=risk_state,
        risk_delta=risk_delta,
        evidence_paths=tuple(evidence_paths),
        calculations=calculations,
        agent_trace=tuple(agent_trace),
        component_versions=component_versions,
        human_review=human_review,
        final_decision=final_decision,
        epistemics=epistemics or {},
        component_telemetry=tuple(component_telemetry or []),
        bundle_hash=digest,
        proposed_decision=proposed_decision,
        assurance=assurance or {},
        decision_sufficient_evidence=decision_sufficient_evidence or {},
        policy_version=policy_version,
        policy_hash=policy_hash,
        calibration_status=calibration_status,
        replay=replay or {},
        certificate_version="decision-certificate-v0.4",
        certificate_hash=digest,
    )


def verify_decision_bundle(
    bundle: DecisionBundle, assurance_policy: AssurancePolicy | None = None
) -> bool:
    if bundle.certificate_hash:
        from ..assurance.engine import verify_assurance_payload

        if (
            not verify_assurance_payload(bundle.assurance, assurance_policy)
            or bundle.assurance.get("proposed_decision") != bundle.proposed_decision
            or bundle.assurance.get("final_decision") != bundle.final_decision
            or bundle.assurance.get("policy_version") != bundle.policy_version
            or bundle.assurance.get("policy_hash") != bundle.policy_hash
            or bundle.assurance.get("calibration_status") != bundle.calibration_status
            or bundle.assurance.get("decision_sufficient_evidence")
            != bundle.decision_sufficient_evidence
        ):
            return False
    content = bundle.to_dict()
    for key in ("bundle_id", "created_at", "bundle_hash", "certificate_hash"):
        content.pop(key)
    digest = canonical_hash(material_decision_payload(content))
    if digest == bundle.bundle_hash and (
        not bundle.certificate_hash or digest == bundle.certificate_hash
    ):
        return True
    if bundle.certificate_hash:
        return False
    # A persisted v0.3 DecisionBundle is still verifiable after the dataclass
    # gains v0.4 defaults. Its original digest did not include these fields.
    for key in (
        "proposed_decision",
        "assurance",
        "decision_sufficient_evidence",
        "policy_version",
        "policy_hash",
        "calibration_status",
        "replay",
        "certificate_version",
    ):
        content.pop(key, None)
    return canonical_hash(content) == bundle.bundle_hash
