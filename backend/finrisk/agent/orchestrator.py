from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..domain import Evidence
from ..enterprise.applicability import applicability_report
from ..enterprise.decision import (
    build_decision_trace,
    canonical_hash,
    create_snapshot,
    replay_snapshot,
)
from ..enterprise.decision_bundle import build_decision_bundle
from ..enterprise.domain import AnalysisSnapshot, Decision
from ..enterprise.fusion import (
    failure_aware_decision,
    hierarchical_escalation,
    sensitivity_analysis,
)
from ..enterprise.integrity import CalibrationStatus, epistemic_summary
from ..enterprise.telemetry import component_delta
from ..enterprise.temporal import classify_trajectory
from ..evidence import VERIFIER_VERSION, has_risk_language
from ..facts import build_facts
from ..llm import NarrativeProvider, provider_from_env
from ..scoring import aggregate
from ..severity import severity_label
from ..tools import build_tool_registry
from .planner import AgentPlanner
from .reflection import reflect
from .review import StructuredJudgement, three_role_review
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
            models = self._call(state, "models", traditional_models=context)
            claims: list = []
            claim_verifications: list = []
            semantic_failed = False
            if pages:
                try:
                    extraction = self._call(
                        state, "claims", narrative_evidence=context
                    )
                    claims = extraction["accepted"]
                    claim_verifications = extraction["verifications"]
                    # A schema-valid empty list is indistinguishable from "no risk
                    # language found", so a successful suppression would silently
                    # remove the narrative layer and lower the score. When the
                    # document plainly contains risk language and nothing was
                    # extracted, treat it as a review condition instead.
                    if not extraction["verifications"] and has_risk_language(pages):
                        semantic_failed = True
                        state.warnings.append(
                            "narrative extraction returned no claims for a document "
                            "containing risk language; possible extraction suppression"
                        )
                except Exception as exc:  # noqa: BLE001 - semantic failure degrades safely
                    semantic_failed = True
                    state.warnings.append(f"Narrative provider unavailable: {exc}")
            # Same builder the deterministic assessment uses, so the published trace
            # and the decision it describes cannot be computed from different facts.
            facts = build_facts(current, previous, year, metrics, models, claims)
            context["facts"] = facts
            self._call(state, "rules", risk_rules={"facts": facts})
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
                    "pages": {} if semantic_failed else pages,
                    "document": document,
                    "entity_type": entity_type,
                    "source_map": source_map,
                    # Hand the already-extracted claims over so the provider runs
                    # exactly once per analysis and both paths see one claim set.
                    "narrative_claims": None if semantic_failed else claims,
                    "claim_verifications": None
                    if semantic_failed
                    else claim_verifications,
                },
            )
            state.assessment = assessment.to_dict()
            state.risk_score = assessment.overall_score
            state.confidence = assessment.confidence
            components = assessment.confidence_components
            state.evidence_coverage = assessment.evidence_coverage
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
            # Exactly one outward-facing score, matching `pipeline.decide`: the score
            # the decision is derived from is `overall_score`, and the weighted
            # aggregate is kept under explicit names so the two can never be
            # confused. Both endpoints now publish the same field semantics.
            weighted = assessment.overall_score
            outward = fusion.score if fusion.score is not None else weighted
            state.assessment["weighted_dimension_score"] = weighted
            state.assessment["legacy_weighted_score"] = weighted
            state.assessment["overall_score"] = outward
            state.assessment["risk_level"] = severity_label(outward)
            state.risk_score = outward
            state.risk_severity = fusion.severity
            state.decision = fusion.decision.value
            state.model_disagreement = fusion.disagreement
            # This single-process run holds one period, so there is no series to
            # classify. Multi-period trajectories are produced by the persisted
            # snapshot path (enterprise timeline API) and by the E3 numeric corpus;
            # see docs/temporal_risk_intelligence.md.
            state.risk_trajectory = classify_trajectory([])
            # Read the claim-level classification from the assessment instead of
            # recomputing it here on a thinner fact set. The two used to disagree
            # about whether the same claim was a material contradiction, so one API
            # response could report a claim as both a contradiction and a non-issue.
            state.assessment["disclosure_tensions"] = assessment.disclosure_tensions
            state.assessment["claim_consistency_evaluations"] = (
                assessment.claim_consistency_evaluations
            )
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
                # An empty claim set is a valid semantic result.  Only an actual
                # provider/tool failure is an LLM availability failure.
                "llm_unavailable": semantic_failed,
                "parser_failure": False,
                "stale_data": False,
                "rule_model_contradiction": False,
            }
            failure_decision = failure_aware_decision(fusion, failures)
            state.decision = failure_decision["decision"]
            state.assessment["failure_state"] = failure_decision
            if failure_decision["review_failures"]:
                state.assessment["human_review_required"] = True
                state.assessment["human_review_reason"] = ",".join(failure_decision["review_failures"])
            state.assessment["sensitivity"] = sensitivity_analysis(
                dimension_scores, fusion, policy=decision_policy
            )
            state.assessment["decision_trace"] = state.decision_trace
            applicability = applicability_report(entity_type, facts)
            state.assessment["model_applicability"] = applicability
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
            candidates = synthesize_conclusions(state.assessment)
            state.transition(AgentStatus.VERIFYING)
            # Consume the tool's result instead of discarding it and re-running the
            # gate inline: the registered handler is now the single verification
            # implementation, so the trace and the decision cannot disagree about
            # which conclusions were supported.
            verification = self._call(
                state, "verification", claim_verification={"conclusions": candidates}
            )
            if isinstance(verification, dict) and "accepted" in verification:
                state.conclusions = verification["accepted"]
                state.warnings.extend(verification["warnings"])
            else:
                state.conclusions, warnings = verify_conclusions(candidates)
                state.warnings.extend(warnings)
            evidence_paths = {
                path["reason_code"]: path for path in state.decision_trace["paths"]
            }
            judgements = [
                StructuredJudgement(
                    claim=item.claim,
                    risk_domain=path["risk_domain"],
                    strength="material",
                    evidence_path_ids=(path_id,),
                    model=(
                        path["rule_or_model"].split(":", 1)[1]
                        if str(path["rule_or_model"]).startswith("model:")
                        else None
                    ),
                )
                for item in candidates
                for path_id, path in evidence_paths.items()
                if path_id in item.claim
            ]
            state.role_review = three_role_review(
                judgements,
                evidence_paths,
                {
                    "Altman Z-Score" if item["model"] == "altman" else
                    "Beneish M-Score" if item["model"] == "beneish" else
                    "Piotroski F-Score" if item["model"] == "piotroski" else
                    "Ohlson O-Score": item["status"]
                    for item in applicability
                },
            )
            state.assessment["agent_role_review"] = state.role_review
            # The critic may only move the disposition toward the more cautious end
            # of DISPOSITION_RANK (PASS < FLAG < REVIEW < ABSTAIN). ABSTAIN is
            # absorbing, so a material-but-unverified case that already withheld a
            # decision cannot be softened back to REVIEW. The reason code records
            # which kind of concern drove the move so "evidence missing" and
            # "evidence conflicting" stay distinguishable.
            recommended = state.role_review.get("recommended_decision")
            decision_before_review = state.decision
            if recommended == "REVIEW":
                # A critic raises a separate human-review requirement; it never
                # downgrades the absorbing ABSTAIN disposition to REVIEW.
                state.assessment["review_escalation_reason"] = (
                    "EVIDENCE_CONFLICT" if assessment.contradictions else "EVIDENCE_MISSING"
                )
                state.assessment["human_review_required"] = True
                state.assessment["human_review_reason"] = state.assessment["review_escalation_reason"]
                from ..enterprise.fusion import DISPOSITION_RANK
                if DISPOSITION_RANK[Decision(recommended)] > DISPOSITION_RANK[Decision(state.decision)]:
                    state.decision = recommended
            state.decision_trace["initial_fusion_decision"] = fusion.decision.value
            state.decision_trace["failure_aware_decision"] = failure_decision["decision"]
            state.decision_trace["review_decision"] = state.decision
            state.decision_trace["decision"] = state.decision
            state.assessment["decision_trace"] = state.decision_trace
            state.assessment["final_decision"] = state.decision
            # The final review escalation is part of the failure-aware outcome;
            # snapshots, trace and DecisionBundle must not record competing final
            # dispositions.
            failure_decision["decision"] = state.decision
            state.assessment["failure_state"] = failure_decision
            state.epistemics = epistemic_summary(
                evidence_coverage=state.evidence_coverage,
                evidence_quality=state.confidence,
                disagreement=state.model_disagreement,
                calibration_status=CalibrationStatus.UNCALIBRATED,
            )
            state.assessment["epistemics"] = state.epistemics
            state.assessment["evidence_quality"] = state.confidence
            state.assessment["reliability_status"] = "UNCALIBRATED"
            scoring_config = json.loads(
                (self.root / "config" / "scoring.json").read_text(encoding="utf-8")
            )
            non_model_signals = [
                item
                for item in assessment.triggered_rules
                if not item.rule_id.startswith("MODEL_")
            ]
            narrative_inputs = {
                "going_concern_doubt",
                "material_weakness",
                "refinancing_dependency",
            }
            numeric_rule_signals = [
                item
                for item in non_model_signals
                if not set(item.required_inputs) & narrative_inputs
            ]
            model_signals = [
                item
                for item in assessment.triggered_rules
                if item.rule_id.startswith("MODEL_")
            ]
            narrative_signals = [
                item for item in non_model_signals if item not in numeric_rule_signals
            ]
            rule_score = aggregate(numeric_rule_signals, [], scoring_config)[0]
            model_score = aggregate(numeric_rule_signals + model_signals, [], scoring_config)[0]
            narrative_score = aggregate(
                numeric_rule_signals + model_signals + narrative_signals,
                assessment.contradictions,
                scoring_config,
            )[0]
            latency = {
                name: sum(t.latency_ms for t in state.trace if t.tool == name)
                for name in (
                    "financial_metrics",
                    "risk_rules",
                    "traditional_models",
                    "narrative_evidence",
                    "claim_verification",
                )
            }
            llm_logs = getattr(self.provider, "call_logs", [])
            llm_cost = sum(item.estimated_cost_usd for item in llm_logs)
            numeric_evidence_count = sum(len(values) for values in source_map.values())
            xbrl_executed = any(
                "xbrl" in str(item.source).lower()
                for values in source_map.values()
                for item in values
            )
            telemetry = [
                component_delta(
                    "XBRL",
                    risk_before=0.0,
                    risk_after=0.0,
                    coverage_before=0.0,
                    coverage_after=components.get("numeric_provenance_coverage", 0.0),
                    new_evidence=numeric_evidence_count,
                    latency_ms=0,
                    status="executed" if xbrl_executed else "not_executed",
                ),
                component_delta(
                    "rules",
                    risk_before=0.0,
                    risk_after=rule_score,
                    coverage_before=components.get("numeric_provenance_coverage", 0.0),
                    coverage_after=components.get("numeric_provenance_coverage", 0.0),
                    new_evidence=len(numeric_rule_signals),
                    latency_ms=latency.get("risk_rules", 0),
                ),
                component_delta(
                    "traditional_models",
                    risk_before=rule_score,
                    risk_after=model_score,
                    coverage_before=components.get("numeric_provenance_coverage", 0.0),
                    coverage_after=components.get("numeric_provenance_coverage", 0.0),
                    new_evidence=sum(item.output is not None for item in assessment.models),
                    latency_ms=latency.get("traditional_models", 0),
                ),
                component_delta(
                    "LLM_narrative",
                    risk_before=model_score,
                    risk_after=narrative_score,
                    coverage_before=components.get("numeric_provenance_coverage", 0.0),
                    coverage_after=state.evidence_coverage,
                    new_evidence=len(claims),
                    latency_ms=latency.get("narrative_evidence", 0),
                    estimated_cost_usd=llm_cost,
                    status="failed" if semantic_failed else "executed" if pages else "not_executed",
                ),
                component_delta(
                    "Critic",
                    risk_before=narrative_score,
                    risk_after=narrative_score,
                    coverage_before=state.evidence_coverage,
                    coverage_after=state.evidence_coverage,
                    decision_changed=decision_before_review != state.decision,
                    new_evidence=len(state.role_review.get("challenges", [])),
                ),
                component_delta(
                    "Verifier",
                    risk_before=narrative_score,
                    risk_after=narrative_score,
                    coverage_before=state.evidence_coverage,
                    coverage_after=state.evidence_coverage,
                    new_evidence=sum(len(item.evidence) for item in state.conclusions),
                    latency_ms=latency.get("claim_verification", 0),
                ),
                component_delta(
                    "fusion",
                    risk_before=narrative_score,
                    risk_after=state.risk_score,
                    coverage_before=state.evidence_coverage,
                    coverage_after=state.evidence_coverage,
                    disagreement_before=0.0,
                    disagreement_after=state.model_disagreement,
                    decision_changed=state.decision != decision_before_review,
                    new_evidence=len(state.decision_trace.get("paths", [])),
                ),
            ]
            state.component_telemetry = [item.to_dict() for item in telemetry]
            state.assessment["component_telemetry"] = state.component_telemetry
            snapshot = create_snapshot(
                "local",
                company,
                frozen_input,
                state.assessment,
                document_versions,
                versions,
            )
            state.analysis_snapshot = snapshot.__dict__
            bundle = build_decision_bundle(
                "local",
                company,
                document_versions,
                frozen_input,
                state.assessment,
                {
                    "score": state.risk_score,
                    "severity": state.risk_severity,
                    "trajectory": state.risk_trajectory,
                    "coverage": state.evidence_coverage,
                    "confidence": state.confidence,
                },
                state.decision_trace["paths"],
                {
                    "metrics": state.assessment.get("metrics", {}),
                    "models": state.assessment.get("models", []),
                    "rules": state.assessment.get("triggered_rules", []),
                },
                [trace.__dict__ for trace in state.trace],
                versions,
                state.decision,
                epistemics=state.epistemics,
                component_telemetry=state.component_telemetry,
            )
            state.decision_bundle = bundle.to_dict()
            state.transition(AgentStatus.REFLECTING)
            state.reflection = reflect(state.assessment)
            if assessment.contradictions or state.assessment.get("human_review_required"):
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
            # Derived from the policy hash so a change to the escalation
            # parameters is detected as a component-version change rather than
            # being misreported as output drift.
            "fusion": f"hierarchical_escalation:{canonical_hash(decision_policy)[:12]}",
            "applicability": "applicability-router:v1",
            "calibration": "UNCALIBRATED:v1",
            "evidence_verifier": VERIFIER_VERSION,
            "agent_review": "analyst-critic-verifier:v1",
            "prompt": getattr(self.provider, "prompt_version", "mock-or-unversioned"),
            "model": getattr(self.provider, "model_id", self.provider.__class__.__name__),
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
        started = time.perf_counter()
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
                    latency_ms=int((time.perf_counter() - started) * 1000),
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
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            raise
