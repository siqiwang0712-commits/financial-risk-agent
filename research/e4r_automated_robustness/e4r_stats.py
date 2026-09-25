"""Statistical primitives for E4-R.

Everything that already exists in the E4-S audit (AUROC, PR-AUC, paired DeLong, BCa
cluster bootstrap, Holm) is **imported** from :mod:`e4s_stats` rather than re-implemented,
so E4-R's inference is methodologically continuous with the audit it is built on. This
module only adds what E4-S did not need:

* a fuller description of a bootstrap distribution (quantiles plus tail probabilities);
* threshold-sweep operating characteristics;
* descriptive calibration diagnostics;
* leave-one-out / leave-group-out influence for a paired ΔAUROC.

All scores handled here remain ``UNCALIBRATED``; nothing in this module fits a
calibration map.
"""

from __future__ import annotations

import gc
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
E4S_DIR = REPO_ROOT / "research" / "e4_statistical_audit"
for _path in (str(E4S_DIR), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# `roc_auc` and `cluster_bootstrap` are re-exported deliberately: callers outside this
# module use the same primitives the study's inference is built on rather than importing
# from two places.
from e4s_stats import (  # noqa: F401
    METRICS,
    PairedObservation,
    cluster_bootstrap,
    delong_paired,
    delta_metric,
    holm_adjust,
    marginal_metric,
    normal_cdf,
    percentile_linear,
    percentile_nearest_rank,
    roc_auc,
)

BOOTSTRAP_TAIL_THRESHOLDS = (0.0, 0.01, 0.02, 0.03)


def paired_rows(
    observation_ids: list[str],
    labels: dict[str, int],
    reference: dict[str, float],
    challenger: dict[str, float],
) -> list[PairedObservation]:
    """One paired row per observation; reference is the comparator, challenger the test arm."""
    return [
        PairedObservation(
            cluster_id=observation_id,
            label=int(labels[observation_id]),
            reference_score=float(reference[observation_id]),
            challenger_score=float(challenger[observation_id]),
        )
        for observation_id in observation_ids
    ]


def bootstrap_summary(result, tail_thresholds=BOOTSTRAP_TAIL_THRESHOLDS) -> dict:
    """Describe a bootstrap replicate distribution beyond a single interval."""
    values = [float(v) for v in result.replicate_values]
    summary: dict = {
        "metric": result.metric,
        "observed": result.observed,
        "samples": result.samples,
        "valid_replicates": result.valid_replicates,
        "invalid_replicates": result.invalid_replicates,
        "cluster_count": result.cluster_count,
        "standard_error": result.standard_error,
        "bias": result.bias,
        "percentile_nearest_rank": list(result.percentile_nearest_rank),
        "percentile_linear": list(result.percentile_linear),
        "bca": list(result.bca) if result.bca else None,
        "bca_low": result.bca[0] if result.bca else None,
        "bca_high": result.bca[1] if result.bca else None,
    }
    if values:
        summary["median"] = percentile_linear(values, 0.5)
        summary["q025"] = percentile_linear(values, 0.025)
        summary["q25"] = percentile_linear(values, 0.25)
        summary["q75"] = percentile_linear(values, 0.75)
        summary["q975"] = percentile_linear(values, 0.975)
        summary["mean"] = sum(values) / len(values)
        for threshold in tail_thresholds:
            key = f"P_delta_gt_{threshold}".replace(".", "p")
            summary[key] = sum(1 for value in values if value > threshold) / len(values)
    return summary


def _bootstrap_engine(rows, metric, samples, seed):
    """Run the replicate loop with the cyclic collector batched out of the hot path.

    The resampling unit, the statistic and the BCa correction are exactly
    :func:`e4s_stats.cluster_bootstrap`'s; only the collector policy differs. Unmanaged, the
    loop spends most of its time re-scanning long-lived container objects as the replicate
    list grows (measured: 2.2 s for 2,000 replicates but 96 s for 20,000 — a 47x cost for a
    10x workload). ``test_bootstrap_engine_matches_e4s_stats`` pins this engine to
    byte-identical output against the E4-S implementation at a smaller replicate count.
    """
    from e4s_stats import _resample as e4s_resample

    observed = delta_metric(rows, metric)
    rng = random.Random(seed)
    values: list[float] = []
    invalid = 0
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        for index in range(samples):
            value = delta_metric(e4s_resample(rows, rng), metric)
            if value is None:
                invalid += 1
            else:
                values.append(value)
            if (index + 1) % 1000 == 0:
                gc.collect()
    finally:
        gc.collect()
        if was_enabled:
            gc.enable()
    return observed, values, invalid


def marginal_bootstrap(
    observation_ids: list[str],
    labels: dict[str, int],
    scores: dict[str, float],
    metric: str = "auroc",
    samples: int = 20000,
    seed: int = 20260925,
) -> dict:
    """Cluster bootstrap of a *single* scorer's metric.

    The delta bootstrap answers "is A better than B"; this answers "how well is A measured",
    which is what a missingness arm or a stability repeat needs. The resampling unit is the
    observation (one per company), matching the rest of the study.
    """
    measure = METRICS[metric]
    label_vector = [labels[oid] for oid in observation_ids]
    score_vector = [scores[oid] for oid in observation_ids]
    observed = measure(label_vector, score_vector)
    rng = random.Random(seed)
    values: list[float] = []
    size = len(observation_ids)
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        for index in range(samples):
            picks = [rng.randrange(size) for _ in range(size)]
            value = measure([label_vector[i] for i in picks], [score_vector[i] for i in picks])
            if value is not None:
                values.append(value)
            if (index + 1) % 1000 == 0:
                gc.collect()
    finally:
        gc.collect()
        if was_enabled:
            gc.enable()
    if not values:
        return {"metric": metric, "observed": observed, "samples": samples, "valid_replicates": 0}
    mean_value = sum(values) / len(values)
    return {
        "metric": metric,
        "observed": observed,
        "samples": samples,
        "valid_replicates": len(values),
        "n": size,
        "mean": mean_value,
        "sd": math.sqrt(sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)),
        "median": percentile_linear(values, 0.5),
        "ci_low": percentile_linear(values, 0.025),
        "ci_high": percentile_linear(values, 0.975),
    }


def paired_bootstrap(
    rows: list[PairedObservation],
    metric: str = "auroc",
    samples: int = 20000,
    seed: int = 20260925,
) -> dict:
    """Paired BCa cluster bootstrap, fully described (quantiles plus tail probabilities)."""
    from e4s_stats import _bca_interval

    observed, values, invalid = _bootstrap_engine(rows, metric, samples, seed)
    summary: dict = {
        "metric": metric,
        "observed": observed,
        "samples": samples,
        "valid_replicates": len(values),
        "invalid_replicates": invalid,
        "cluster_count": len(rows),
        "standard_error": None,
        "bias": None,
        "percentile_nearest_rank": [None, None],
        "percentile_linear": [None, None],
        "bca": None,
        "bca_low": None,
        "bca_high": None,
    }
    if not values:
        return summary
    mean_value = sum(values) / len(values)
    summary["standard_error"] = (
        math.sqrt(sum((value - mean_value) ** 2 for value in values) / (len(values) - 1))
        if len(values) > 1
        else None
    )
    summary["bias"] = mean_value - observed if observed is not None else None
    summary["percentile_nearest_rank"] = [
        percentile_nearest_rank(values, 0.025),
        percentile_nearest_rank(values, 0.975),
    ]
    summary["percentile_linear"] = [percentile_linear(values, 0.025), percentile_linear(values, 0.975)]
    bca = _bca_interval(rows, metric, observed, values)
    summary["bca"] = list(bca) if bca else None
    summary["bca_low"] = bca[0] if bca else None
    summary["bca_high"] = bca[1] if bca else None
    summary["median"] = percentile_linear(values, 0.5)
    summary["mean"] = mean_value
    summary["q025"] = percentile_linear(values, 0.025)
    summary["q25"] = percentile_linear(values, 0.25)
    summary["q75"] = percentile_linear(values, 0.75)
    summary["q975"] = percentile_linear(values, 0.975)
    for threshold in BOOTSTRAP_TAIL_THRESHOLDS:
        summary[f"P_delta_gt_{threshold}".replace(".", "p")] = (
            sum(1 for value in values if value > threshold) / len(values)
        )
    return summary


def paired_comparison(
    rows: list[PairedObservation],
    samples: int = 20000,
    seed: int = 20260925,
    label: str = "",
) -> dict:
    """Full paired inference for one prespecified comparison: DeLong + BCa + PR-AUC."""
    auroc_boot = paired_bootstrap(rows, "auroc", samples, seed)
    pr_boot = paired_bootstrap(rows, "pr_auc", samples, seed)
    delong = delong_paired(rows, "auroc")
    return {
        "label": label,
        "n_pairs": len(rows),
        "events": sum(row.label for row in rows),
        "reference_auroc": marginal_metric(rows, "reference", "auroc"),
        "challenger_auroc": marginal_metric(rows, "challenger", "auroc"),
        "reference_pr_auc": marginal_metric(rows, "reference", "pr_auc"),
        "challenger_pr_auc": marginal_metric(rows, "challenger", "pr_auc"),
        "delta_auroc": delta_metric(rows, "auroc"),
        "delta_pr_auc": delta_metric(rows, "pr_auc"),
        "delong": delong,
        "bootstrap_auroc": auroc_boot,
        "bootstrap_pr_auc": pr_boot,
    }


def holm_family(comparisons: list[dict]) -> list[dict]:
    """Holm-adjust the DeLong p-values of a prespecified primary family."""
    payload = [
        {"label": item["label"], "p_value": item["delong"].get("p_value")}
        for item in comparisons
    ]
    adjusted = holm_adjust(payload)
    for item, entry in zip(comparisons, adjusted, strict=True):
        item["holm_adjusted_p"] = entry.get("holm_adjusted_p")
    return comparisons


# --------------------------------------------------------------------------------------
# Threshold sweep (SENSITIVITY_ONLY)
# --------------------------------------------------------------------------------------


def threshold_sweep(labels: list[int], scores: list[float], grid: list[float]) -> list[dict]:
    """Operating characteristics on a prespecified threshold grid.

    This is a sensitivity description, not a threshold-selection exercise: the operational
    threshold shipped by FinRisk is not changed here.
    """
    total = len(labels)
    events = sum(labels)
    non_events = total - events
    rows = []
    for threshold in grid:
        tp = sum(1 for y, s in zip(labels, scores, strict=True) if s >= threshold and y == 1)
        fp = sum(1 for y, s in zip(labels, scores, strict=True) if s >= threshold and y == 0)
        fn = events - tp
        tn = non_events - fp
        predicted_positive = tp + fp
        precision = tp / predicted_positive if predicted_positive else None
        recall = tp / events if events else None
        specificity = tn / non_events if non_events else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
        rows.append(
            {
                "threshold": threshold,
                "predicted_positive": predicted_positive,
                "predicted_positive_rate": predicted_positive / total if total else None,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "recall": recall,
                "specificity": specificity,
                "precision": precision,
                "f1": f1,
                "fnr": (fn / events) if events else None,
                "review_load": predicted_positive / total if total else None,
            }
        )
    return rows


# --------------------------------------------------------------------------------------
# Descriptive calibration diagnostics (scores stay UNCALIBRATED)
# --------------------------------------------------------------------------------------


def _logit(value: float, epsilon: float = 1e-6) -> float:
    clipped = min(max(value, epsilon), 1.0 - epsilon)
    return math.log(clipped / (1.0 - clipped))


def calibration_diagnostics(labels: list[int], scores: list[float], bins: int = 10) -> dict:
    n = len(labels)
    if n == 0:
        return {"status": "EMPTY"}
    mean_score = sum(scores) / n
    event_rate = sum(labels) / n
    brier = sum((s - y) ** 2 for y, s in zip(labels, scores, strict=True)) / n

    # Equal-width bins over [0, 1]; the last bin is closed on the right.
    edges = [index / bins for index in range(bins + 1)]
    bin_rows = []
    ece = 0.0
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        members = [i for i, s in enumerate(scores) if (low <= s < high) or (index == bins - 1 and s == 1.0)]
        if not members:
            bin_rows.append(
                {"bin": index, "low": low, "high": high, "n": 0, "mean_score": None, "event_rate": None}
            )
            continue
        bin_mean = sum(scores[i] for i in members) / len(members)
        bin_rate = sum(labels[i] for i in members) / len(members)
        ece += (len(members) / n) * abs(bin_rate - bin_mean)
        bin_rows.append(
            {
                "bin": index,
                "low": low,
                "high": high,
                "n": len(members),
                "mean_score": bin_mean,
                "event_rate": bin_rate,
            }
        )

    # Calibration-in-the-large and slope, from a one-variable logistic fit of y on logit(s).
    logits = [_logit(s) for s in scores]
    intercept, slope = _logistic_fit(logits, labels)

    unique = sorted({round(float(s), 12) for s in scores})
    zero_mass = sum(1 for s in scores if s <= 0.0) / n
    one_mass = sum(1 for s in scores if s >= 1.0) / n
    return {
        "status": "UNCALIBRATED_DESCRIPTIVE",
        "n": n,
        "events": sum(labels),
        "brier": brier,
        "brier_skill_vs_prevalence": None,
        "mean_score": mean_score,
        "event_rate": event_rate,
        "citl_intercept": intercept,
        "calibration_slope": slope,
        "ece_bins": bins,
        "ece": ece,
        "unique_score_values": len(unique),
        "zero_mass": zero_mass,
        "one_mass": one_mass,
        "extreme_mass": zero_mass + one_mass,
        "bins": bin_rows,
        "note": (
            "Descriptive only. No calibration map was fitted; refitting a calibrator on this "
            "cohort and then reporting its performance here would be circular."
        ),
    }


def _logistic_fit(x: list[float], y: list[int], iterations: int = 200, rate: float = 0.5) -> tuple[float, float]:
    """Newton-free gradient fit of y ~ a + b*x; used only for descriptive diagnostics."""
    if len(set(y)) < 2:
        return float("nan"), float("nan")
    a, b = 0.0, 0.0
    n = len(x)
    for _ in range(iterations):
        ga = gb = 0.0
        for xi, yi in zip(x, y, strict=True):
            z = min(max(a + b * xi, -30.0), 30.0)
            p = 1.0 / (1.0 + math.exp(-z))
            ga += p - yi
            gb += (p - yi) * xi
        a -= rate * ga / n
        b -= rate * gb / n
    return a, b


# --------------------------------------------------------------------------------------
# Influence
# --------------------------------------------------------------------------------------


def leave_one_out_delta(rows: list[PairedObservation]) -> list[dict]:
    """Delete-one-observation ΔAUROC(challenger - reference)."""
    observed = delta_metric(rows, "auroc")
    out = []
    for index, row in enumerate(rows):
        reduced = rows[:index] + rows[index + 1 :]
        value = delta_metric(reduced, "auroc")
        out.append(
            {
                "observation_id": row.cluster_id,
                "label": row.label,
                "delta_without": value,
                "influence": (observed - value) if (value is not None and observed is not None) else None,
            }
        )
    return out


def leave_group_out_delta(rows: list[PairedObservation], groups: dict[str, str]) -> list[dict]:
    """Delete-one-group ΔAUROC, for the leave-sector-out robustness check."""
    observed = delta_metric(rows, "auroc")
    buckets: dict[str, list[PairedObservation]] = {}
    for row in rows:
        buckets.setdefault(groups.get(row.cluster_id, "UNKNOWN"), []).append(row)
    out = []
    for name, members in sorted(buckets.items()):
        removed = {row.cluster_id for row in members}
        reduced = [row for row in rows if row.cluster_id not in removed]
        value = delta_metric(reduced, "auroc")
        out.append(
            {
                "group": name,
                "removed_n": len(members),
                "removed_events": sum(row.label for row in members),
                "delta_without": value,
                "influence": (observed - value) if (value is not None and observed is not None) else None,
            }
        )
    return out


def describe_influence(entries: list[dict], key: str, observed: float) -> dict:
    values = [(item[key], item["influence"]) for item in entries if item["influence"] is not None]
    if not values:
        return {"status": "NOT_ESTIMABLE", "reason": "no valid delete-one estimates"}
    ordered = sorted(values, key=lambda pair: pair[1])
    influences = [value for _, value in values]
    return {
        "status": "OK",
        "observed_delta_auroc": observed,
        "n_units": len(values),
        "max_negative_influence": ordered[0][1],
        "max_negative_unit": ordered[0][0],
        "max_positive_influence": ordered[-1][1],
        "max_positive_unit": ordered[-1][0],
        "median_influence": percentile_linear(influences, 0.5),
        "min_delta_after_deletion": min(item["delta_without"] for item in entries if item["delta_without"] is not None),
        "max_delta_after_deletion": max(item["delta_without"] for item in entries if item["delta_without"] is not None),
        "deletions_flipping_sign": sum(
            1 for item in entries if item["delta_without"] is not None and item["delta_without"] <= 0
        ),
        "top_20_by_absolute_influence": [
            {key: unit, "influence": influence, "delta_without": next(
                item["delta_without"] for item in entries if item[key] == unit
            )}
            for unit, influence in sorted(values, key=lambda pair: abs(pair[1]), reverse=True)[:20]
        ],
    }


def normal_p_from_z(z: float) -> float:
    return 2.0 * (1.0 - normal_cdf(abs(z)))
