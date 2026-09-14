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


# The workflow's legal edges, in the order `FinancialRiskAgent.run` performs them.
#
# An empty set marks a terminal state. `FAILED` is terminal too, but the
# orchestrator's `except` handler assigns it directly rather than transitioning,
# so a failure can always be recorded no matter how far the run got.
LEGAL_TRANSITIONS: dict[AgentStatus, frozenset[AgentStatus]] = {
    AgentStatus.UNDERSTANDING: frozenset({AgentStatus.PLANNING}),
    AgentStatus.PLANNING: frozenset({AgentStatus.COLLECTING}),
    AgentStatus.COLLECTING: frozenset({AgentStatus.ANALYZING, AgentStatus.CROSS_CHECKING}),
    AgentStatus.ANALYZING: frozenset({AgentStatus.CROSS_CHECKING}),
    AgentStatus.CROSS_CHECKING: frozenset({AgentStatus.SYNTHESIZING}),
    AgentStatus.SYNTHESIZING: frozenset({AgentStatus.VERIFYING}),
    AgentStatus.VERIFYING: frozenset({AgentStatus.REFLECTING}),
    AgentStatus.REFLECTING: frozenset(
        {
            AgentStatus.COMPLETED,
            AgentStatus.INSUFFICIENT_EVIDENCE,
            AgentStatus.REVIEW_REQUIRED,
        }
    ),
    AgentStatus.COMPLETED: frozenset(),
    AgentStatus.INSUFFICIENT_EVIDENCE: frozenset(),
    AgentStatus.REVIEW_REQUIRED: frozenset(),
    AgentStatus.FAILED: frozenset(),
}


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
    latency_ms: int = 0


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
    confidence_semantics: str = "LEGACY_EVIDENCE_QUALITY_INDEX_NOT_PROBABILITY"
    evidence_coverage: float = 0.0
    risk_severity: str = "unknown"
    risk_trajectory: str = "insufficient_history"
    decision: str = "ABSTAIN"
    model_disagreement: float = 0.0
    fusion: dict[str, Any] = field(default_factory=dict)
    decision_trace: dict[str, Any] = field(default_factory=dict)
    analysis_snapshot: dict[str, Any] = field(default_factory=dict)
    decision_bundle: dict[str, Any] = field(default_factory=dict)
    role_review: dict[str, Any] = field(default_factory=dict)
    epistemics: dict[str, Any] = field(default_factory=dict)
    component_telemetry: list[dict[str, Any]] = field(default_factory=list)

    def transition(self, target: AgentStatus) -> None:
        """Move to `target`, rejecting anything the workflow cannot do.

        The previous guard only rejected *leaving* a terminal state, so any
        non-terminal state could jump straight to any other - `UNDERSTANDING`
        to `COMPLETED` was accepted, and with it every skip and backward move in
        between. The published trace is a claim about the order in which the
        Agent worked, so the order has to be enforced somewhere.

        `ANALYZING` is reachable from `COLLECTING` even though nothing emits it
        today, which records where it belongs instead of leaving it undefined.
        """
        allowed = LEGAL_TRANSITIONS[self.status]
        if target not in allowed:
            if not allowed:
                raise ValueError(f"cannot transition from terminal state {self.status}")
            raise ValueError(
                f"illegal transition {self.status} -> {target}; "
                f"allowed: {sorted(item.value for item in allowed)}"
            )
        self.status = target

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
