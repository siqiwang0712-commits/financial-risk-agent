from __future__ import annotations

from .state import MaterialConclusion


def verify_conclusions(
    conclusions: list[MaterialConclusion],
) -> tuple[list[MaterialConclusion], list[str]]:
    accepted, warnings = [], []
    for conclusion in conclusions:
        if conclusion.evidence:
            accepted.append(conclusion)
        else:
            warnings.append(f"Rejected unsupported conclusion: {conclusion.claim}")
    return accepted, warnings
