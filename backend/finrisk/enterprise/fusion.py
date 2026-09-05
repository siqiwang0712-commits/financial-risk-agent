from __future__ import annotations

from collections.abc import Callable
from statistics import mean, pstdev

from .domain import Decision, FusionResult

DEFAULT_DECISION_POLICY = {
    "minimum_coverage": 0.4,
    "maximum_disagreement": 0.45,
    "flag_score": 60.0,
    "review_score": 40.0,
}


def _severity(score: float | None) -> str:
    if score is None:
        return "unknown"
    return (
        "critical"
        if score >= 80
        else "high"
        if score >= 60
        else "moderate"
        if score >= 40
        else "low"
        if score >= 20
        else "very_low"
    )


def _final(
    method: str,
    score: float | None,
    coverage: float,
    confidence: float,
    disagreement: float,
    drivers: list[str],
    rationale: str,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    policy = DEFAULT_DECISION_POLICY | (policy or {})
    if score is None or coverage < policy["minimum_coverage"]:
        decision = Decision.ABSTAIN
    elif disagreement >= policy["maximum_disagreement"]:
        decision = Decision.REVIEW
    elif score >= policy["flag_score"]:
        decision = Decision.FLAG
    elif score >= policy["review_score"]:
        decision = Decision.REVIEW
    else:
        decision = Decision.PASS
    return FusionResult(
        method,
        _severity(score),
        None if score is None else round(score, 1),
        decision,
        round(coverage, 3),
        round(confidence, 3),
        round(disagreement, 3),
        drivers,
        rationale,
    )


def weighted_average(
    scores: dict[str, float | None],
    weights: dict[str, float],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    active = {
        key: value
        for key, value in scores.items()
        if value is not None and weights.get(key, 0) > 0
    }
    denominator = sum(weights[key] for key in active)
    score = (
        None
        if not denominator
        else sum(value * weights[key] for key, value in active.items()) / denominator
    )
    values = list(active.values())
    disagreement = min(1.0, pstdev(values) / 50) if len(values) > 1 else 0.0
    return _final(
        "weighted_average",
        score,
        coverage,
        confidence,
        disagreement,
        sorted(active, key=active.get, reverse=True)[:3],
        "Expert-weighted active dimensions; missing dimensions are not zero",
        policy,
    )


def max_severity(
    scores: dict[str, float | None],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    active = {key: value for key, value in scores.items() if value is not None}
    score = max(active.values()) if active else None
    return _final(
        "max_severity",
        score,
        coverage,
        confidence,
        0.0,
        [key for key, value in active.items() if value == score],
        "Highest supported dimension prevents concentrated-risk dilution",
        policy,
    )


def hierarchical_escalation(
    scores: dict[str, float | None],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    active = {key: value for key, value in scores.items() if value is not None}
    effective = DEFAULT_DECISION_POLICY | (policy or {})
    severe = [
        key
        for key, value in active.items()
        if value >= effective.get("severe_dimension_score", 70)
    ]
    elevated = [
        key
        for key, value in active.items()
        if value >= effective.get("elevated_dimension_score", 50)
    ]
    score = (
        max(active.values())
        if severe
        else mean(active.values()) + min(15, 5 * len(elevated))
        if active
        else None
    )
    return _final(
        "hierarchical_escalation",
        min(100, score) if score is not None else None,
        coverage,
        confidence,
        0.0,
        severe or elevated,
        "Severe dimensions escalate before portfolio averaging",
        policy,
    )


def interaction_aware(
    scores: dict[str, float | None],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    result = weighted_average(
        scores, {key: 1 for key in scores}, coverage, confidence, policy
    )
    active = {key: value for key, value in scores.items() if value is not None}
    interactions = [
        ("liquidity", "solvency_leverage"),
        ("profitability", "cash_flow"),
        ("earnings_quality", "accounting"),
    ]
    effective = DEFAULT_DECISION_POLICY | (policy or {})
    interaction_threshold = effective.get("interaction_dimension_score", 50)
    triggered = [
        f"{a}+{b}"
        for a, b in interactions
        if active.get(a, 0) >= interaction_threshold
        and active.get(b, 0) >= interaction_threshold
    ]
    score = (
        None
        if result.score is None
        else min(
            100, result.score + effective.get("interaction_premium", 8) * len(triggered)
        )
    )
    return _final(
        "interaction_aware",
        score,
        coverage,
        confidence,
        result.disagreement,
        triggered or result.drivers,
        "Transparent pairwise interaction premiums applied after equal-weight baseline",
        policy,
    )


FUSION_METHODS: dict[str, Callable] = {
    "weighted_average": weighted_average,
    "max_severity": max_severity,
    "hierarchical_escalation": hierarchical_escalation,
    "interaction_aware": interaction_aware,
}


def failure_aware_decision(
    result: FusionResult,
    failures: dict[str, bool],
    policy: dict[str, float] | None = None,
) -> dict:
    blocking = [
        name
        for name in ("parser_failure", "stale_data", "missing_evidence")
        if failures.get(name)
    ]
    review = [
        name
        for name in (
            "conflicting_evidence",
            "llm_unavailable",
            "rule_model_contradiction",
        )
        if failures.get(name)
    ]
    decision = (
        Decision.ABSTAIN if blocking else Decision.REVIEW if review else result.decision
    )
    return {
        "decision": decision.value,
        "degraded": bool(blocking or review),
        "blocking_failures": blocking,
        "review_failures": review,
    }


def sensitivity_analysis(
    scores: dict[str, float | None],
    base: FusionResult,
    delta: float = 5.0,
    policy: dict[str, float] | None = None,
) -> list[dict]:
    output = []
    for name, value in scores.items():
        if value is None:
            continue
        changed = dict(scores)
        changed[name] = min(100.0, value + delta)
        candidate = hierarchical_escalation(
            changed, base.evidence_coverage, base.decision_confidence, policy
        )
        output.append(
            {
                "input": name,
                "delta": delta,
                "score_change": None
                if base.score is None or candidate.score is None
                else round(candidate.score - base.score, 2),
                "decision_change": candidate.decision != base.decision,
            }
        )
    return sorted(output, key=lambda item: abs(item["score_change"] or 0), reverse=True)
