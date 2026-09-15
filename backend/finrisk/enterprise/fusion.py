from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from statistics import pstdev

from ..severity import severity_key
from .domain import Decision, FusionResult
from .integrity import DecisionReasonCode

DEFAULT_DECISION_POLICY = {
    "minimum_coverage": 0.4,
    "maximum_disagreement": 0.45,
    "flag_score": 60.0,
    "review_score": 40.0,
}

FUSION_POLICY_KEYS = frozenset(
    {
        "minimum_coverage",
        "maximum_disagreement",
        "flag_score",
        "review_score",
        "severe_dimension_score",
        "critical_dimension_score",
        "elevated_dimension_score",
        "interaction_dimension_score",
        "interaction_premium",
        "interaction_uplift_per_dimension",
        "interaction_uplift_cap",
    }
)
_POLICY_METADATA_KEYS = frozenset({"version", "status"})


def validate_fusion_inputs(
    scores: dict[str, float | None],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> dict:
    """Validate the numeric domain and ordering used by every fusion method."""
    numeric_values = [value for value in scores.values() if value is not None]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 100
        for value in numeric_values
    ):
        raise ValueError("fusion scores must be finite and within [0, 100]")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in (coverage, confidence)
    ):
        raise ValueError("coverage and confidence must be finite and within [0, 1]")
    if weights is not None and any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in weights.values()
    ):
        raise ValueError("fusion weights must be finite and non-negative")

    supplied = policy or {}
    unknown = set(supplied) - FUSION_POLICY_KEYS - _POLICY_METADATA_KEYS
    if unknown:
        raise ValueError(f"unknown fusion policy keys: {sorted(unknown)}")
    effective = DEFAULT_DECISION_POLICY | {
        key: value for key, value in supplied.items() if key in FUSION_POLICY_KEYS
    }
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in effective.values()
    ):
        raise ValueError("fusion policy values must be finite numbers")
    for key in ("minimum_coverage", "maximum_disagreement"):
        if not 0 <= effective[key] <= 1:
            raise ValueError(f"{key} must be within [0, 1]")
    for key in (
        "flag_score",
        "review_score",
        "severe_dimension_score",
        "critical_dimension_score",
        "elevated_dimension_score",
        "interaction_dimension_score",
    ):
        if key in effective and not 0 <= effective[key] <= 100:
            raise ValueError(f"{key} must be within [0, 100]")
    if effective["review_score"] > effective["flag_score"]:
        raise ValueError("review_score must not exceed flag_score")
    ordered = [
        effective.get("elevated_dimension_score", 50),
        effective.get("severe_dimension_score", 70),
        effective.get("critical_dimension_score", 80),
    ]
    if ordered != sorted(ordered):
        raise ValueError("dimension thresholds must be elevated <= severe <= critical")
    for key in (
        "interaction_premium",
        "interaction_uplift_per_dimension",
        "interaction_uplift_cap",
    ):
        if key in effective and effective[key] < 0:
            raise ValueError(f"{key} must be non-negative")
    return effective


def _severity(score: float | None) -> str:
    return severity_key(score)


def _final(
    method: str,
    score: float | None,
    coverage: float,
    confidence: float,
    disagreement: float,
    drivers: list[str],
    rationale: str,
    policy: dict[str, float] | None = None,
    critical_dimension: bool = False,
) -> FusionResult:
    policy = DEFAULT_DECISION_POLICY | (policy or {})
    reason_codes: list[str] = []
    if score is None or coverage < policy["minimum_coverage"]:
        decision = Decision.ABSTAIN
        reason_codes.append(DecisionReasonCode.INSUFFICIENT_EVIDENCE.value)
    elif disagreement >= policy["maximum_disagreement"]:
        # REVIEW ("needs human review") is the escalation state, ranked above FLAG
        # in `Decision`. High dispersion means the aggregate is not trustworthy
        # enough to act on automatically, so it is deliberately escalated. See
        # `DISPOSITION_RANK` in `failure_aware_decision` for the shared ordering.
        decision = Decision.REVIEW
        reason_codes.append(DecisionReasonCode.HIGH_MODEL_DISAGREEMENT.value)
    elif score >= policy["flag_score"]:
        decision = Decision.FLAG
    elif score >= policy["review_score"]:
        decision = Decision.REVIEW
    else:
        decision = Decision.PASS
    if critical_dimension:
        reason_codes.append(DecisionReasonCode.CRITICAL_DIMENSION_ESCALATION.value)
    elif score is not None and score >= policy.get("critical_dimension_score", 80):
        reason_codes.append(DecisionReasonCode.AGGREGATE_CRITICAL_SCORE.value)
    reason_codes.append(DecisionReasonCode.UNVALIDATED_RELIABILITY.value)
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
        evidence_quality=round(confidence, 3),
        reliability=None,
        reliability_status="UNCALIBRATED",
        reason_codes=reason_codes,
    )


def weighted_average(
    scores: dict[str, float | None],
    weights: dict[str, float],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    validate_fusion_inputs(scores, coverage, confidence, policy, weights)
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
    validate_fusion_inputs(scores, coverage, confidence, policy)
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
        bool(
            score is not None
            and score
            >= (DEFAULT_DECISION_POLICY | (policy or {})).get(
                "critical_dimension_score", 80
            )
        ),
    )


def hierarchical_escalation(
    scores: dict[str, float | None],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    validate_fusion_inputs(scores, coverage, confidence, policy)
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
    # Non-compensatory floor: a supported adverse dimension cannot be averaged
    # away by ordinary dimensions. Adding another adverse score therefore cannot
    # lower the aggregate. Missing dimensions are excluded, never treated as safe.
    score = None
    disagreement = 0.0
    if active:
        maximum = max(active.values())
        # Configured so the frozen component version detects parameter changes.
        interaction_uplift = min(
            effective.get("interaction_uplift_cap", 15.0),
            effective.get("interaction_uplift_per_dimension", 5.0)
            * max(0, len(elevated) - 1),
        )
        score = maximum + interaction_uplift
        values = list(active.values())
        disagreement = min(1.0, pstdev(values) / 50) if len(values) > 1 else 0.0
    return _final(
        "hierarchical_escalation",
        min(100, score) if score is not None else None,
        coverage,
        confidence,
        disagreement,
        severe or elevated,
        "Coverage-aware non-compensatory fusion; the highest supported dimension is a monotonic floor and missing dimensions are excluded",
        policy,
        bool(
            active
            and max(active.values())
            >= effective.get("critical_dimension_score", 80)
        ),
    )


def interaction_aware(
    scores: dict[str, float | None],
    coverage: float,
    confidence: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    validate_fusion_inputs(scores, coverage, confidence, policy)
    # Non-compensatory baseline. A weighted average let a supported adverse
    # dimension be diluted by otherwise low dimensions: {liquidity:90,
    # solvency_leverage:60} scored 83/FLAG, but adding cash_flow:0 (i.e. *no*
    # cash-flow risk) pulled it to 58/REVIEW. The interaction premium is added to
    # the strongest supported dimension instead, so extra dimensions can only
    # raise the score.
    active = {key: value for key, value in scores.items() if value is not None}
    effective = DEFAULT_DECISION_POLICY | (policy or {})
    baseline = max(active.values()) if active else None
    values = list(active.values())
    disagreement = min(1.0, pstdev(values) / 50) if len(values) > 1 else 0.0
    interactions = [
        ("liquidity", "solvency_leverage"),
        ("profitability", "cash_flow"),
        ("earnings_quality", "accounting"),
    ]
    interaction_threshold = effective.get("interaction_dimension_score", 50)
    # A pair is evaluable only when BOTH dimensions carry a supported score.
    # `active` already excludes unsupported dimensions, so a default of 0 would
    # silently read "unknown" as "no risk" (missing must never mean safe).
    triggered = [
        f"{a}+{b}"
        for a, b in interactions
        if active.get(a) is not None
        and active.get(b) is not None
        and active[a] >= interaction_threshold
        and active[b] >= interaction_threshold
    ]
    indeterminate = [
        f"{a}+{b}"
        for a, b in interactions
        if (active.get(a) is None) != (active.get(b) is None)
    ]
    score = (
        None
        if baseline is None
        else min(
            100, baseline + effective.get("interaction_premium", 8) * len(triggered)
        )
    )
    outcome = _final(
        "interaction_aware",
        score,
        coverage,
        confidence,
        disagreement,
        triggered or sorted(active, key=active.get, reverse=True)[:3],
        "Transparent pairwise interaction premiums applied to the strongest supported dimension (non-compensatory baseline)",
        policy,
    )
    if indeterminate:
        # Surface the unresolved pair instead of reporting an evaluated "no interaction".
        outcome.reason_codes.append(
            DecisionReasonCode.CLAIM_CONTEXT_INCOMPLETE.value
        )
    return outcome


FUSION_METHODS: dict[str, Callable] = {
    "weighted_average": weighted_average,
    "max_severity": max_severity,
    "hierarchical_escalation": hierarchical_escalation,
    "interaction_aware": interaction_aware,
}


@dataclass(frozen=True)
class RiskContribution:
    dimension: str
    score: float
    evidence_id: str
    verified: bool = True
    evidence_group: str | None = None


def deduplicate_contributions(
    contributions: list[RiskContribution],
) -> tuple[list[RiskContribution], int]:
    """Cap a correlated evidence group to its strongest contribution per dimension.

    The cap is scoped to the dimension on purpose. A purely global cap can drop a
    whole risk dimension from the fusion input, which reduces the escalation count
    and therefore lowers the aggregate: adding adverse evidence would make the
    score go down. Scoping per dimension keeps fusion monotonic in adverse
    evidence while still suppressing duplicate citations of one disclosure.
    """
    unique: dict[tuple[str, str], RiskContribution] = {}
    for item in contributions:
        key = (item.dimension, item.evidence_group or item.evidence_id)
        if key not in unique or item.score > unique[key].score:
            unique[key] = item
    return list(unique.values()), len(contributions) - len(unique)


def fuse_verified_contributions(
    contributions: list[RiskContribution],
    coverage: float,
    evidence_quality: float,
    policy: dict[str, float] | None = None,
) -> FusionResult:
    unique, duplicate_count = deduplicate_contributions(contributions)
    verified = [item for item in unique if item.verified]
    by_dimension: dict[str, float] = {}
    for item in verified:
        by_dimension[item.dimension] = max(
            item.score, by_dimension.get(item.dimension, 0.0)
        )
    result = hierarchical_escalation(
        by_dimension, coverage, evidence_quality, policy
    )
    if any(
        item.score >= (DEFAULT_DECISION_POLICY | (policy or {})).get(
            "severe_dimension_score", 70
        )
        for item in verified
    ):
        result.reason_codes.append(DecisionReasonCode.SEVERE_VERIFIED_SIGNAL.value)
    if duplicate_count:
        result.reason_codes.append(
            DecisionReasonCode.DUPLICATE_EVIDENCE_SUPPRESSED.value
        )
    return result


# Response strength of a disposition. A failure signal may only move a decision
# *up* this scale; it may never weaken an already-stronger disposition.
# Ordering: PASS < FLAG < REVIEW < ABSTAIN. REVIEW ("human review required") ranks
# above FLAG because it is the more cautious response, and ABSTAIN (withhold) is
# the most cautious of all. This matches `Decision`'s declaration order and the
# escalation performed by `_final`.
DISPOSITION_RANK = {
    Decision.PASS: 0,
    Decision.FLAG: 1,
    Decision.REVIEW: 2,
    Decision.ABSTAIN: 3,
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
    from_failures = (
        Decision.ABSTAIN if blocking else Decision.REVIEW if review else result.decision
    )
    decision = (
        from_failures
        if DISPOSITION_RANK[from_failures] >= DISPOSITION_RANK[result.decision]
        else result.decision
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
