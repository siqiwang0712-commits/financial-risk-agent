from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

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
from .policy import evaluate_kri
from .portfolio import portfolio_overview
from .scenario import Scenario, compare_scenario
from .security import CredentialStore, SlidingWindowRateLimiter, issue_api_key
from .service import EnterpriseRiskService
from .temporal import RiskSnapshot, compare_risk_snapshots


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)


class EntityCreate(BaseModel):
    name: str = Field(min_length=1)
    sector: str = "unspecified"
    parent_id: str | None = None


class CaseCreate(BaseModel):
    entity_id: str
    domain: RiskDomain
    severity: str
    trajectory: str = "insufficient_history"
    confidence: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    decision_trace: dict = Field(default_factory=dict)
    snapshot_id: str | None = None
    fusion_version: str | None = None


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


class ScenarioRequest(BaseModel):
    year: int
    baseline: dict[str, float | None]
    shocks: dict[str, float]


class PolicyCreate(BaseModel):
    name: str
    version: int = Field(ge=1)
    thresholds: dict[str, dict[str, float | str]]


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


class ApplicabilityRequest(BaseModel):
    industry: str
    facts: dict[str, float | str | bool | None]


class SelectiveDecisionRequest(BaseModel):
    proposed_decision: Decision
    coverage: float = Field(ge=0, le=1)
    reliability: float | None = Field(default=None, ge=0, le=1)
    disagreement: float = Field(ge=0, le=1)
    policy: dict[str, float] = Field(default_factory=dict)


def enterprise_router(service: EnterpriseRiskService | None = None) -> APIRouter:
    service = service or EnterpriseRiskService()
    router = APIRouter(prefix="/api/v1/enterprise", tags=["enterprise"])
    credentials = CredentialStore()
    limiter = SlidingWindowRateLimiter()

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
    def create_organization(req: OrganizationCreate):
        organization = service.create_organization(req.name, req.actor_id)
        raw, credential = issue_api_key(organization.id, req.actor_id, Role.ADMIN)
        credentials.register(credential)
        return {**asdict(organization), "api_key": raw, "api_key_id": credential.id}

    @router.post("/entities")
    def create_entity(req: EntityCreate, actor: Principal = principal_dependency):
        return asdict(service.create_entity(actor, req.name, req.sector, req.parent_id))

    @router.post("/risk-cases")
    def create_case(req: CaseCreate, actor: Principal = principal_dependency):
        case = RiskCase(
            new_id("case"),
            actor.organization_id,
            req.entity_id,
            req.domain,
            req.severity,
            req.trajectory,
            req.confidence,
            req.evidence_coverage,
            rationale=req.rationale,
            evidence_ids=req.evidence_ids,
            reason_codes=req.reason_codes,
            decision_trace=req.decision_trace,
            snapshot_id=req.snapshot_id,
            fusion_version=req.fusion_version,
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
            raise HTTPException(422, str(exc)) from exc

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
            raise HTTPException(422, str(exc)) from exc

    @router.post("/risk-cases/{case_id}/actions")
    def add_action(
        case_id: str, req: ActionRequest, actor: Principal = principal_dependency
    ):
        try:
            return service.add_action(
                actor, case_id, req.description, req.owner_id, req.due_date
            ).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

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
            raise HTTPException(422, str(exc)) from exc

    @router.post("/risk-cases/{case_id}/reopen")
    def reopen(
        case_id: str, req: ReopenRequest, actor: Principal = principal_dependency
    ):
        try:
            return service.reopen(actor, case_id, req.reason).to_dict()
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

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
        metrics: dict[str, float | None],
        actor: Principal = principal_dependency,
    ):
        policy = service.repository.policies.get(policy_id)
        if policy is None or policy.organization_id != actor.organization_id:
            raise HTTPException(404, "policy not found")
        return evaluate_kri(policy, metrics)

    @router.post("/snapshots")
    def save_snapshot(req: SnapshotCreate, actor: Principal = principal_dependency):
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
            item = RiskSnapshot(entity_id=entity_id, **req.model_dump())
            return asdict(service.save_risk_snapshot(actor, item))
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

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
        allowed = set(Scenario.__dataclass_fields__) - {"name"}
        unknown = set(req.shocks) - allowed
        if unknown:
            raise HTTPException(422, f"unknown scenario shock(s): {sorted(unknown)}")
        return compare_scenario(req.baseline, req.year, Scenario("api", **req.shocks))

    return router
