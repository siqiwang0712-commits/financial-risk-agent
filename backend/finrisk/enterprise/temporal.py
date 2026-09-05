from __future__ import annotations

from itertools import pairwise


def classify_trajectory(values: list[float | None]) -> str:
    observed = [value for value in values if value is not None]
    if len(observed) < 2:
        return "insufficient_history"
    changes = [b - a for a, b in pairwise(observed)]
    if all(value >= 60 for value in observed[-2:]):
        return "persistent_weakness"
    if changes[-1] >= 20:
        return "sharply_deteriorating"
    if changes[-1] >= 5:
        return "deteriorating"
    if changes[-1] <= -20:
        return "recovery"
    if changes[-1] <= -5:
        return "improving"
    return "stable"
