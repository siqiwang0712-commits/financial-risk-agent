from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .domain import AnalysisSnapshot, new_id


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


NON_MATERIAL_REPLAY_FIELDS = frozenset({"latency_ms", "created_at"})


def verified_numeric_inputs(required_inputs: list, provenance: dict) -> bool:
    if not isinstance(required_inputs, list) or not required_inputs or not isinstance(provenance, dict):
        return False
    for name in required_inputs:
        if not isinstance(name, str):
            return False
        references = provenance.get(name)
        if not isinstance(references, list) or not references:
            return False
        if any(
            not isinstance(item, dict)
            or str(item.get("verification_status", "")).casefold() != "verified"
            for item in references
        ):
            return False
    return True


def verified_material_path(path: dict) -> bool:
    """Reject legacy quote-only numeric contradictions at workflow proof gates."""
    if not isinstance(path, dict):
        return False
    evidence = path.get("source_evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, dict) for item in evidence):
        return False
    return isinstance(path, dict) and (
        path.get("evidence_path_status") == "VERIFIED"
        and bool(path.get("source_evidence"))
        and (
            path.get("rule_or_model") != "narrative_numeric_consistency"
            or (
                all(
                    isinstance(item, dict) and item.get("verification_status") == "verified"
                    for item in evidence
                )
                and verified_numeric_inputs(
                    path.get("required_inputs", []), path.get("input_provenance", {})
                )
            )
        )
    )


def material_decision_payload(value: Any) -> Any:
    """Remove operational telemetry that must not change decision identity."""

    if isinstance(value, dict):
        return {
            key: material_decision_payload(item)
            for key, item in value.items()
            if key not in NON_MATERIAL_REPLAY_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [material_decision_payload(item) for item in value]
    return value


def build_decision_trace(
    assessment: dict, fusion: dict, component_versions: dict[str, str] | None = None
) -> dict:
    component_versions = component_versions or {}
    rules = {item["rule_id"]: item for item in assessment.get("triggered_rules", [])}
    paths = []
    for domain, dimension in assessment.get("dimensions", {}).items():
        for reason_code in dimension.get("key_drivers", []):
            signal = rules.get(reason_code, {})
            evidence = signal.get("source_refs", [])
            required_inputs = signal.get("required_inputs", [])
            provenance = signal.get("input_provenance", {})
            verified = verified_numeric_inputs(required_inputs, provenance)
            paths.append(
                {
                    "reason_code": reason_code,
                    "risk_domain": domain,
                    "source_evidence": evidence,
                    "required_inputs": required_inputs,
                    "input_provenance": provenance,
                    "rule_or_model": signal.get("family") or reason_code,
                    "rule_version": component_versions.get("rules", "UNPINNED"),
                    "fusion_version": component_versions.get("fusion", "UNPINNED"),
                    "confidence": assessment.get("confidence"),
                    "coverage": dimension.get("coverage", 0.0),
                    "disagreement": fusion.get("disagreement", 0.0),
                    "fusion_contribution": {
                        "method": fusion.get("method"),
                        "dimension_score": dimension.get("score"),
                        "role": "escalator"
                        if domain in fusion.get("drivers", [])
                        else "supporting",
                    },
                    "decision_dependency": {
                        "proposed_decision": fusion.get(
                            "proposed_decision", fusion.get("decision")
                        ),
                        "risk_dimension": domain,
                        "computational_contribution": dimension.get("score"),
                    },
                    "evidence_path_status": "VERIFIED" if verified else "UNVERIFIED",
                    "path": [
                        "document",
                        "evidence_span",
                        "fact",
                        "metric",
                        "rule/model",
                        "dimension",
                        "fusion",
                        "decision",
                    ],
                }
            )
    for index, contradiction in enumerate(assessment.get("contradictions", [])):
        evidence = [contradiction.get("evidence", {})]
        required_inputs = contradiction.get("required_inputs", [])
        provenance = contradiction.get("input_provenance", {})
        verified = (
            evidence[0].get("verification_status") == "verified"
            and verified_numeric_inputs(required_inputs, provenance)
        )
        paths.append(
            {
                "reason_code": f"DISCLOSURE_TENSION_{index + 1:03d}",
                "risk_domain": contradiction.get("category", "disclosure_tension"),
                "source_evidence": evidence,
                "required_inputs": required_inputs,
                "input_provenance": provenance,
                "rule_or_model": "narrative_numeric_consistency",
                "rule_version": component_versions.get("rules", "UNPINNED"),
                "fusion_version": component_versions.get("fusion", "UNPINNED"),
                "confidence": contradiction.get("evidence", {}).get("confidence", 0.0),
                "coverage": 1.0 if verified else 0.0,
                "disagreement": fusion.get("disagreement", 0.0),
                "fusion_contribution": {
                    "method": fusion.get("method"),
                    "dimension_score": assessment.get("dimensions", {})
                    .get(contradiction.get("category"), {})
                    .get("score"),
                    "role": "cross_modal_review",
                },
                "decision_dependency": {
                    "proposed_decision": fusion.get(
                        "proposed_decision", fusion.get("decision")
                    ),
                    "risk_dimension": contradiction.get(
                        "category", "disclosure_tension"
                    ),
                    "computational_contribution": assessment.get(
                        "dimensions", {}
                    )
                    .get(contradiction.get("category"), {})
                    .get("score"),
                },
                "evidence_path_status": "VERIFIED" if verified else "UNVERIFIED",
                "path": [
                    "document",
                    "evidence_span",
                    "claim",
                    "consistency_check",
                    "dimension",
                    "fusion",
                    "decision",
                ],
            }
        )
    valid = sum(path["evidence_path_status"] == "VERIFIED" for path in paths)
    return {
        "proposed_decision": fusion.get(
            "proposed_decision", fusion.get("decision")
        ),
        # v0.3 compatibility alias. Assurance later writes the authorized
        # ``final_decision`` without mutating this proposal record.
        "decision": fusion.get("proposed_decision", fusion.get("decision")),
        "decision_reason_codes": fusion.get("reason_codes", []),
        "paths": paths,
        "verified_path_count": valid,
        "material_path_count": len(paths),
        "proof_coverage": round(valid / len(paths), 3) if paths else 0.0,
    }


def create_snapshot(
    organization_id: str,
    entity_id: str,
    frozen_input: dict,
    frozen_output: dict,
    document_versions: dict[str, str],
    component_versions: dict[str, str],
) -> AnalysisSnapshot:
    frozen_input = deepcopy(frozen_input)
    frozen_output = deepcopy(frozen_output)
    document_versions = deepcopy(document_versions)
    component_versions = deepcopy(component_versions)
    return AnalysisSnapshot(
        new_id("snapshot"),
        organization_id,
        entity_id,
        canonical_hash(material_decision_payload(frozen_input)),
        canonical_hash(material_decision_payload(frozen_output)),
        document_versions,
        component_versions,
        frozen_input,
        frozen_output,
    )


def replay_diff(snapshot: AnalysisSnapshot, replayed_output: dict) -> dict:
    replay_hash = canonical_hash(material_decision_payload(replayed_output))
    match = replay_hash == snapshot.output_hash
    return {
        "snapshot_id": snapshot.id,
        "historical_output_hash": snapshot.output_hash,
        "replayed_output_hash": replay_hash,
        "match": match,
        "classification": "IDENTICAL" if match else "DRIFT_DETECTED",
    }


def replay_snapshot(
    snapshot: AnalysisSnapshot, runner, current_component_versions: dict[str, str]
) -> dict:
    version_match = current_component_versions == snapshot.component_versions
    if not version_match:
        return {
            "snapshot_id": snapshot.id,
            "status": "VERSION_MISMATCH",
            "historical_result": snapshot.frozen_output,
            "recomputed_result": None,
            "version_diff": {
                key: {
                    "historical": snapshot.component_versions.get(key),
                    "current": current_component_versions.get(key),
                }
                for key in sorted(
                    set(snapshot.component_versions) | set(current_component_versions)
                )
                if snapshot.component_versions.get(key)
                != current_component_versions.get(key)
            },
        }
    recomputed = runner(snapshot.frozen_input)
    return {
        "snapshot_id": snapshot.id,
        "status": "REPLAYED",
        "historical_result": snapshot.frozen_output,
        "recomputed_result": recomputed,
        "diff": replay_diff(snapshot, recomputed),
    }
