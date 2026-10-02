from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..enterprise.decision import canonical_hash
from .domain import PolicyMaturity


@dataclass(frozen=True)
class AssurancePolicy:
    version: str = "assurance-policy-v0.4.0-development"
    maturity: PolicyMaturity = PolicyMaturity.HEURISTIC_POLICY
    minimum_verified_coverage: float = 0.4
    maximum_disagreement: float = 0.45
    sensitive_score_delta: float = 10.0
    fragile_score_delta: float = 20.0
    maximum_fragility_nodes_exact: int = 12
    require_distribution_reference: bool = True
    require_calibration_for_automation: bool = True
    review_on_unknown_distribution: bool = True
    review_on_fragility_not_estimable: bool = True

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> AssurancePolicy:
        if not value:
            return cls()
        allowed = set(cls.__dataclass_fields__)
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown assurance policy fields: {sorted(unknown)}")
        payload = dict(value)
        if "maturity" in payload:
            payload["maturity"] = PolicyMaturity(payload["maturity"])
        return cls(**payload)

    @property
    def policy_hash(self) -> str:
        return canonical_hash(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
