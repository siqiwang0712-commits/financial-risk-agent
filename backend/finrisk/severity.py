"""Single source of truth for score -> severity mapping.

`scoring.risk_level` (human-readable labels used by assessments and the Workbench)
and `enterprise.fusion._severity` (machine-readable keys used by decisions and
reason codes) previously each hard-coded the same 20/40/60/80 boundaries. They are
kept as two presentations of one table so a threshold change cannot drift between
them.
"""

from __future__ import annotations

# (lower bound inclusive, machine key, human label)
SEVERITY_BANDS: tuple[tuple[float, str, str], ...] = (
    (80.0, "critical", "Critical"),
    (60.0, "high", "High"),
    (40.0, "moderate", "Moderate"),
    (20.0, "low", "Low"),
    (0.0, "very_low", "Very Low"),
)


def severity_key(score: float | None) -> str:
    """Machine-readable severity key; `unknown` when no score is supported."""
    if score is None:
        return "unknown"
    for threshold, key, _ in SEVERITY_BANDS:
        if score >= threshold:
            return key
    return "very_low"


def severity_label(score: float | None) -> str:
    """Human-readable severity label; `N/A` when no score is supported."""
    if score is None:
        return "N/A"
    for threshold, _, label in SEVERITY_BANDS:
        if score >= threshold:
            return label
    return "Very Low"
