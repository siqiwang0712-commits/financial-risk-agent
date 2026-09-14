from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .domain import AnalysisSnapshot, new_id


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


# `assessment["dimensions"]` is keyed by `scoring.CATEGORIES`. Exactly one of those
# keys does not match its `RiskDomain` spelling, so a decision path carrying it
# would never match a case opened in the corresponding domain.
#
# `service.transition` and `enterprise/api.create_case` used to keep a private copy
# of this map each, with four entries of which three were identity mappings that
# could never fire. Two copies of a gate that must agree is one copy too many: a
# divergence would let a case be created that could never be transitioned.
DIMENSION_TO_RISK_DOMAIN = {"accounting": "accounting_anomaly"}


def risk_domain_of_path(path: dict) -> str | None:
    """The `RiskDomain` value a decision path belongs to, or `None`."""
    return DIMENSION_TO_RISK_DOMAIN.get(path.get("risk_domain"), path.get("risk_domain"))


def verified_paths_for_domain(trace: dict, domain_value: str) -> list[dict]:
    """Verified decision paths that prove `domain_value`, with a source span.

    A path counts only when its evidence is `VERIFIED` *and* it carries at least
    one `source_evidence` entry -- an unsourced "verified" claim is not evidence.
    """
    return [
        path
        for path in trace.get("paths", [])
        if path.get("evidence_path_status") == "VERIFIED"
        and path.get("source_evidence")
        and risk_domain_of_path(path) == domain_value
    ]


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
            verified = bool(required_inputs) and all(
                provenance.get(name)
                and all(item.get("verification_status", "").casefold() == "verified" for item in provenance[name])
                for name in required_inputs
            )
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
        # `or {}` rather than `.get(key, {})`: the default only applies when the
        # key is *absent*, and this codebase uses `None` for "missing". A
        # contradiction carrying an explicit `None` evidence would have raised
        # `AttributeError` on `.get` one line later.
        evidence = [contradiction.get("evidence") or {}]
        # `.casefold()` for the same reason line 61 uses it: the producer writes
        # lower-case `verified` today, but two spellings of the same test inside
        # one function is a latent divergence, not a decision.
        verified = str(evidence[0].get("verification_status", "")).casefold() == "verified"
        # A narrative-vs-numeric conflict is a cross-modal review, not a fact about
        # the dimension the numbers happen to sit in. Filing it under the
        # contradiction's dimension made it indistinguishable from the rule paths
        # for that dimension, and left `RiskDomain.DISCLOSURE_TENSION` with no
        # producer at all -- so no case could ever be opened in it. The dimension is
        # still used below for `fusion_contribution.dimension_score`.
        paths.append(
            {
                "reason_code": f"DISCLOSURE_TENSION_{index + 1:03d}",
                "risk_domain": "disclosure_tension",
                "source_evidence": evidence,
                # A contradiction path's input is the narrative claim itself, not a
                # normalised metric, so there is no metric provenance. The keys are
                # still present (empty) because the frontend iterates them and an
                # undefined value crashed the Decision paths tab.
                "required_inputs": [],
                "input_provenance": {},
                "rule_or_model": "narrative_numeric_consistency",
                "rule_version": component_versions.get("rules", "UNPINNED"),
                "fusion_version": component_versions.get("fusion", "UNPINNED"),
                # `evidence[0]`, not `contradiction.get("evidence", {})`: the same
                # explicit-`None` hazard as above, and `evidence` is already the
                # normalised list.
                "confidence": evidence[0].get("confidence", 0.0),
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
