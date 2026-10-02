from __future__ import annotations

from itertools import combinations
from typing import Any

from ..enterprise.fusion import hierarchical_escalation
from .domain import (
    DecisionSufficientEvidence,
    EvidenceDependency,
    EvidenceFragility,
    EvidenceFragilityState,
    SufficientEvidenceMethod,
)
from .policy import AssurancePolicy


def _retained_dependencies(
    dependencies: list[EvidenceDependency], retained: set[str]
) -> list[EvidenceDependency]:
    return [
        item
        for item in dependencies
        if item.verified
        and item.evidence_ids
        and set(item.evidence_ids).issubset(retained)
    ]


def _recompute(
    dependencies: list[EvidenceDependency],
    retained: set[str],
    material_path_count: int,
    fusion_policy: dict[str, float] | None,
) -> tuple[float | None, str, str, list[EvidenceDependency]]:
    active = _retained_dependencies(dependencies, retained)
    scores: dict[str, float | None] = {}
    for item in active:
        if item.score is None:
            continue
        current = scores.get(item.risk_dimension)
        scores[item.risk_dimension] = (
            item.score if current is None else max(current, item.score)
        )
    coverage = len(active) / material_path_count if material_path_count else 0.0
    result = hierarchical_escalation(scores, coverage, coverage, fusion_policy)
    return result.score, result.decision.value, result.severity, active


def analyze_fragility(
    dependencies: list[EvidenceDependency],
    baseline_score: float | None,
    baseline_decision: str,
    assurance_policy: AssurancePolicy,
    fusion_policy: dict[str, float] | None = None,
) -> EvidenceFragility:
    nodes = sorted(
        {
            evidence_id
            for item in dependencies
            if item.verified
            for evidence_id in item.evidence_ids
        }
    )
    if not nodes:
        return EvidenceFragility(
            EvidenceFragilityState.NOT_ESTIMABLE,
            None,
            0,
            None,
            0,
        )
    retained = set(nodes)
    baseline_recomputed = _recompute(
        dependencies, retained, len(dependencies), fusion_policy
    )
    baseline_severity = baseline_recomputed[2]
    ablations: list[dict[str, Any]] = []
    for evidence_id in nodes:
        score, decision, severity, active = _recompute(
            dependencies, retained - {evidence_id}, len(dependencies), fusion_policy
        )
        score_delta = (
            None
            if baseline_score is None or score is None
            else round(score - baseline_score, 6)
        )
        affected = [
            item
            for item in dependencies
            if item.verified and evidence_id in item.evidence_ids and item not in active
        ]
        ablations.append(
            {
                "evidence_id": evidence_id,
                "score_delta": score_delta,
                "severity_change": severity != baseline_severity,
                "proposed_decision_change": decision != baseline_decision,
                "final_decision_impact": decision != baseline_decision,
                "recomputed_proposed_decision": decision,
                "affected_dimensions": sorted({item.risk_dimension for item in affected}),
                "affected_claims": sorted(
                    {claim for item in affected for claim in item.claims}
                ),
            }
        )
    impacts = [abs(item["score_delta"]) for item in ablations if item["score_delta"] is not None]
    largest = max(impacts) if impacts else None
    flips = sum(item["proposed_decision_change"] for item in ablations)
    severity_changes = sum(item["severity_change"] for item in ablations)
    if flips or (largest is not None and largest >= assurance_policy.fragile_score_delta):
        state = EvidenceFragilityState.FRAGILE
    elif largest is not None and largest >= assurance_policy.sensitive_score_delta:
        state = EvidenceFragilityState.SENSITIVE
    else:
        state = EvidenceFragilityState.STABLE
    return EvidenceFragility(
        state=state,
        largest_single_evidence_impact=largest,
        decision_flip_count=flips,
        decision_flip_rate=round(flips / len(nodes), 6),
        severity_change_count=severity_changes,
        affected_dimensions=tuple(
            sorted({value for row in ablations for value in row["affected_dimensions"]})
        ),
        affected_claims=tuple(
            sorted({value for row in ablations for value in row["affected_claims"]})
        ),
        ablations=tuple(ablations),
    )

def decision_sufficient_evidence(
    dependencies: list[EvidenceDependency],
    baseline_decision: str,
    assurance_policy: AssurancePolicy,
    fusion_policy: dict[str, float] | None = None,
) -> DecisionSufficientEvidence:
    nodes = sorted(
        {
            evidence_id
            for item in dependencies
            if item.verified
            for evidence_id in item.evidence_ids
        }
    )
    if not nodes:
        return DecisionSufficientEvidence(
            (),
            SufficientEvidenceMethod.NOT_ESTIMABLE,
            False,
            False,
            0,
            baseline_decision,
        )

    evaluated = 0

    def preserves(candidate: set[str]) -> bool:
        nonlocal evaluated
        evaluated += 1
        _, decision, _, _ = _recompute(
            dependencies, candidate, len(dependencies), fusion_policy
        )
        return decision == baseline_decision

    if len(nodes) <= assurance_policy.maximum_fragility_nodes_exact:
        for size in range(1, len(nodes) + 1):
            for candidate in combinations(nodes, size):
                if preserves(set(candidate)):
                    return DecisionSufficientEvidence(
                        tuple(candidate),
                        SufficientEvidenceMethod.EXACT,
                        True,
                        True,
                        evaluated,
                        baseline_decision,
                    )
    else:
        candidate = set(nodes)
        for evidence_id in nodes:
            trial = candidate - {evidence_id}
            if trial and preserves(trial):
                candidate = trial
        return DecisionSufficientEvidence(
            tuple(sorted(candidate)),
            SufficientEvidenceMethod.GREEDY_APPROXIMATION,
            False,
            preserves(candidate),
            evaluated,
            baseline_decision,
        )
    return DecisionSufficientEvidence(
        tuple(nodes),
        SufficientEvidenceMethod.EXACT,
        True,
        preserves(set(nodes)),
        evaluated,
        baseline_decision,
    )
