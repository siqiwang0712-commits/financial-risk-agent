from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class AgentStatus(StrEnum):
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    COLLECTING = "COLLECTING_EVIDENCE"
    ANALYZING = "ANALYZING"
    CROSS_CHECKING = "CROSS_CHECKING"
    VERIFYING = "VERIFYING"
    REFLECTING = "REFLECTING"
    SYNTHESIZING = "SYNTHESIZING"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PlanStep:
    id: str
    phase: str
    tool: str
    purpose: str


@dataclass
class ToolCallTrace:
    step_id: str
    phase: str
    tool: str
    status: str
    summary: str
    evidence_ids: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class MaterialConclusion:
    claim: str
    reason: str
    tool: str
    rationale: str
    confidence: float
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentState:
    company: str
    fiscal_year: int
    status: AgentStatus = AgentStatus.UNDERSTANDING
    plan: list[PlanStep] = field(default_factory=list)
    trace: list[ToolCallTrace] = field(default_factory=list)
    conclusions: list[MaterialConclusion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reflection: list[str] = field(default_factory=list)
    assessment: dict[str, Any] | None = None
    risk_score: float | None = None
    confidence: float = 0.0
    evidence_coverage: float = 0.0

    def transition(self, target: AgentStatus) -> None:
        terminal = {
            AgentStatus.COMPLETED,
            AgentStatus.INSUFFICIENT_EVIDENCE,
            AgentStatus.REVIEW_REQUIRED,
            AgentStatus.FAILED,
        }
        if self.status in terminal:
            raise ValueError(f"cannot transition from terminal state {self.status}")
        self.status = target

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
