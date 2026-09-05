from __future__ import annotations

import hashlib
import json
from typing import Any

from .domain import AnalysisSnapshot, new_id


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


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
            verified = any(
                item.get("verification_status") in {"verified", "located"}
                for item in evidence
            )
            paths.append(
                {
                    "reason_code": reason_code,
                    "risk_domain": domain,
                    "source_evidence": evidence,
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
        verified = evidence[0].get("verification_status") == "verified"
        paths.append(
            {
                "reason_code": f"DISCLOSURE_TENSION_{index + 1:03d}",
                "risk_domain": contradiction.get("category", "disclosure_tension"),
                "source_evidence": evidence,
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
        "decision": fusion.get("decision"),
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
    return AnalysisSnapshot(
        new_id("snapshot"),
        organization_id,
        entity_id,
        canonical_hash(frozen_input),
        canonical_hash(frozen_output),
        document_versions,
        component_versions,
        frozen_input,
        frozen_output,
    )


def replay_diff(snapshot: AnalysisSnapshot, replayed_output: dict) -> dict:
    replay_hash = canonical_hash(replayed_output)
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
