from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import pairwise
from typing import Any


@dataclass(frozen=True)
class RiskSnapshot:
    entity_id: str
    period: str
    filing_id: str
    risk_score: float | None
    dimension_scores: dict[str, float | None]
    metrics: dict[str, float | None]
    evidence_paths: dict[str, list[str]]
    decision: str
    coverage: float
    reliability: float | None = None


@dataclass(frozen=True)
class EvidenceDelta:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    retained: tuple[str, ...]


@dataclass(frozen=True)
class RiskDelta:
    from_period: str
    to_period: str
    score_change: float | None
    dimension_changes: dict[str, float]
    metric_changes: dict[str, float]
    evidence_delta: EvidenceDelta
    attribution: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityRiskState:
    entity_id: str
    snapshots: list[RiskSnapshot] = field(default_factory=list)
    deltas: list[RiskDelta] = field(default_factory=list)

    def update(self, snapshot: RiskSnapshot) -> RiskDelta | None:
        if snapshot.entity_id != self.entity_id:
            raise ValueError("snapshot belongs to a different entity")
        if any(item.period == snapshot.period for item in self.snapshots):
            raise ValueError(f"risk snapshot already exists for {snapshot.period}")
        previous = self.snapshots[-1] if self.snapshots else None
        if previous is not None and snapshot.period <= previous.period:
            raise ValueError("risk snapshots must be appended in reporting-period order")
        self.snapshots.append(snapshot)
        if previous is None:
            return None
        delta = compare_risk_snapshots(previous, snapshot)
        self.deltas.append(delta)
        return delta

    @property
    def current(self) -> RiskSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None


def classify_trajectory(values: list[float | None]) -> str:
    observed = [value for value in values if value is not None]
    if len(observed) < 2:
        return "insufficient_history"
    changes = [b - a for a, b in pairwise(observed)]
    if all(value >= 60 for value in observed[-2:]):
        return "persistent_weakness"
    if changes[-1] >= 20:
        return "sharply_deteriorating"
    if changes[-1] >= 5:
        return "deteriorating"
    if changes[-1] <= -20:
        return "recovery"
    if changes[-1] <= -5:
        return "improving"
    return "stable"


def compare_risk_snapshots(previous: RiskSnapshot, current: RiskSnapshot) -> RiskDelta:
    if previous.entity_id != current.entity_id:
        raise ValueError("cannot compare different entities")
    dimensions = _numeric_changes(previous.dimension_scores, current.dimension_scores)
    metrics = _numeric_changes(previous.metrics, current.metrics)
    previous_evidence = {item for values in previous.evidence_paths.values() for item in values}
    current_evidence = {item for values in current.evidence_paths.values() for item in values}
    evidence_delta = EvidenceDelta(
        tuple(sorted(current_evidence - previous_evidence)),
        tuple(sorted(previous_evidence - current_evidence)),
        tuple(sorted(previous_evidence & current_evidence)),
    )
    attribution = tuple(
        {
            "driver": name,
            "risk_change": round(change, 3),
            "direction": "deterioration" if change > 0 else "improvement",
            "evidence_path_ids": tuple(current.evidence_paths.get(name, ())),
        }
        for name, change in sorted(dimensions.items(), key=lambda item: abs(item[1]), reverse=True)
        if change
    )
    score_change = (
        None
        if previous.risk_score is None or current.risk_score is None
        else round(current.risk_score - previous.risk_score, 3)
    )
    return RiskDelta(previous.period, current.period, score_change, dimensions, metrics, evidence_delta, attribution)


def _numeric_changes(previous: dict[str, float | None], current: dict[str, float | None]) -> dict[str, float]:
    return {
        key: round(current[key] - previous[key], 6)
        for key in sorted(set(previous) & set(current))
        if previous[key] is not None and current[key] is not None
    }
