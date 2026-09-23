"""Validated request contracts for the enterprise HTTP router."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import Decision, RiskCaseStatus, RiskDomain
from .integrity import CalibrationStatus


def _finite_mapping(values: dict, boolean_fields: set[str] | None = None) -> dict:
    boolean_fields = boolean_fields or set()
    for name, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool):
            if name not in boolean_fields:
                raise ValueError(f"boolean is not a financial numeric value: {name}")
        elif not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"non-finite or invalid financial value: {name}")
    return values


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)


class EntityCreate(BaseModel):
    name: str = Field(min_length=1)
    sector: str = "unspecified"
    parent_id: str | None = None


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    domain: RiskDomain
    snapshot_id: str
    rationale: str = ""


class TransitionRequest(BaseModel):
    target: RiskCaseStatus


class OverrideRequest(BaseModel):
    original: Decision
    override: Decision
    reason: str = Field(min_length=1)


class ActionRequest(BaseModel):
    description: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    due_date: str = Field(min_length=1)


class ResolutionEvidenceRequest(BaseModel):
    evidence_id: str = Field(min_length=1)


class ReopenRequest(BaseModel):
    reason: str = Field(min_length=1)


class FusionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: str
    scores: dict[str, float | None]
    weights: dict[str, float] = Field(default_factory=dict)
    coverage: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    decision_policy: dict[str, float] = Field(default_factory=dict)

    @field_validator("scores", "weights", "decision_policy", mode="before")
    @classmethod
    def finite_mappings(cls, values):
        return _finite_mapping(values)

    @model_validator(mode="after")
    def validate_domains(self):
        if any(
            value is not None and not 0 <= value <= 100
            for value in self.scores.values()
        ):
            raise ValueError("fusion scores must be between 0 and 100")
        if any(value < 0 or value > 1 for value in self.weights.values()):
            raise ValueError("fusion weights must be between 0 and 1")
        if self.method == "weighted_average" and not any(
            value > 0 for value in self.weights.values()
        ):
            raise ValueError("weighted_average requires at least one positive weight")
        allowed_policy = {
            "minimum_coverage",
            "maximum_disagreement",
            "minimum_reliability",
            "flag_score",
            "review_score",
            "critical_dimension_score",
            "severe_dimension_score",
            "elevated_dimension_score",
            "interaction_uplift_cap",
            "interaction_uplift_per_dimension",
            "interaction_dimension_score",
            "interaction_premium",
        }
        if set(self.decision_policy) - allowed_policy:
            raise ValueError("unknown decision policy field")
        unit_interval = {
            "minimum_coverage",
            "maximum_disagreement",
            "minimum_reliability",
        }
        for key, value in self.decision_policy.items():
            upper = 1 if key in unit_interval else 100
            if not 0 <= value <= upper:
                raise ValueError(f"decision policy value out of range: {key}")
        if self.decision_policy.get("review_score", 40) > self.decision_policy.get(
            "flag_score", 60
        ):
            raise ValueError("review_score cannot exceed flag_score")
        return self


class ScenarioRequest(BaseModel):
    year: int
    baseline: dict[str, float | None]
    shocks: dict[str, float]

    @field_validator("baseline", "shocks", mode="before")
    @classmethod
    def finite_mappings(cls, values):
        return _finite_mapping(values)


class PolicyCreate(BaseModel):
    name: str
    version: int = Field(ge=1)
    thresholds: dict[str, dict[str, float | str]]

    @field_validator("thresholds")
    @classmethod
    def valid_thresholds(cls, thresholds):
        if not thresholds:
            raise ValueError("at least one KRI threshold is required")
        for name, limits in thresholds.items():
            if not name.strip() or set(limits) - {
                "warning",
                "critical",
                "risk_direction",
            }:
                raise ValueError("invalid KRI threshold fields")
            direction = limits.get("risk_direction")
            if direction not in {"high", "low"}:
                raise ValueError("risk_direction must be 'high' or 'low'")
            warning, critical = limits.get("warning"), limits.get("critical")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in (warning, critical)
            ):
                raise ValueError("warning and critical thresholds must be finite numbers")
            if (direction == "high" and warning > critical) or (
                direction == "low" and warning < critical
            ):
                raise ValueError("warning must be less severe than critical")
        return thresholds


class SnapshotCreate(BaseModel):
    entity_id: str
    frozen_input: dict
    frozen_output: dict
    document_versions: dict[str, str]
    component_versions: dict[str, str]


class ReplayRequest(BaseModel):
    replayed_output: dict


class RiskSnapshotRequest(BaseModel):
    period: str = Field(pattern=r"^(?:FY)?(?:19|20)\d{2}(?:-Q[1-4])?$")
    filing_id: str = Field(min_length=1)
    risk_score: float | None = Field(default=None, ge=0, le=100)
    dimension_scores: dict[str, float | None]
    metrics: dict[str, float | None]
    evidence_paths: dict[str, list[str]]
    decision: Decision
    coverage: float = Field(ge=0, le=1)
    reliability: float | None = Field(default=None, ge=0, le=1)
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED

    @field_validator("risk_score", "reliability", mode="before")
    @classmethod
    def finite_scalars(cls, value):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("financial values must be finite numbers")
        return value

    @field_validator("dimension_scores", "metrics", mode="before")
    @classmethod
    def finite_financial_mappings(cls, values):
        return _finite_mapping(values)

    @field_validator("dimension_scores")
    @classmethod
    def bounded_dimension_scores(cls, values):
        if any(
            value is not None and not 0 <= value <= 100 for value in values.values()
        ):
            raise ValueError("dimension scores must be between 0 and 100")
        return values

    @field_validator("period")
    @classmethod
    def canonical_period(cls, period):
        return period.removeprefix("FY")


class ApplicabilityRequest(BaseModel):
    industry: str
    facts: dict[str, float | str | bool | None]

    @field_validator("facts", mode="before")
    @classmethod
    def finite_facts(cls, values):
        return _finite_mapping(
            values,
            {
                "going_concern_doubt",
                "material_weakness",
                "refinancing_dependency",
            },
        )


class SelectiveDecisionRequest(BaseModel):
    proposed_decision: Decision
    coverage: float = Field(ge=0, le=1)
    reliability: float | None = Field(default=None, ge=0, le=1)
    disagreement: float = Field(ge=0, le=1)
    policy: dict[str, float] = Field(default_factory=dict)
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED
