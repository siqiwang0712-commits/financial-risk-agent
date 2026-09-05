from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Role(StrEnum):
    ADMIN = "admin"
    RISK_MANAGER = "risk_manager"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class RiskDomain(StrEnum):
    LIQUIDITY = "liquidity"
    SOLVENCY = "solvency_leverage"
    PROFITABILITY = "profitability"
    CASH_FLOW = "cash_flow"
    EARNINGS_QUALITY = "earnings_quality"
    ACCOUNTING = "accounting_anomaly"
    COVENANT = "covenant_refinancing"
    COUNTERPARTY = "counterparty_concentration"
    GOVERNANCE = "governance_audit"
    GOING_CONCERN = "business_going_concern"
    DISCLOSURE_TENSION = "disclosure_tension"


class Decision(StrEnum):
    PASS = "PASS"
    FLAG = "FLAG"
    REVIEW = "REVIEW"
    ABSTAIN = "ABSTAIN"


class RiskCaseStatus(StrEnum):
    DETECTED = "detected"
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    role: Role


@dataclass(frozen=True)
class Organization:
    id: str
    name: str
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class Entity:
    id: str
    organization_id: str
    name: str
    parent_id: str | None = None
    sector: str = "unspecified"


@dataclass(frozen=True)
class PolicyVersion:
    id: str
    organization_id: str
    version: int
    name: str
    thresholds: dict[str, dict[str, Any]]
    created_by: str
    created_at: str = field(default_factory=now_iso)
    status: str = "draft"


@dataclass(frozen=True)
class FusionResult:
    method: str
    severity: str
    score: float | None
    decision: Decision
    evidence_coverage: float
    decision_confidence: float
    disagreement: float
    drivers: list[str]
    rationale: str


@dataclass
class RiskCase:
    id: str
    organization_id: str
    entity_id: str
    domain: RiskDomain
    severity: str
    trajectory: str
    confidence: float
    evidence_coverage: float
    status: RiskCaseStatus = RiskCaseStatus.DETECTED
    owner_id: str | None = None
    reviewer_id: str | None = None
    due_date: str | None = None
    rationale: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    decision_trace: dict[str, Any] = field(default_factory=dict)
    snapshot_id: str | None = None
    fusion_version: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditEvent:
    id: str
    organization_id: str
    actor_id: str
    action: str
    object_type: str
    object_id: str
    payload: dict[str, Any]
    occurred_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ModelRecord:
    id: str
    organization_id: str
    component: str
    version: str
    owner: str
    intended_use: str
    limitations: str
    validation_status: str = "experimental"
    dataset_version: str | None = None
    prompt_hash: str | None = None
    rule_version: str | None = None
    fusion_version: str | None = None
    policy_version: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    last_validation: str | None = None
    deployment_state: str = "experimental"


@dataclass(frozen=True)
class AnalysisSnapshot:
    id: str
    organization_id: str
    entity_id: str
    input_hash: str
    output_hash: str
    document_versions: dict[str, str]
    component_versions: dict[str, str]
    frozen_input: dict[str, Any]
    frozen_output: dict[str, Any]
    created_at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ValidationRecord:
    id: str
    organization_id: str
    component: str
    version: str
    dataset_version: str
    status: str
    metrics: dict[str, float]
    reviewer_id: str | None
    created_at: str = field(default_factory=now_iso)
