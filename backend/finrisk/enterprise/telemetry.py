from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ComponentTelemetry:
    component: str
    status: str
    risk_before: float | None
    risk_after: float | None
    delta_risk: float | None
    coverage_before: float
    coverage_after: float
    delta_coverage: float
    disagreement_before: float
    disagreement_after: float
    delta_disagreement: float
    decision_changed: bool
    new_evidence: int
    latency_ms: int
    estimated_cost_usd: float

    def to_dict(self) -> dict:
        return asdict(self)


def component_delta(
    component: str,
    *,
    risk_before: float | None,
    risk_after: float | None,
    coverage_before: float,
    coverage_after: float,
    disagreement_before: float = 0.0,
    disagreement_after: float = 0.0,
    decision_changed: bool = False,
    new_evidence: int = 0,
    latency_ms: int = 0,
    estimated_cost_usd: float = 0.0,
    status: str = "executed",
) -> ComponentTelemetry:
    return ComponentTelemetry(
        component,
        status,
        risk_before,
        risk_after,
        None
        if risk_before is None or risk_after is None
        else round(risk_after - risk_before, 3),
        round(coverage_before, 3),
        round(coverage_after, 3),
        round(coverage_after - coverage_before, 3),
        round(disagreement_before, 3),
        round(disagreement_after, 3),
        round(disagreement_after - disagreement_before, 3),
        decision_changed,
        new_evidence,
        max(0, latency_ms),
        round(max(0.0, estimated_cost_usd), 8),
    )
