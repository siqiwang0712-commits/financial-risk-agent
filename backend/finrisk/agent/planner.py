from __future__ import annotations

from .state import PlanStep


class AgentPlanner:
    """Creates an inspectable execution plan; it never performs financial calculations."""

    def plan(self, *, has_previous: bool, has_pages: bool) -> list[PlanStep]:
        steps = [
            PlanStep(
                "metrics",
                "analyze",
                "financial_metrics",
                "Calculate ratios and trends deterministically",
            ),
            PlanStep(
                "models",
                "analyze",
                "traditional_models",
                "Evaluate model applicability and outputs",
            ),
            PlanStep(
                "rules",
                "analyze",
                "risk_rules",
                "Evaluate configured expert risk signals",
            ),
        ]
        if has_pages:
            steps += [
                PlanStep(
                    "claims",
                    "collect",
                    "narrative_evidence",
                    "Extract and verify narrative claims",
                ),
                PlanStep(
                    "consistency",
                    "cross_check",
                    "contradiction_detection",
                    "Compare verified claims with numeric facts",
                ),
            ]
        if has_previous:
            steps.append(
                PlanStep(
                    "periods",
                    "cross_check",
                    "period_comparison",
                    "Confirm multi-period coverage",
                )
            )
        steps += [
            PlanStep(
                "assessment",
                "synthesize",
                "risk_assessment",
                "Create deterministic evidence-linked assessment",
            ),
            PlanStep(
                "verification",
                "verify",
                "claim_verification",
                "Reject unsupported material conclusions",
            ),
        ]
        return steps
