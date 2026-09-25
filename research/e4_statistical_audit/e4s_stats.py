"""Independent statistical primitives for the POST-E4 statistical audit (E4-S).

This module is deliberately self-contained and does **not** import the frozen E4
implementation. It re-implements every inference procedure from first principles so
that the audit can compare methods rather than merely re-run the original code.

Scope note
----------
E4's frozen prediction artifacts (``research/e4/_artifacts``) are not published, so the
original 674 paired observations cannot be re-derived. This module therefore supplies
the *machinery*; the audit report states explicitly which numbers are reproduced from
published sufficient statistics, which are surrogate reconstructions, and which are
method-calibration simulations.

Evidence labels used throughout:

``ORIGINAL_E4``
    A value copied from a frozen E4 artifact.
``POST_E4_STATISTICAL_AUDIT``
    A value produced by this audit, from published sufficient statistics or simulation.
``SURROGATE_RECONSTRUCTION``
    A value computed on data reconstructed to match published E4 summary statistics.
``NOT_INDEPENDENTLY_REPRODUCIBLE``
    A claim that cannot be re-derived from published artifacts.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

# --------------------------------------------------------------------------------------
# Normal distribution helpers (pure Python; no SciPy dependency)
# --------------------------------------------------------------------------------------


def normal_cdf(value: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def normal_quantile(probability: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |err| < 1.15e-9)."""
    if not 0.0 < probability < 1.0:
        if probability <= 0.0:
            return -math.inf
        if probability >= 1.0:
            return math.inf
        raise ValueError("probability must lie in [0, 1]")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    plow = 0.02425
    phigh = 1.0 - plow
    if probability < plow:
        q = math.sqrt(-2.0 * math.log(probability))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if probability > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - probability))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = probability - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
    )


# --------------------------------------------------------------------------------------
# Ranking metrics (must agree with the frozen E4 metric definitions)
# --------------------------------------------------------------------------------------


def midranks(values: Sequence[float]) -> list[float]:
    """Average ranks, ties share the mean of the ranks they span."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0 + 1.0
        for position in order[start:end]:
            ranks[position] = rank
        start = end
    return ranks


def roc_auc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    """Mann-Whitney AUROC with 0.5 credit for ties.

    Computed from midranks, which is algebraically identical to the brute-force
    ``wins / (n1 * n0)`` form used by the frozen E4 ``evaluation.roc_auc`` but runs in
    O(n log n) so that 20,000-replicate bootstraps stay tractable.
    """
    positives = [i for i, y in enumerate(labels) if y == 1]
    negatives = [i for i, y in enumerate(labels) if y == 0]
    n1, n0 = len(positives), len(negatives)
    if not n1 or not n0:
        return None
    ranks = midranks(scores)
    statistic = sum(ranks[i] for i in positives) - n1 * (n1 + 1) / 2.0
    return statistic / (n1 * n0)


def roc_auc_bruteforce(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    """Reference implementation used only to test :func:`roc_auc`."""
    positives = [s for y, s in zip(labels, scores, strict=True) if y == 1]
    negatives = [s for y, s in zip(labels, scores, strict=True) if y == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def average_precision(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    """Tie-grouped average precision (matches E4 ``evaluation.average_precision``)."""
    positives = sum(labels)
    if not positives:
        return None
    groups: dict[float, list[int]] = {}
    for score, label in zip(scores, labels, strict=True):
        entry = groups.setdefault(float(score), [0, 0])
        entry[0] += 1
        entry[1] += int(label)
    cumulative_tp = 0
    cumulative_total = 0
    total = 0.0
    for score in sorted(groups, reverse=True):
        size, group_positives = groups[score]
        cumulative_tp += group_positives
        cumulative_total += size
        total += (group_positives / positives) * (cumulative_tp / cumulative_total)
    return total


METRICS: dict[str, Callable[[Sequence[int], Sequence[float]], float | None]] = {
    "auroc": roc_auc,
    "pr_auc": average_precision,
}


# --------------------------------------------------------------------------------------
# Paired observation container
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PairedObservation:
    cluster_id: str
    label: int
    reference_score: float
    challenger_score: float


def paired_observations(rows: Iterable[dict[str, Any]]) -> list[PairedObservation]:
    """Build the paired container from raw row dicts.

    Rows must expose ``cluster_id``, ``label``, ``reference_score`` and
    ``challenger_score``. Duplicate clusters raise, because E4's company bootstrap
    silently collapses them into a dict and would drop observations.
    """
    seen: set[str] = set()
    output: list[PairedObservation] = []
    for row in rows:
        cluster = str(row["cluster_id"])
        if cluster in seen:
            raise ValueError(f"duplicate cluster {cluster!r}: paired inference requires one row per cluster")
        seen.add(cluster)
        output.append(
            PairedObservation(
                cluster_id=cluster,
                label=int(row["label"]),
                reference_score=float(row["reference_score"]),
                challenger_score=float(row["challenger_score"]),
            )
        )
    return output


def delta_metric(rows: Sequence[PairedObservation], metric: str = "auroc") -> float | None:
    """Observed challenger-minus-reference metric difference."""
    measure = METRICS[metric]
    labels = [row.label for row in rows]
    reference = measure(labels, [row.reference_score for row in rows])
    challenger = measure(labels, [row.challenger_score for row in rows])
    if reference is None or challenger is None:
        return None
    return challenger - reference


def marginal_metric(rows: Sequence[PairedObservation], side: str, metric: str = "auroc") -> float | None:
    key = "reference_score" if side == "reference" else "challenger_score"
    return METRICS[metric]([row.label for row in rows], [getattr(row, key) for row in rows])


# --------------------------------------------------------------------------------------
# Percentile conventions
# --------------------------------------------------------------------------------------


def percentile_nearest_rank(values: Sequence[float], probability: float) -> float | None:
    """E4's ``_percentile``: index = floor((n-1) * p), clamped. No interpolation."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * probability))]


def percentile_linear(values: Sequence[float], probability: float) -> float | None:
    """Standard linear-interpolation percentile (numpy's default convention)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


# --------------------------------------------------------------------------------------
# Cluster bootstrap
# --------------------------------------------------------------------------------------


@dataclass
class BootstrapResult:
    metric: str
    observed: float | None
    samples: int
    valid_replicates: int
    invalid_replicates: int
    cluster_count: int
    percentile_nearest_rank: tuple[float | None, float | None]
    percentile_linear: tuple[float | None, float | None]
    bca: tuple[float | None, float | None] | None
    standard_error: float | None
    bias: float | None
    replicate_values: list[float] = field(default_factory=list, repr=False)


def _resample(rows: Sequence[PairedObservation], rng: random.Random) -> list[PairedObservation]:
    return [rows[rng.randrange(len(rows))] for _ in range(len(rows))]


def cluster_bootstrap(
    rows: Sequence[PairedObservation],
    metric: str = "auroc",
    samples: int = 20000,
    seed: int = 20260925,
    with_bca: bool = True,
) -> BootstrapResult:
    """Company-cluster bootstrap of the paired metric difference.

    Resampling units are clusters (one observation per company in E4), which preserves
    the within-company dependence that a naive observation-level bootstrap would break.
    """
    observed = delta_metric(rows, metric)
    rng = random.Random(seed)
    values: list[float] = []
    invalid = 0
    for _ in range(samples):
        value = delta_metric(_resample(rows, rng), metric)
        if value is None:
            invalid += 1
        else:
            values.append(value)
    if not values:
        return BootstrapResult(metric, observed, samples, 0, invalid, len(rows), (None, None), (None, None), None, None, None)
    standard_error = math.sqrt(sum((v - mean(values)) ** 2 for v in values) / (len(values) - 1)) if len(values) > 1 else None
    bca = _bca_interval(rows, metric, observed, values) if with_bca else None
    return BootstrapResult(
        metric=metric,
        observed=observed,
        samples=samples,
        valid_replicates=len(values),
        invalid_replicates=invalid,
        cluster_count=len(rows),
        percentile_nearest_rank=(percentile_nearest_rank(values, 0.025), percentile_nearest_rank(values, 0.975)),
        percentile_linear=(percentile_linear(values, 0.025), percentile_linear(values, 0.975)),
        bca=bca,
        standard_error=standard_error,
        bias=(mean(values) - observed) if observed is not None else None,
        replicate_values=values,
    )


def _bca_interval(
    rows: Sequence[PairedObservation],
    metric: str,
    observed: float | None,
    values: Sequence[float],
    alpha: float = 0.05,
) -> tuple[float | None, float | None] | None:
    """Bias-corrected and accelerated (BCa) interval with a cluster jackknife.

    The acceleration constant uses the delete-one-cluster jackknife, which is the
    correct resampling unit for company-clustered data.
    """
    if observed is None or len(rows) < 3:
        return None
    below = sum(1 for v in values if v < observed)
    proportion = min(max(below / len(values), 1.0 / (len(values) + 1)), 1.0 - 1.0 / (len(values) + 1))
    z0 = normal_quantile(proportion)

    jackknife: list[float] = []
    for index in range(len(rows)):
        reduced = list(rows[:index]) + list(rows[index + 1 :])
        value = delta_metric(reduced, metric)
        if value is not None:
            jackknife.append(value)
    if len(jackknife) < 3:
        return None
    jack_mean = mean(jackknife)
    deviations = [jack_mean - value for value in jackknife]
    sum_squares = sum(d * d for d in deviations)
    if sum_squares == 0:
        acceleration = 0.0
    else:
        acceleration = sum(d**3 for d in deviations) / (6.0 * sum_squares**1.5)

    def adjusted(probability: float) -> float:
        inner = z0 + normal_quantile(probability)
        denominator = 1.0 - acceleration * inner
        if denominator == 0:
            return probability
        return normal_cdf(z0 + inner / denominator)

    low = adjusted(alpha / 2.0)
    high = adjusted(1.0 - alpha / 2.0)
    return (percentile_linear(values, low), percentile_linear(values, high))


# --------------------------------------------------------------------------------------
# DeLong test for two correlated ROC AUCs
# --------------------------------------------------------------------------------------


def _midrank(values: Sequence[float]) -> list[float]:
    return midranks(values)


def _delong_components(labels: Sequence[int], scores: Sequence[float]) -> tuple[float, list[float], list[float]]:
    """Return (auc, v01_for_positives, v10_for_negatives) using the fast midrank form."""
    positives = [i for i, y in enumerate(labels) if y == 1]
    negatives = [i for i, y in enumerate(labels) if y == 0]
    n1, n0 = len(positives), len(negatives)
    tx = _midrank([scores[i] for i in positives])
    ty = _midrank([scores[i] for i in negatives])
    tz = _midrank(scores)
    auc = (sum(tz[i] for i in positives) - n1 * (n1 + 1) / 2.0) / (n1 * n0)
    v01 = [(tz[i] - tx[k]) / n0 for k, i in enumerate(positives)]
    v10 = [1.0 - (tz[j] - ty[k]) / n1 for k, j in enumerate(negatives)]
    return auc, v01, v10


def _covariance(left: Sequence[float], right: Sequence[float]) -> float:
    n = len(left)
    if n < 2:
        return 0.0
    left_mean, right_mean = mean(left), mean(right)
    return sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True)) / (n - 1)


def delong_paired(
    rows: Sequence[PairedObservation],
    metric: str = "auroc",
) -> dict[str, Any]:
    """Paired DeLong test of H0: metric(challenger) = metric(reference).

    Implements DeLong, DeLong & Clarke-Pearson (1988) with the O(n log n) midrank
    formulation of Sun & Xu (2014). Only ``auroc`` is supported, because the
    DeLong covariance theory is specific to the AUC U-statistic.
    """
    if metric != "auroc":
        raise ValueError("DeLong is only defined for AUROC")
    labels = [row.label for row in rows]
    reference_scores = [row.reference_score for row in rows]
    challenger_scores = [row.challenger_score for row in rows]
    if len(set(labels)) < 2:
        return {"status": "SINGLE_CLASS", "p_value": None}

    auc_ref, v01_ref, v10_ref = _delong_components(labels, reference_scores)
    auc_chall, v01_chall, v10_chall = _delong_components(labels, challenger_scores)
    n1, n0 = len(v01_ref), len(v10_ref)

    s01_ref = _covariance(v01_ref, v01_ref)
    s10_ref = _covariance(v10_ref, v10_ref)
    s01_chall = _covariance(v01_chall, v01_chall)
    s10_chall = _covariance(v10_chall, v10_chall)
    s01_cross = _covariance(v01_ref, v01_chall)
    s10_cross = _covariance(v10_ref, v10_chall)

    var_ref = s01_ref / n1 + s10_ref / n0
    var_chall = s01_chall / n1 + s10_chall / n0
    covariance = s01_cross / n1 + s10_cross / n0
    variance_delta = var_ref + var_chall - 2.0 * covariance
    delta = auc_chall - auc_ref
    if variance_delta <= 0:
        z = math.inf if delta != 0 else 0.0
    else:
        z = delta / math.sqrt(variance_delta)
    p_value = 2.0 * (1.0 - normal_cdf(abs(z)))
    return {
        "status": "OK",
        "metric": "auroc",
        "auc_reference": auc_ref,
        "auc_challenger": auc_chall,
        "observed_delta": delta,
        "variance_reference": var_ref,
        "variance_challenger": var_chall,
        "covariance": covariance,
        "variance_delta": variance_delta,
        "standard_error_delta": math.sqrt(variance_delta) if variance_delta > 0 else None,
        "z": z,
        "p_value": p_value,
        "z_ci_low": delta - 1.959963984540054 * math.sqrt(variance_delta) if variance_delta > 0 else None,
        "z_ci_high": delta + 1.959963984540054 * math.sqrt(variance_delta) if variance_delta > 0 else None,
        "n_pairs": len(rows),
        "events": sum(labels),
        "test": "delong_1988_paired",
    }


# --------------------------------------------------------------------------------------
# Permutation procedures
# --------------------------------------------------------------------------------------


def label_permutation_as_implemented(
    rows: Sequence[PairedObservation],
    metric: str = "auroc",
    samples: int = 2000,
    seed: int = 20260924,
) -> dict[str, Any]:
    """Faithful re-implementation of E4 ``e4_evaluation.paired_permutation``.

    The outcome labels are shuffled **across observations** while the
    ``(reference_score, challenger_score)`` pair attached to each observation stays
    fixed. The resulting reference distribution is the distribution of the metric
    difference when the outcome carries no information about *either* score.
    """
    measure = METRICS[metric]
    labels = [row.label for row in rows]
    reference = [row.reference_score for row in rows]
    challenger = [row.challenger_score for row in rows]
    observed = delta_metric(rows, metric)
    if observed is None:
        return {"p_value": None, "valid_permutations": 0, "test": "label_permutation_as_implemented"}
    rng = random.Random(seed)
    null: list[float] = []
    for _ in range(samples):
        shuffled = list(labels)
        rng.shuffle(shuffled)
        left = measure(shuffled, reference)
        right = measure(shuffled, challenger)
        if left is not None and right is not None:
            null.append(right - left)
    if not null:
        return {"p_value": None, "valid_permutations": 0, "test": "label_permutation_as_implemented"}
    p_value = (1 + sum(abs(v) >= abs(observed) for v in null)) / (len(null) + 1)
    return {
        "test": "label_permutation_as_implemented",
        "observed_delta": observed,
        "p_value": p_value,
        "valid_permutations": len(null),
        "null_ci_nearest_rank": (percentile_nearest_rank(null, 0.025), percentile_nearest_rank(null, 0.975)),
        "null_ci_linear": (percentile_linear(null, 0.025), percentile_linear(null, 0.975)),
        "null_standard_deviation": math.sqrt(sum((v - mean(null)) ** 2 for v in null) / (len(null) - 1)) if len(null) > 1 else None,
        "null_mean": mean(null),
        "p_value_floor": 1.0 / (len(null) + 1),
        "at_p_value_floor": p_value <= 1.0 / (len(null) + 1) + 1e-12,
    }


def score_swap_randomization(
    rows: Sequence[PairedObservation],
    metric: str = "auroc",
    samples: int = 20000,
    seed: int = 20260925,
) -> dict[str, Any]:
    """Within-observation score-swap randomization test.

    Under the exchangeability null ``H0_exch`` the two score vectors are exchangeable
    given the outcome, which implies equal AUROCs (``H0_exch`` => ``H0_equality``).
    Rejecting ``H0_exch`` therefore *does* transfer to rejecting ``H0_equality``, which
    is what makes this a valid (conservative) permutation design for the equality
    hypothesis, unlike the label-shuffling design.
    """
    measure = METRICS[metric]
    labels = [row.label for row in rows]
    observed = delta_metric(rows, metric)
    if observed is None:
        return {"p_value": None, "valid_permutations": 0, "test": "score_swap_randomization"}
    rng = random.Random(seed)
    null: list[float] = []
    for _ in range(samples):
        first: list[float] = []
        second: list[float] = []
        for row in rows:
            if rng.random() < 0.5:
                first.append(row.reference_score)
                second.append(row.challenger_score)
            else:
                first.append(row.challenger_score)
                second.append(row.reference_score)
        left = measure(labels, first)
        right = measure(labels, second)
        if left is not None and right is not None:
            null.append(right - left)
    if not null:
        return {"p_value": None, "valid_permutations": 0, "test": "score_swap_randomization"}
    p_value = (1 + sum(abs(v) >= abs(observed) for v in null)) / (len(null) + 1)
    return {
        "test": "score_swap_randomization",
        "observed_delta": observed,
        "p_value": p_value,
        "valid_permutations": len(null),
        "null_ci_linear": (percentile_linear(null, 0.025), percentile_linear(null, 0.975)),
        "null_standard_deviation": math.sqrt(sum((v - mean(null)) ** 2 for v in null) / (len(null) - 1)) if len(null) > 1 else None,
        "null_mean": mean(null),
        "null_hypothesis": "H0_exch: the two score vectors are exchangeable given the outcome (implies equal AUROC)",
    }


def holm_adjust(tests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Holm step-down adjustment, matching E4's procedure."""
    indexed = [(i, item["p_value"]) for i, item in enumerate(tests) if item.get("p_value") is not None]
    ordered = sorted(indexed, key=lambda pair: pair[1])
    adjusted: dict[int, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, (index, value) in enumerate(ordered):
        running = max(running, min(1.0, (count - rank) * float(value)))
        adjusted[index] = running
    return [{**item, "holm_adjusted_p": adjusted.get(i)} for i, item in enumerate(tests)]
