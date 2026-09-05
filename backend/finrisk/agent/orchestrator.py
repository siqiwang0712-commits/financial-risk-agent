from __future__ import annotations

from pathlib import Path
from typing import Any

from ..llm import NarrativeProvider, provider_from_env
from ..tools import build_tool_registry
from .planner import AgentPlanner
from .reflection import reflect
from .state import AgentState, AgentStatus, ToolCallTrace
from .synthesis import synthesize_conclusions
from .verification import verify_conclusions


class FinancialRiskAgent:
    """Public orchestration boundary. Trace records actions and evidence, never hidden reasoning."""

    def __init__(
        self, root: Path | None = None, provider: NarrativeProvider | None = None
    ):
        self.root = root or Path(__file__).resolve().parents[3]
        self.provider = provider or provider_from_env()
        self.planner = AgentPlanner()
        self.tools = build_tool_registry(self.root, self.provider)

    def run(
        self,
        company: str,
        year: int,
        current: dict,
        previous: dict | None = None,
        pages: dict[int, str] | None = None,
        document: str = "Annual Report",
        entity_type: str = "industrial",
        source_map: dict | None = None,
    ) -> AgentState:
        state = AgentState(company, year)
        pages, source_map = pages or {}, source_map or {}
        try:
            state.transition(AgentStatus.PLANNING)
            state.plan = self.planner.plan(
                has_previous=bool(previous), has_pages=bool(pages)
            )
            state.transition(AgentStatus.COLLECTING)
            context: dict[str, Any] = {
                "current": current,
                "previous": previous,
                "pages": pages,
                "document": document,
                "year": year,
                "entity_type": entity_type,
            }
            metrics = self._call(
                state,
                "metrics",
                financial_metrics={
                    "current": current,
                    "previous": previous,
                    "year": year,
                },
            )
            facts = current | {name: metric.value for name, metric in metrics.items()}
            context["facts"] = facts
            self._call(state, "models", traditional_models=context)
            self._call(state, "rules", risk_rules={"facts": facts})
            claims = (
                self._call(state, "claims", narrative_evidence=context) if pages else []
            )
            state.transition(AgentStatus.CROSS_CHECKING)
            if pages:
                self._call(
                    state,
                    "consistency",
                    contradiction_detection={"claims": claims, "facts": facts},
                )
            if previous:
                self._call(
                    state,
                    "periods",
                    period_comparison={"current": current, "previous": previous},
                )
            state.transition(AgentStatus.SYNTHESIZING)
            assessment = self._call(
                state,
                "assessment",
                risk_assessment={
                    "company": company,
                    "year": year,
                    "current": current,
                    "previous": previous,
                    "pages": pages,
                    "document": document,
                    "entity_type": entity_type,
                    "source_map": source_map,
                },
            )
            state.assessment = assessment.to_dict()
            state.risk_score = assessment.overall_score
            state.confidence = assessment.confidence
            components = assessment.confidence_components
            state.evidence_coverage = (
                round(sum(components.values()) / len(components), 3)
                if components
                else 0.0
            )
            candidates = synthesize_conclusions(state.assessment)
            state.transition(AgentStatus.VERIFYING)
            self._call(
                state, "verification", claim_verification={"conclusions": candidates}
            )
            state.conclusions, warnings = verify_conclusions(candidates)
            state.warnings.extend(warnings)
            state.transition(AgentStatus.REFLECTING)
            state.reflection = reflect(state.assessment)
            if assessment.overall_score is None:
                state.transition(AgentStatus.INSUFFICIENT_EVIDENCE)
            elif assessment.contradictions:
                state.transition(AgentStatus.REVIEW_REQUIRED)
            else:
                state.transition(AgentStatus.COMPLETED)
        except Exception as exc:  # noqa: BLE001 - provider/tool failures must fail closed
            state.warnings.append(str(exc))
            if state.status not in {
                AgentStatus.COMPLETED,
                AgentStatus.INSUFFICIENT_EVIDENCE,
                AgentStatus.REVIEW_REQUIRED,
            }:
                state.status = AgentStatus.FAILED
        return state

    def run_document(
        self, company: str, year: int, path: Path, document: str
    ) -> AgentState:
        ingested = self.tools.call(
            "pdf_extraction", path=path, document=document, fiscal_year=year
        )
        state = self.run(
            company,
            year,
            ingested["current"],
            ingested["previous"],
            ingested["pages"],
            document,
            source_map=ingested["source_map"],
        )
        state.trace.insert(
            0,
            ToolCallTrace(
                "ingestion",
                "collect",
                "pdf_extraction",
                "success",
                f"Resolved {ingested['extraction']['candidate_count']} financial candidate(s)",
            ),
        )
        if state.assessment is not None:
            state.assessment["extraction"] = ingested["extraction"]
        return state

    def _call(self, state: AgentState, step_id: str, **tool_input: dict[str, Any]):
        tool_name, kwargs = next(iter(tool_input.items()))
        try:
            result = self.tools.call(tool_name, **kwargs)
            size = len(result) if hasattr(result, "__len__") else 1
            state.trace.append(
                ToolCallTrace(
                    step_id,
                    next((s.phase for s in state.plan if s.id == step_id), "analyze"),
                    tool_name,
                    "success",
                    f"Produced {size} structured result(s)",
                )
            )
            return result
        except Exception as exc:
            state.trace.append(
                ToolCallTrace(
                    step_id,
                    "tool",
                    tool_name,
                    "failed",
                    "Tool call rejected",
                    error=str(exc),
                )
            )
            raise
