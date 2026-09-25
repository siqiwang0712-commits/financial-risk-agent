"""Subgroup, missingness, threshold, calibration and complexity analyses for E4-R.

Subgroup rules are prespecified and applied uniformly: a sector is reported only when it
reaches ``min_n`` observations *and* ``min_events`` events. Everything else is
``NOT_ESTIMABLE`` -- not "small but interesting". Every sector that clears the gate is
reported, including the ones where B6 loses.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import e4r_stats

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def metrics(labels: list[int], scores: list[float]) -> dict:
    """AUROC and PR-AUC, or None when the subgroup cannot support them."""
    if len(set(labels)) < 2:
        return {"auroc": None, "pr_auc": None, "status": "SINGLE_CLASS"}
    finite = [(y, s) for y, s in zip(labels, scores, strict=True) if not math.isnan(s)]
    if len(finite) != len(labels):
        return {"auroc": None, "pr_auc": None, "status": "MISSING_SCORES"}
    return {
        "auroc": e4r_stats.roc_auc(labels, scores),
        "pr_auc": e4r_stats.marginal_metric(
            e4r_stats.paired_rows(
                [str(i) for i in range(len(labels))],
                {str(i): y for i, y in enumerate(labels)},
                {str(i): s for i, s in enumerate(scores)},
                {str(i): s for i, s in enumerate(scores)},
            ),
            "reference",
            "pr_auc",
        ),
        "status": "OK",
    }


def subgroup_table(
    observation_ids: list[str],
    labels: dict[str, int],
    membership: dict[str, str],
    score_vectors: dict[str, dict[str, float]],
    min_n: int = 40,
    min_events: int = 10,
) -> list[dict]:
    """One row per subgroup; subgroups below the gate are reported as NOT_ESTIMABLE."""
    buckets: dict[str, list[str]] = {}
    for oid in observation_ids:
        buckets.setdefault(membership[oid], []).append(oid)
    rows = []
    for name in sorted(buckets):
        members = buckets[name]
        events = sum(labels[oid] for oid in members)
        row: dict = {
            "subgroup": name,
            "n": len(members),
            "events": events,
            "prevalence": events / len(members) if members else None,
            "min_n": min_n,
            "min_events": min_events,
            "estimable": len(members) >= min_n and events >= min_events,
        }
        if not row["estimable"]:
            row["status"] = "NOT_ESTIMABLE"
            row["reason"] = f"n={len(members)} < {min_n} or events={events} < {min_events}"
            row["models"] = {}
            rows.append(row)
            continue
        row["status"] = "OK"
        row["models"] = {}
        for model_id, vector in score_vectors.items():
            subgroup_labels = [labels[oid] for oid in members]
            subgroup_scores = [vector[oid] for oid in members]
            row["models"][model_id] = metrics(subgroup_labels, subgroup_scores)
        rows.append(row)
    return rows


def quantile_membership(
    observation_ids: list[str], values: dict[str, float], labels: list[str]
) -> dict[str, str]:
    """Split observations into equal-count bins on a *feature-side* quantity.

    The split uses no outcome information, so it cannot leak the label.
    """
    ordered = sorted(observation_ids, key=lambda oid: (values[oid], oid))
    size = len(ordered)
    membership: dict[str, str] = {}
    for index, oid in enumerate(ordered):
        position = min(len(labels) - 1, (index * len(labels)) // max(1, size))
        membership[oid] = labels[position]
    return membership


def missingness_profile(
    observation_ids: list[str], matrix: dict[str, list[float]], fields: list[str]
) -> dict[str, float]:
    """Fraction of the listed fields missing for each observation."""
    profile = {}
    for position, oid in enumerate(observation_ids):
        missing = sum(
            1 for name in fields if math.isnan(matrix[name][position])
        )
        profile[oid] = missing / len(fields) if fields else 0.0
    return profile


def missingness_bands(profile: dict[str, float], labels: tuple[str, ...] = ("low", "medium", "high")) -> dict[str, str]:
    ordered = sorted(profile, key=lambda oid: (profile[oid], oid))
    size = len(ordered)
    membership: dict[str, str] = {}
    for index, oid in enumerate(ordered):
        membership[oid] = labels[min(len(labels) - 1, (index * len(labels)) // max(1, size))]
    return membership


def threshold_table(
    labels: list[int], score_vectors: dict[str, list[float]], grid: list[float]
) -> dict:
    return {
        "status": "SENSITIVITY_ONLY",
        "note": (
            "AUROC is threshold-free; this sweep exists to show how the operating point "
            "moves. It does not select a threshold and must not be used to update the "
            "production configuration."
        ),
        "threshold_grid": grid,
        "models": {
            model_id: e4r_stats.threshold_sweep(labels, scores, grid)
            for model_id, scores in score_vectors.items()
        },
    }


def calibration_table(labels: list[int], score_vectors: dict[str, list[float]], bins: int = 10) -> dict:
    return {
        "status": "UNCALIBRATED",
        "note": (
            "Descriptive diagnostics on out-of-fold scores. No calibration map was fitted "
            "on this cohort, so these numbers must not be reported as calibrated performance."
        ),
        "models": {
            model_id: e4r_stats.calibration_diagnostics(labels, scores, bins)
            for model_id, scores in score_vectors.items()
        },
    }


def complexity_table(entries: list[dict]) -> dict:
    """Deterministic / dependency / operational burden, per comparator."""
    return {
        "status": "OK",
        "note": (
            "E4-R compares deterministic heuristics with conventional tabular learners. "
            "No LLM inference is involved, so no token or API cost is attributed."
        ),
        "models": entries,
    }
