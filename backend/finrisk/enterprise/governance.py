from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from .domain import ModelRecord


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
