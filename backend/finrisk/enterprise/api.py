from __future__ import annotations

import hmac
import math
import os
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .applicability import applicability_report
from .calibration import selective_decision
from .decision import create_snapshot, replay_diff
from .domain import (
    Decision,
    Principal,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
    Role,
    new_id,
)
from .fusion import FUSION_METHODS
from .integrity import CalibrationStatus
from .policy import evaluate_kri
from .portfolio import portfolio_overview
from .scenario import Scenario, compare_scenario
from .security import (
    CredentialStore,
    DurableCredentialStore,
    RateLimiter,
    SlidingWindowRateLimiter,
    issue_api_key,
)
from .service import EnterpriseRiskService, verified_evidence_ids
from .temporal import RiskSnapshot, compare_risk_snapshots


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


def _as_float(value, default: float = 0.0) -> float:
    """Coerce a caller-supplied score to a finite float, falling back to `default`.

    `float()` on a missing key raises KeyError/TypeError and on a non-numeric
    string raises ValueError; both escaped the risk-case endpoint as 500s.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


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
        if any(value is not None and not 0 <= value <= 100 for value in self.scores.values()):
            raise ValueError("fusion scores must be between 0 and 100")
        if any(value < 0 or value > 1 for value in self.weights.values()):
            raise ValueError("fusion weights must be between 0 and 1")
        if self.method == "weighted_average" and not any(value > 0 for value in self.weights.values()):
            raise ValueError("weighted_average requires at least one positive weight")
        # `minimum_reliability` is the reliability floor `calibration.selective_decision`
        # applies. It was absent here, so a caller who sent it got a 422 and the
        # threshold stayed at the hardcoded 0.6 with no way to express it.
        allowed_policy = {
            "minimum_coverage", "maximum_disagreement", "minimum_reliability",
            "flag_score",
            "review_score", "critical_dimension_score", "severe_dimension_score",
            "elevated_dimension_score", "interaction_uplift_cap",
            "interaction_uplift_per_dimension", "interaction_dimension_score",
            "interaction_premium",
        }
        if set(self.decision_policy) - allowed_policy:
            raise ValueError("unknown decision policy field")
        for key, value in self.decision_policy.items():
            upper = 1 if key in {"minimum_coverage", "maximum_disagreement", "minimum_reliability"} else 100
            if not 0 <= value <= upper:
                raise ValueError(f"decision policy value out of range: {key}")
        if self.decision_policy.get("review_score", 40) > self.decision_policy.get("flag_score", 60):
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
            if not name.strip() or set(limits) - {"warning", "critical", "risk_direction"}:
                raise ValueError("invalid KRI threshold fields")
            direction = limits.get("risk_direction")
            if direction not in {"high", "low"}:
                raise ValueError("risk_direction must be 'high' or 'low'")
            warning, critical = limits.get("warning"), limits.get("critical")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (warning, critical)):
                raise ValueError("warning and critical thresholds must be finite numbers")
            if (direction == "high" and warning > critical) or (direction == "low" and warning < critical):
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
        if any(value is not None and not 0 <= value <= 100 for value in values.values()):
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
        return _finite_mapping(values, {"going_concern_doubt", "material_weakness", "refinancing_dependency"})


class SelectiveDecisionRequest(BaseModel):
    proposed_decision: Decision
    coverage: float = Field(ge=0, le=1)
    reliability: float | None = Field(default=None, ge=0, le=1)
    disagreement: float = Field(ge=0, le=1)
    policy: dict[str, float] = Field(default_factory=dict)
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED


def enterprise_router(
    service: EnterpriseRiskService | None = None,
    credentials: DurableCredentialStore | None = None,
    limiter: RateLimiter | None = None,
    bootstrap_enabled: bool = True,
    bootstrap_token: str | None = None,
    require_bootstrap_token: bool = False,
    bootstrap_rate_limit: int | None = None,
) -> APIRouter:
    service = service or EnterpriseRiskService()
    router = APIRouter(prefix="/api/v1/enterprise", tags=["enterprise"])
    credentials = credentials or CredentialStore()
    limiter = limiter or SlidingWindowRateLimiter()
    # The bootstrap route is the highest-privilege endpoint (it mints ADMIN keys)
    # and is the only one that cannot require an API key, so it gets its own
    # limiter keyed by client address. The shared `limiter` lives inside
    # `principal()` and therefore never covered this route.
    bootstrap_limiter = SlidingWindowRateLimiter(
        limit=bootstrap_rate_limit
        if bootstrap_rate_limit is not None
        else int(os.getenv("FINRISK_BOOTSTRAP_RATE_LIMIT", "60")),
        window_seconds=60,
    )

    def principal(
        api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> Principal:
        if not api_key:
            raise HTTPException(401, "missing API key")
        try:
            actor = credentials.authenticate(api_key)
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from exc
        if not limiter.allow(f"{actor.organization_id}:{actor.user_id}"):
            raise HTTPException(429, "rate limit exceeded")
        return actor

    principal_dependency = Depends(principal)

    @router.post("/organizations")
    def create_organization(
        req: OrganizationCreate,
        request: Request,
        x_bootstrap_token: Annotated[str | None, Header(alias="X-Bootstrap-Token")] = None,
    ):
        if not bootstrap_enabled:
            raise HTTPException(403, "organization bootstrap is disabled")
        client = request.client.host if request.client else "unknown"
        if not bootstrap_limiter.allow(f"bootstrap:{client}"):
            raise HTTPException(429, "bootstrap rate limit exceeded")
        if bootstrap_token is not None or require_bootstrap_token:
            expected = bootstrap_token or ""
            supplied = x_bootstrap_token or ""
            # Constant-time comparison; an unset expected token can never match.
            if not expected or not hmac.compare_digest(supplied, expected):
                raise HTTPException(403, "invalid bootstrap token")
        organization = service.create_organization(req.name, req.actor_id)
        raw, credential = issue_api_key(organization.id, req.actor_id, Role.ADMIN)
        credentials.register(credential)
        return {**asdict(organization), "api_key": raw, "api_key_id": credential.id}

    @router.post("/entities")
    def create_entity(req: EntityCreate, actor: Principal = principal_dependency):
        try:
            return asdict(service.create_entity(actor, req.name, req.sector, req.parent_id))
        except (KeyError, PermissionError, ValueError) as exc:
            # An unknown `parent_id` raises KeyError inside the service; without
            # this mapping it escaped to the catch-all middleware as a 500.
            raise HTTPException(422, "entity creation rejected") from exc

    @router.post("/risk-cases")
    def create_case(req: CaseCreate, actor: Principal = principal_dependency):
        try:
            snapshot = service.repository.get_snapshot(actor.organization_id, req.snapshot_id)
        except KeyError as exc:
            raise HTTPException(422, "server-side analysis snapshot not found") from exc
        if snapshot.organization_id != actor.organization_id or snapshot.entity_id != req.entity_id:
            raise HTTPException(422, "analysis snapshot scope does not match risk case")
        output = snapshot.frozen_output
        # `agent` is absent for snapshots produced before the agent path existed and
        # can legitimately be `null`; both used to fail on `.get` below.
        agent_output = output.get("agent") or {}
        trace = agent_output.get("decision_trace") or {}
        aliases = {
            "accounting": "accounting_anomaly",
            "governance": "governance_audit",
            "going_concern": "business_going_concern",
            "solvency": "solvency_leverage",
        }
        verified_paths = [
            path for path in trace.get("paths", [])
            if path.get("evidence_path_status") == "VERIFIED"
            and path.get("source_evidence")
            and aliases.get(path.get("risk_domain"), path.get("risk_domain"))
            == req.domain.value
        ]
        case = RiskCase(
            new_id("case"),
            actor.organization_id,
            req.entity_id,
            req.domain,
            str(agent_output.get("risk_severity", output.get("risk_level", "unknown"))),
            str(agent_output.get("risk_trajectory", "insufficient_history")),
            _as_float((agent_output.get("epistemics") or {}).get("evidence_quality"), 0.0),
            _as_float(agent_output.get("evidence_coverage"), 0.0),
            rationale=req.rationale,
            evidence_ids=sorted(verified_evidence_ids(snapshot, req.domain.value)),
            reason_codes=sorted({str(path.get("reason_code")) for path in verified_paths}),
            decision_trace={**trace, "verified_path_count": len(verified_paths)},
            snapshot_id=snapshot.id,
            fusion_version=snapshot.component_versions.get("fusion"),
        )
        try:
            return service.create_case(actor, case).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            # Same mapping as the sibling enterprise endpoints: an unknown entity or
            # a role without write access is a rejected request, not a server fault.
            raise HTTPException(422, "risk-case creation rejected") from exc

    @router.get("/risk-cases")
    def list_cases(actor: Principal = principal_dependency):
        return [
            case.to_dict()
            for case in service.repository.list_cases(actor.organization_id)
        ]

    @router.post("/risk-cases/{case_id}/transition")
    def transition(
        case_id: str,
        req: TransitionRequest,
        actor: Principal = principal_dependency,
    ):
        try:
            return service.transition(actor, case_id, req.target).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "risk-case transition rejected") from exc

    @router.post("/risk-cases/{case_id}/override")
    def override(
        case_id: str,
        req: OverrideRequest,
        actor: Principal = principal_dependency,
    ):
        try:
            return service.override(
                actor, case_id, req.original.value, req.override.value, req.reason
            ).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "risk-case override rejected") from exc

    @router.post("/risk-cases/{case_id}/actions")
    def add_action(
        case_id: str, req: ActionRequest, actor: Principal = principal_dependency
    ):
        try:
            return service.add_action(
                actor, case_id, req.description, req.owner_id, req.due_date
            ).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "risk-case action rejected") from exc

    @router.post("/risk-cases/{case_id}/resolution-evidence")
    def add_resolution_evidence(
        case_id: str,
        req: ResolutionEvidenceRequest,
        actor: Principal = principal_dependency,
    ):
        try:
            return service.add_resolution_evidence(
                actor, case_id, req.evidence_id
            ).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "resolution evidence rejected") from exc

    @router.post("/risk-cases/{case_id}/reopen")
    def reopen(
        case_id: str, req: ReopenRequest, actor: Principal = principal_dependency
    ):
        try:
            return service.reopen(actor, case_id, req.reason).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "risk-case reopen rejected") from exc

    @router.get("/overview")
    def overview(actor: Principal = principal_dependency):
        return portfolio_overview(service.repository.list_cases(actor.organization_id))

    @router.post("/policies")
    def create_policy(req: PolicyCreate, actor: Principal = principal_dependency):
        try:
            return asdict(
                service.create_policy(actor, req.name, req.thresholds, req.version)
            )
        except (KeyError, PermissionError, ValueError) as exc:
            # `authorize` rejects ANALYST/REVIEWER/VIEWER with PermissionError, which
            # otherwise reached the catch-all middleware as a 500.
            raise HTTPException(422, "policy creation rejected") from exc

    @router.post("/policies/{policy_id}/evaluate")
    def evaluate_policy(
        policy_id: str,
        metrics: dict[str, float | None],
        actor: Principal = principal_dependency,
    ):
        try:
            policy = service.repository.get_policy(actor.organization_id, policy_id)
        except KeyError:
            raise HTTPException(404, "policy not found")
        try:
            return evaluate_kri(policy, metrics)
        except ValueError as exc:
            # A stored policy written before `risk_direction` was required cannot be
            # evaluated without guessing its direction; that is a 422, not a 500.
            raise HTTPException(422, str(exc)) from exc

    @router.post("/snapshots")
    def save_snapshot(req: SnapshotCreate, actor: Principal = principal_dependency):
        if not bootstrap_enabled:
            raise HTTPException(403, "snapshot import is disabled; use the server analysis workflow")
        snapshot = create_snapshot(
            actor.organization_id,
            req.entity_id,
            req.frozen_input,
            req.frozen_output,
            req.document_versions,
            req.component_versions,
        )
        try:
            return asdict(service.save_snapshot(actor, snapshot))
        except (KeyError, PermissionError, ValueError) as exc:
            # An unknown entity or a role without write access is a rejected
            # request; unmapped it became a 500.
            raise HTTPException(422, "snapshot import rejected") from exc

    @router.post("/snapshots/{snapshot_id}/replay-diff")
    def compare_replay(
        snapshot_id: str, req: ReplayRequest, actor: Principal = principal_dependency
    ):
        try:
            snapshot = service.repository.get_snapshot(
                actor.organization_id, snapshot_id
            )
        except KeyError as exc:
            raise HTTPException(404, "snapshot not found") from exc
        return replay_diff(snapshot, req.replayed_output)

    @router.get("/audit-events")
    def events(actor: Principal = principal_dependency):
        return [
            asdict(event)
            for event in service.repository.list_events(actor.organization_id)
        ]

    @router.post("/entities/{entity_id}/risk-snapshots")
    def save_risk_snapshot(
        entity_id: str,
        req: RiskSnapshotRequest,
        actor: Principal = principal_dependency,
    ):
        try:
            payload = req.model_dump()
            if req.calibration_status is CalibrationStatus.UNCALIBRATED:
                payload["reliability"] = None
            item = RiskSnapshot(entity_id=entity_id, **payload)
            return asdict(service.save_risk_snapshot(actor, item))
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "risk snapshot rejected") from exc

    @router.get("/entities/{entity_id}/risk-timeline")
    def risk_timeline(entity_id: str, actor: Principal = principal_dependency):
        try:
            timeline = service.risk_timeline(actor, entity_id)
        except (KeyError, PermissionError, TypeError, ValueError) as exc:
            raise HTTPException(404, "entity not found") from exc
        output = []
        for index, item in enumerate(timeline):
            row = asdict(item)
            try:
                row["delta"] = (
                    compare_risk_snapshots(timeline[index - 1], item).to_dict()
                    if index
                    else None
                )
            except (TypeError, ValueError) as exc:
                # Two snapshots that do not share a comparable metric set are a
                # request the caller can fix, not a server fault.
                raise HTTPException(422, "risk timeline is not comparable") from exc
            output.append(row)
        return output

    @router.post("/applicability")
    def applicability(
        req: ApplicabilityRequest, actor: Principal = principal_dependency
    ):
        return applicability_report(req.industry, req.facts)

    @router.post("/selective-decision")
    def apply_selective_policy(
        req: SelectiveDecisionRequest, actor: Principal = principal_dependency
    ):
        return selective_decision(
            req.proposed_decision,
            req.coverage,
            req.reliability,
            req.disagreement,
            req.policy,
            req.calibration_status,
        )

    @router.post("/fusion")
    def fuse(req: FusionRequest, actor: Principal = principal_dependency):
        method = FUSION_METHODS.get(req.method)
        if method is None:
            raise HTTPException(422, "unknown fusion method")
        kwargs = (
            (req.scores, req.weights, req.coverage, req.confidence, req.decision_policy)
            if req.method == "weighted_average"
            else (req.scores, req.coverage, req.confidence, req.decision_policy)
        )
        return asdict(method(*kwargs))

    @router.post("/scenarios")
    def scenario(req: ScenarioRequest, actor: Principal = principal_dependency):
        if any(value is None for value in req.baseline.values()):
            raise HTTPException(422, "scenario baseline values must be present")
        allowed = set(Scenario.__dataclass_fields__) - {"name"}
        unknown = set(req.shocks) - allowed
        if unknown:
            raise HTTPException(422, f"unknown scenario shock(s): {sorted(unknown)}")
        try:
            return compare_scenario(req.baseline, req.year, Scenario("api", **req.shocks))
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            # A stress scenario that cannot be computed (missing `total_debt` for a
            # debt-cost shock, or a zero denominator) is a rejected request.
            raise HTTPException(422, f"scenario could not be computed: {exc}") from exc

    return router
