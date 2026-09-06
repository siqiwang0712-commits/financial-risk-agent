from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .decision import canonical_hash


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
    bundle_hash: str

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
) -> DecisionBundle:
    created_at = datetime.now(UTC).isoformat()
    input_hash, output_hash = canonical_hash(frozen_input), canonical_hash(frozen_output)
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
    }
    digest = canonical_hash(content)
    return DecisionBundle(f"bundle_{digest[:20]}", organization_id, entity_id, created_at, document_hashes, input_hash, output_hash, risk_state, risk_delta, tuple(evidence_paths), calculations, tuple(agent_trace), component_versions, human_review, final_decision, digest)


def verify_decision_bundle(bundle: DecisionBundle) -> bool:
    content = bundle.to_dict()
    for key in ("bundle_id", "created_at", "bundle_hash"):
        content.pop(key)
    return canonical_hash(content) == bundle.bundle_hash
