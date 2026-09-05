from __future__ import annotations

from collections import Counter
from dataclasses import asdict

from .domain import RiskCase, RiskCaseStatus


def portfolio_overview(cases: list[RiskCase]) -> dict:
    severity_rank = {
        "very_low": 10,
        "low": 20,
        "moderate": 40,
        "high": 60,
        "critical": 80,
    }
    open_cases = [
        case
        for case in cases
        if case.status not in {RiskCaseStatus.RESOLVED, RiskCaseStatus.CLOSED}
    ]
    ranked = sorted(
        open_cases, key=lambda case: severity_rank.get(case.severity, 0), reverse=True
    )
    return {
        "case_count": len(cases),
        "open_case_count": len(open_cases),
        "critical_open_count": sum(case.severity == "critical" for case in open_cases),
        "by_domain": dict(Counter(case.domain.value for case in open_cases)),
        "by_status": dict(Counter(case.status.value for case in cases)),
        "top_risks": [asdict(case) for case in ranked[:10]],
    }
