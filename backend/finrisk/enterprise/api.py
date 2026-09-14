from __future__ import annotations

import hmac
import inspect
import math
import os
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .applicability import applicability_report
from .calibration import selective_decision
from .decision import create_snapshot, replay_diff, verified_paths_for_domain
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
from .policy import evaluate_kri, validate_thresholds
from .portfolio import portfolio_overview
from .scenario import Scenario, compare_scenario
from .security import (
    CredentialStore,
    DurableCredentialStore,
    RateLimiter,
    SlidingWindowRateLimiter,
    issue_api_key,
)
from .service import EnterpriseRiskService
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
    original: str
    override: str
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
    def thresholds_are_evaluable(cls, values):
        # Reject at the boundary what `evaluate_kri` cannot evaluate, so a
        # malformed policy is a 422 instead of being stored and later raising
        # `TypeError` (a 500) when the policy is applied.
        validate_thresholds(values)
        return values


class SnapshotCreate(BaseModel):
    entity_id: str
    frozen_input: dict
    frozen_output: dict
    document_versions: dict[str, str]
    component_versions: dict[str, str]


class ReplayRequest(BaseModel):
    replayed_output: dict


class RiskSnapshotRequest(BaseModel):
    period: str = Field(min_length=1)
    filing_id: str = Field(min_length=1)
    risk_score: float | None
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
        if not limiter.allow(actor.organization_id):
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
        return asdict(service.create_entity(actor, req.name, req.sector, req.parent_id))

    @router.post("/risk-cases")
    def create_case(req: CaseCreate, actor: Principal = principal_dependency):
        try:
            snapshot = service.repository.get_snapshot(actor.organization_id, req.snapshot_id)
        except KeyError as exc:
            raise HTTPException(422, "server-side analysis snapshot not found") from exc
        if snapshot.organization_id != actor.organization_id or snapshot.entity_id != req.entity_id:
            raise HTTPException(422, "analysis snapshot scope does not match risk case")
        output = snapshot.frozen_output
        agent_output = output.get("agent", {})
        trace = agent_output.get("decision_trace", {})
        # Same gate `service.transition` applies before ACCEPTED/RESOLVED, from the
        # same function. The two used to be separate copies of the same alias map.
        verified_paths = verified_paths_for_domain(trace, req.domain.value)
        case = RiskCase(
            new_id("case"),
            actor.organization_id,
            req.entity_id,
            req.domain,
            str(agent_output.get("risk_severity", output.get("risk_level", "unknown"))),
            str(agent_output.get("risk_trajectory", "insufficient_history")),
            float(agent_output.get("epistemics", {}).get("evidence_quality", 0.0)),
            float(agent_output.get("evidence_coverage", 0.0)),
            rationale=req.rationale,
            evidence_ids=sorted({
                str(evidence.get("source"))
                for path in verified_paths
                for evidence in path.get("source_evidence", [])
                if evidence.get("source")
            }),
            reason_codes=sorted({str(path.get("reason_code")) for path in verified_paths}),
            decision_trace={**trace, "verified_path_count": len(verified_paths)},
            snapshot_id=snapshot.id,
            fusion_version=snapshot.component_versions.get("fusion"),
        )
        return service.create_case(actor, case).to_dict()

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
                actor, case_id, req.original, req.override, req.reason
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
        return asdict(
            service.create_policy(actor, req.name, req.thresholds, req.version)
        )

    @router.post("/policies/{policy_id}/evaluate")
    def evaluate_policy(
        policy_id: str,
        # `float | bool | None`, not `float | None`: Pydantic coerces `true` to
        # `1.0`, so a boolean KRI value passed the numeric guard unseen. Keeping
        # the bool in the annotation lets `_finite_mapping` reject it, exactly as
        # `AssessmentRequest.current` does on the core API.
        metrics: dict[str, float | bool | None],
        actor: Principal = principal_dependency,
    ):
        # `metrics` is a bare body parameter, so it never passed through the
        # `_finite_mapping` guard every other numeric endpoint uses: a string,
        # `NaN` or `Infinity` reached `evaluate_kri` and its comparisons.
        try:
            _finite_mapping(metrics)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        try:
            policy = service.repository.get_policy(actor.organization_id, policy_id)
        except KeyError:
            raise HTTPException(404, "policy not found")
        # `evaluate_kri` validates `risk_direction` and the limit bounds, so it can
        # raise for a policy stored before those checks existed. Converting that to
        # 422 keeps a malformed stored policy from surfacing as a 500.
        try:
            return evaluate_kri(policy, metrics)
        except ValueError as exc:
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
        return asdict(service.save_snapshot(actor, snapshot))

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
        except (KeyError, PermissionError) as exc:
            raise HTTPException(404, "entity not found") from exc
        output = []
        for index, item in enumerate(timeline):
            row = asdict(item)
            row["delta"] = (
                compare_risk_snapshots(timeline[index - 1], item).to_dict()
                if index
                else None
            )
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
        # Dispatch on the function's own signature rather than special-casing one
        # method name by string. The old `req.method == "weighted_average"` test
        # hard-coded the fact that exactly one method takes `weights`, so adding a
        # method with a different arity produced a bare `TypeError` - a 500 for a
        # request that should be a 422.
        available = {
            "scores": req.scores,
            "weights": req.weights,
            "coverage": req.coverage,
            "confidence": req.confidence,
            "policy": req.decision_policy,
        }
        parameters = list(inspect.signature(method).parameters)
        missing = [name for name in parameters if name not in available]
        if missing:
            raise HTTPException(422, f"fusion method {req.method!r} requires {missing}")
        try:
            return asdict(method(**{name: available[name] for name in parameters}))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/scenarios")
    def scenario(req: ScenarioRequest, actor: Principal = principal_dependency):
        allowed = set(Scenario.__dataclass_fields__) - {"name"}
        unknown = set(req.shocks) - allowed
        if unknown:
            raise HTTPException(422, f"unknown scenario shock(s): {sorted(unknown)}")
        return compare_scenario(req.baseline, req.year, Scenario("api", **req.shocks))

    return router
