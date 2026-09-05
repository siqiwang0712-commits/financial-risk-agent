from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain import Evidence
from ..enterprise.decision import (
    build_decision_trace,
    canonical_hash,
    create_snapshot,
    replay_snapshot,
)
from ..enterprise.domain import AnalysisSnapshot
from ..enterprise.fusion import (
    failure_aware_decision,
    hierarchical_escalation,
    sensitivity_analysis,
)
from ..enterprise.temporal import classify_trajectory
from ..enterprise.tension import classify_tension
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
            contradictions = []
            if pages:
                contradictions = self._call(
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
            dimension_scores = {
                name: value.get("score")
                for name, value in state.assessment.get("dimensions", {}).items()
            }
            decision_policy = json.loads(
                (self.root / "config" / "decision_policy.json").read_text(
                    encoding="utf-8"
                )
            )
            fusion = hierarchical_escalation(
                dimension_scores,
                state.evidence_coverage,
                state.confidence,
                decision_policy,
            )
            state.fusion = fusion.__dict__
            state.risk_score = fusion.score
            state.risk_severity = fusion.severity
            state.decision = fusion.decision.value
            state.model_disagreement = fusion.disagreement
            state.risk_trajectory = classify_trajectory([])
            tensions = []
            for claim in claims:
                matched = [
                    item
                    for item in contradictions
                    if item.management_claim == claim.claim
                ]
                opposing = [
                    fact for item in matched for fact in item.conflicting_evidence
                ]
                tensions.append(
                    classify_tension(
                        claim,
                        [],
                        opposing,
                        "Compared with all available normalized evidence for the claim category.",
                    ).to_dict()
                )
            state.assessment["disclosure_tensions"] = tensions
            state.assessment["enterprise_fusion"] = state.fusion
            versions = self.component_versions()
            state.decision_trace = build_decision_trace(
                state.assessment, state.fusion, versions
            )
            failures = {
                "missing_evidence": bool(
                    state.decision_trace["material_path_count"]
                    and not state.decision_trace["verified_path_count"]
                ),
                "conflicting_evidence": bool(assessment.contradictions),
                "llm_unavailable": bool(pages and not claims),
                "parser_failure": False,
                "stale_data": False,
                "rule_model_contradiction": False,
            }
            failure_decision = failure_aware_decision(fusion, failures)
            state.decision = failure_decision["decision"]
            state.assessment["failure_state"] = failure_decision
            state.assessment["sensitivity"] = sensitivity_analysis(
                dimension_scores, fusion, policy=decision_policy
            )
            state.assessment["decision_trace"] = state.decision_trace
            frozen_input = {
                "company": company,
                "year": year,
                "current": current,
                "previous": previous,
                "pages": pages,
                "document": document,
                "entity_type": entity_type,
                "source_map": {
                    key: [evidence.__dict__ for evidence in values]
                    for key, values in source_map.items()
                },
            }
            document_versions = (
                {document: canonical_hash(pages)}
                if pages
                else {document: "NO_DOCUMENT"}
            )
            snapshot = create_snapshot(
                "local",
                company,
                frozen_input,
                state.assessment,
                document_versions,
                versions,
            )
            state.analysis_snapshot = snapshot.__dict__
            candidates = synthesize_conclusions(state.assessment)
            state.transition(AgentStatus.VERIFYING)
            self._call(
                state, "verification", claim_verification={"conclusions": candidates}
            )
            state.conclusions, warnings = verify_conclusions(candidates)
            state.warnings.extend(warnings)
            state.transition(AgentStatus.REFLECTING)
            state.reflection = reflect(state.assessment)
            if assessment.contradictions:
                state.transition(AgentStatus.REVIEW_REQUIRED)
            elif state.decision == "ABSTAIN":
                state.transition(AgentStatus.INSUFFICIENT_EVIDENCE)
            elif state.decision == "REVIEW":
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

    def component_versions(self) -> dict[str, str]:
        decision_policy = json.loads(
            (self.root / "config" / "decision_policy.json").read_text(encoding="utf-8")
        )
        return {
            "rules": canonical_hash(
                (self.root / "rules" / "rules.json").read_text(encoding="utf-8")
            ),
            "scoring": canonical_hash(
                (self.root / "config" / "scoring.json").read_text(encoding="utf-8")
            ),
            "decision_policy": canonical_hash(decision_policy),
            "fusion": "hierarchical_escalation:v1",
            "prompt": getattr(self.provider, "prompt_version", "mock-or-unversioned"),
            "model": self.provider.__class__.__name__,
        }

    def replay(self, snapshot: AnalysisSnapshot) -> dict:
        def runner(frozen: dict) -> dict:
            source_map = {
                key: [Evidence(**evidence) for evidence in values]
                for key, values in frozen.get("source_map", {}).items()
            }
            state = self.run(
                frozen["company"],
                frozen["year"],
                frozen["current"],
                frozen.get("previous"),
                {int(key): value for key, value in frozen.get("pages", {}).items()},
                frozen.get("document", "Annual Report"),
                frozen.get("entity_type", "industrial"),
                source_map,
            )
            return state.assessment or {}

        return replay_snapshot(snapshot, runner, self.component_versions())

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
