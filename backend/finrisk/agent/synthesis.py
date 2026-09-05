from __future__ import annotations

from typing import Any

from .state import MaterialConclusion


def synthesize_conclusions(assessment: dict[str, Any]) -> list[MaterialConclusion]:
    conclusions = []
    for signal in assessment.get("triggered_rules", []):
        evidence = [
            {
                "source": ref.get("document", ""),
                "document": ref.get("document", ""),
                "company": assessment["company"],
                "period": assessment["reporting_period"],
                "page": ref.get("page"),
                "quote": ref.get("source_text", ""),
                "value": None,
                "unit": None,
                "confidence": ref.get("confidence", 0.0),
                "verification_status": ref.get("verification_status", "unverified"),
            }
            for ref in signal.get("source_refs", [])
        ]
        if not evidence:
            evidence = [
                {
                    "source": "deterministic",
                    "document": "calculated metrics",
                    "company": assessment["company"],
                    "period": assessment["reporting_period"],
                    "page": None,
                    "quote": item,
                    "value": None,
                    "unit": None,
                    "confidence": 1.0,
                    "verification_status": "derived",
                }
                for item in signal.get("evidence", [])
            ]
        conclusions.append(
            MaterialConclusion(
                f"{signal['category']} risk signal {signal['rule_id']}",
                signal["rationale"],
                "risk_rules",
                f"Configured rule {signal['rule_id']} triggered",
                assessment["confidence"],
                evidence,
            )
        )
    return conclusions
