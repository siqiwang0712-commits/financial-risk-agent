from __future__ import annotations

from typing import Any


def reflect(assessment: dict[str, Any]) -> list[str]:
    notes = []
    if assessment.get("overall_score") is None:
        notes.append(
            "Overall score withheld because minimum dimension coverage was not met."
        )
    if assessment.get("contradictions"):
        notes.append(
            "Narrative and numeric signals conflict; human review is required."
        )
    if assessment.get("missing_information"):
        notes.append(
            "Missing inputs reduce evidence coverage; missing values were not treated as zero."
        )
    return notes
