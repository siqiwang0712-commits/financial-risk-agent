from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from .domain import ModelRecord


def _finite_numbers(values, name: str) -> None:
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError(f"{name} must contain only finite numeric values")


def _probabilities(values, name: str) -> None:
    _finite_numbers(values, name)
    if any(not 0 <= value <= 1 for value in values):
        raise ValueError(f"{name} must be within [0, 1]")


@dataclass(frozen=True)
class ExperimentRun:
    dataset_version: str
    git_commit: str
    component: str
    component_version: str
    prompt_hash: str | None
    temperature: float | None
    seed: int | None
    rule_version: str
    fusion_version: str
    policy_version: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    status: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


def experiment_run(**values) -> ExperimentRun:
    allowed = {"NOT_RUN", "FAILED", "COMPLETED"}
    if values.get("status") not in allowed:
        raise ValueError("invalid experiment status")
    values.setdefault("timestamp", datetime.now(UTC).isoformat())
    return ExperimentRun(**values)


VALIDATION_TRANSITIONS = {
    "experimental": {"validated", "deprecated"},
    "validated": {"approved", "experimental", "deprecated"},
    "approved": {"deprecated"},
    "deprecated": set(),
}


def transition_model(
    record: ModelRecord, target: str, validation_record_id: str | None = None
) -> ModelRecord:
    if target not in VALIDATION_TRANSITIONS.get(record.validation_status, set()):
        raise ValueError(
            f"invalid model transition: {record.validation_status} -> {target}"
        )
    if target in {"validated", "approved"} and not validation_record_id:
        raise ValueError("validation record is required")
    values = asdict(record)
    values["validation_status"] = target
    values["deployment_state"] = target
    return ModelRecord(**values)


def champion_challenger(
    champion: list[float], challenger: list[float], labels: list[int]
) -> dict:
    if not (len(champion) == len(challenger) == len(labels)) or not labels:
        raise ValueError("aligned non-empty predictions and labels are required")
    _probabilities(champion, "champion predictions")
    _probabilities(challenger, "challenger predictions")
    if any(isinstance(label, bool) or label not in {0, 1} for label in labels):
        raise ValueError("labels must contain only integer 0 or 1")
    champion_loss = sum(
        (score - label) ** 2 for score, label in zip(champion, labels, strict=True)
    ) / len(labels)
    challenger_loss = sum(
        (score - label) ** 2 for score, label in zip(challenger, labels, strict=True)
    ) / len(labels)
    return {
        "champion_brier": round(champion_loss, 6),
        "challenger_brier": round(challenger_loss, 6),
        "recommendation": "PROMOTE_CHALLENGER"
        if challenger_loss < champion_loss
        else "KEEP_CHAMPION",
        "automatic_promotion": False,
    }


def drift_report(
    reference: list[float],
    current: list[float],
    reference_coverage: float,
    current_coverage: float,
) -> dict:
    _finite_numbers(reference, "reference")
    _finite_numbers(current, "current")
    _probabilities([reference_coverage, current_coverage], "coverage")
    if not reference or not current:
        return {
            "status": "INSUFFICIENT_DATA",
            "mean_shift": None,
            "coverage_drift": round(current_coverage - reference_coverage, 4),
        }
    ref_mean = sum(reference) / len(reference)
    current_mean = sum(current) / len(current)
    scale = max(max(reference) - min(reference), 1.0)
    shift = abs(current_mean - ref_mean) / scale
    return {
        "status": "REVIEW"
        if shift >= 0.2 or abs(current_coverage - reference_coverage) >= 0.15
        else "STABLE",
        "mean_shift": round(shift, 4),
        "coverage_drift": round(current_coverage - reference_coverage, 4),
    }


# Metrics the promotion gate actually compares.
GATE_METRICS: frozenset[str] = frozenset(
    {
        "f1",
        "balanced_accuracy",
        "false_negative_rate",
        "calibration_error",
        "coverage",
        "evidence_verification_error",
    }
)

# Metrics that are recorded and reported but never gate a promotion. They used to
# sit in the same undifferentiated `required` set as the six above, so a caller
# had to supply `latency_ms` and `cost_usd` to get a verdict those numbers had no
# influence on. Naming the two groups makes the contract honest: all nine are
# required (the report is a regression record), only six can block.
REPORTED_METRICS: frozenset[str] = frozenset({"abstention_rate", "latency_ms", "cost_usd"})


def compare_system_versions(champion: dict[str, float], challenger: dict[str, float], policy: dict[str, float] | None = None) -> dict:
    """Evidence-based promotion gate; a recommendation never deploys a system."""
    required = GATE_METRICS | REPORTED_METRICS
    if required - champion.keys() or required - challenger.keys():
        raise ValueError(f"both versions require metrics: {sorted(required)}")
    _finite_numbers((champion[key] for key in required), "champion metrics")
    _finite_numbers((challenger[key] for key in required), "challenger metrics")
    rate_metrics = GATE_METRICS | {"abstention_rate"}
    if any(
        not 0 <= values[key] <= 1
        for values in (champion, challenger)
        for key in rate_metrics
    ):
        raise ValueError("rate metrics must be within [0, 1]")
    if any(
        values[key] < 0
        for values in (champion, challenger)
        for key in ("latency_ms", "cost_usd")
    ):
        raise ValueError("latency and cost must be non-negative")
    allowed_policy = {
        "maximum_fnr_increase",
        "maximum_evidence_error",
        "maximum_calibration_error",
        "minimum_coverage",
    }
    if policy and set(policy) - allowed_policy:
        raise ValueError(f"unknown comparison policy keys: {sorted(set(policy) - allowed_policy)}")
    limits = {
        "maximum_fnr_increase": 0.0,
        "maximum_evidence_error": 0.02,
        "maximum_calibration_error": 0.15,
        "minimum_coverage": 0.5,
    } | (policy or {})
    _finite_numbers(limits.values(), "comparison policy")
    if any(not 0 <= limits[key] <= 1 for key in allowed_policy):
        raise ValueError("comparison policy limits must be within [0, 1]")
    blockers = []
    if challenger["false_negative_rate"] > champion["false_negative_rate"] + limits["maximum_fnr_increase"]:
        blockers.append("FALSE_NEGATIVE_REGRESSION")
    if challenger["evidence_verification_error"] > limits["maximum_evidence_error"]:
        blockers.append("EVIDENCE_ERROR_LIMIT")
    if challenger["calibration_error"] > limits["maximum_calibration_error"]:
        blockers.append("CALIBRATION_LIMIT")
    if challenger["coverage"] < limits["minimum_coverage"]:
        blockers.append("COVERAGE_LIMIT")
    improves = challenger["f1"] > champion["f1"] and challenger["balanced_accuracy"] >= champion["balanced_accuracy"]
    recommendation = "DO_NOT_PROMOTE" if blockers else "PROMOTE" if improves else "PROMOTE_WITH_CONDITIONS"
    return {"recommendation": recommendation, "blockers": blockers, "automatic_promotion": False, "metric_delta": {key: round(challenger[key] - champion[key], 6) for key in sorted(required)}}
