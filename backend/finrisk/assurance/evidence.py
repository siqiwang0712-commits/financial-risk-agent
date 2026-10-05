from __future__ import annotations

from typing import Any

from ..enterprise.decision import canonical_hash, verified_material_path
from .domain import (
    EvidenceAssurance,
    EvidenceAssuranceState,
    EvidenceDependency,
)


def evidence_identifier(value: dict[str, Any]) -> str:
    explicit = value.get("id") or value.get("evidence_id")
    if explicit:
        return str(explicit)
    material = {
        key: value.get(key)
        for key in (
            "source",
            "document",
            "source_hash",
            "page",
            "source_text",
            "fiscal_year",
            "concept",
            "unit",
            "raw_value",
            "normalized_value",
        )
        if value.get(key) is not None
    }
    return f"evidence_{canonical_hash(material)[:20]}"


def _verified_path(path: dict[str, Any]) -> bool:
    if path.get("rule_or_model") == "narrative_numeric_consistency":
        return verified_material_path(path)
    return path.get("evidence_path_status") == "VERIFIED"


def _path_evidence(path: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in path.get("source_evidence") or []:
        if isinstance(item, dict):
            evidence.append(item)
    for items in (path.get("input_provenance") or {}).values():
        if isinstance(items, list):
            evidence.extend(item for item in items if isinstance(item, dict))
    unique: dict[str, dict[str, Any]] = {}
    for item in evidence:
        unique[evidence_identifier(item)] = item
    return [unique[key] for key in sorted(unique)]


def dependencies_from_paths(paths: list[dict[str, Any]]) -> list[EvidenceDependency]:
    dependencies: list[EvidenceDependency] = []
    for index, path in enumerate(paths):
        evidence_ids = tuple(
            sorted(evidence_identifier(item) for item in _path_evidence(path))
        )
        contribution = path.get("fusion_contribution") or {}
        score = contribution.get("dimension_score")
        score = float(score) if isinstance(score, (int, float)) else None
        reason = str(path.get("reason_code") or f"path_{index}")
        claims = tuple(
            str(value)
            for value in (
                path.get("material_claim"),
                path.get("claim"),
                reason,
            )
            if value
        )
        dependencies.append(
            EvidenceDependency(
                dependency_id=reason,
                evidence_ids=evidence_ids,
                risk_dimension=str(path.get("risk_domain") or "unknown"),
                score=score,
                claims=claims,
                verified=_verified_path(path),
            )
        )
    return dependencies


def assess_evidence(
    paths: list[dict[str, Any]],
    minimum_verified_coverage: float,
    removed_evidence_ids: set[str] | None = None,
) -> EvidenceAssurance:
    material = len(paths)
    removed_evidence_ids = removed_evidence_ids or set()
    verified_paths = [
        path
        for path in paths
        if _verified_path(path)
        and not (
            removed_evidence_ids
            & {evidence_identifier(item) for item in _path_evidence(path)}
        )
    ]
    verified = len(verified_paths)
    coverage = verified / material if material else 0.0
    evidence_ids = {
        evidence_identifier(item)
        for path in verified_paths
        for item in _path_evidence(path)
    }
    claims = {
        str(path.get("material_claim") or path.get("reason_code"))
        for path in verified_paths
        if path.get("material_claim") or path.get("reason_code")
    }
    diagnostics: list[str] = []
    if not material:
        state = EvidenceAssuranceState.UNKNOWN
        diagnostics.append("No material decision path was supplied to assurance.")
    elif verified == 0:
        state = EvidenceAssuranceState.INSUFFICIENT
        diagnostics.append("No material path has complete verified provenance.")
    elif coverage < minimum_verified_coverage or verified < material:
        state = EvidenceAssuranceState.PARTIAL
        diagnostics.append("Only part of the material decision path is verified.")
    else:
        state = EvidenceAssuranceState.VERIFIED
    return EvidenceAssurance(
        state=state,
        material_path_count=material,
        verified_path_count=verified,
        coverage=round(coverage, 6),
        verified_evidence_ids=tuple(sorted(evidence_ids)),
        supported_claims=tuple(sorted(claims)),
        diagnostics=tuple(diagnostics),
    )
