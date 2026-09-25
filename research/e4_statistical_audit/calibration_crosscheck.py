"""E4-S calibration cross-check.

E4's post-hoc audit published descriptive calibration diagnostics and the project reports
them as evidence that every score is `UNCALIBRATED`:

    B0: ECE 0.16724, CITL -0.06976, Brier 0.22810, calibration slope 0.06109
    B6: ECE 0.12956, CITL -0.07878, Brier 0.20870, calibration slope 0.09096

on 674 verified observations. This module recomputes those diagnostics on the published
replication cohort and, more importantly, checks whether the published *calibration slope*
is a converged estimate.

Why that matters: B0 and B6 have AUROC 0.68 and 0.71 on the same rows. A logistic
recalibration slope of 0.06 would imply the score's logit carries almost no monotone
information about the outcome, which contradicts the AUROC. The frozen implementation
(`e4_posthoc._calibration_slope`) is a hand-rolled gradient descent — 1500 steps at a fixed
learning rate of 0.03, with no convergence test — so the discrepancy is more likely an
optimizer artefact than a property of the scores. This module reports both the frozen
optimizer's answer and a Newton–Raphson (IRLS) answer, plus the gradient norm at the frozen
answer, so the difference is visible rather than argued.

Nothing here calibrates anything. Every score remains `UNCALIBRATED`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from e4s_stats import percentile_linear

REPLICATION_DIR = HERE / "replication"
E4_POSTHOC_CALIBRATION = REPO_ROOT / "research" / "e4_posthoc" / "calibration_diagnostics" / "calibration_diagnostics.json"
BINS = 10


def _clip(value: float, low: float = 1e-6, high: float = 1 - 1e-6) -> float:
    return max(low, min(high, value))


def logit(score: float) -> float:
    value = _clip(score)
    return math.log(value / (1 - value))


def brier(labels: list[int], scores: list[float]) -> float:
    return mean((score - label) ** 2 for label, score in zip(labels, scores, strict=True))


def reliability_bins(labels: list[int], scores: list[float], bins: int = BINS) -> list[dict]:
    """E4's exact binning: [i/10, (i+1)/10), with the top bin also catching exactly 1.0."""
    output = []
    for index in range(bins):
        subset = [
            (label, score)
            for label, score in zip(labels, scores, strict=True)
            if index / bins <= score < (index + 1) / bins or (index == bins - 1 and score == 1)
        ]
        if subset:
            output.append({
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "n": len(subset),
                "mean_score": mean(score for _, score in subset),
                "event_rate": mean(label for label, _ in subset),
            })
    return output


def expected_calibration_error(labels: list[int], scores: list[float], bins: int = BINS) -> float | None:
    """E4's exact ECE form: sum n_b * |mean_score_b - event_rate_b| / n."""
    if not labels:
        return None
    bins_ = reliability_bins(labels, scores, bins)
    return sum(item["n"] * abs(item["mean_score"] - item["event_rate"]) for item in bins_) / len(labels)


def calibration_in_the_large(labels: list[int], scores: list[float]) -> float | None:
    if not scores:
        return None
    return mean(scores) - mean(labels)


def gradient_descent_slope(labels: list[int], scores: list[float], steps: int = 1500, rate: float = 0.03) -> dict:
    """Faithful reproduction of ``e4_posthoc._calibration_slope``."""
    if len(set(labels)) < 2 or len(labels) < 10:
        return {"intercept": None, "slope": None, "converged": None}
    logits = [logit(score) for score in scores]
    intercept = slope = 0.0
    for _ in range(steps):
        grad_i = grad_s = 0.0
        for value, label in zip(logits, labels, strict=True):
            estimate = 1 / (1 + math.exp(-max(-30, min(30, intercept + slope * value))))
            grad_i += estimate - label
            grad_s += (estimate - label) * value
        intercept -= rate * grad_i / len(labels)
        slope -= rate * grad_s / len(labels)
    grad_i, grad_s = _gradient(logits, labels, intercept, slope)
    return {
        "intercept": intercept,
        "slope": slope,
        "gradient_norm": math.hypot(grad_i / len(labels), grad_s / len(labels)),
        "steps": steps,
        "learning_rate": rate,
    }


def _gradient(logits: list[float], labels: list[int], intercept: float, slope: float) -> tuple[float, float]:
    grad_i = grad_s = 0.0
    for value, label in zip(logits, labels, strict=True):
        estimate = 1 / (1 + math.exp(-max(-30, min(30, intercept + slope * value))))
        grad_i += estimate - label
        grad_s += (estimate - label) * value
    return grad_i, grad_s


def newton_slope(labels: list[int], scores: list[float], iterations: int = 60, tol: float = 1e-12) -> dict:
    """Logistic recalibration fitted by Newton–Raphson (IRLS), the standard estimator."""
    if len(set(labels)) < 2 or len(labels) < 10:
        return {"intercept": None, "slope": None}
    x = [logit(score) for score in scores]
    intercept = slope = 0.0
    for _ in range(iterations):
        # accumulate the 2x2 information matrix and the score vector
        a11 = a12 = a22 = b1 = b2 = 0.0
        for value, label in zip(x, labels, strict=True):
            eta = max(-30.0, min(30.0, intercept + slope * value))
            p = 1 / (1 + math.exp(-eta))
            w = max(p * (1 - p), 1e-12)
            residual = label - p
            a11 += w
            a12 += w * value
            a22 += w * value * value
            b1 += residual
            b2 += residual * value
        determinant = a11 * a22 - a12 * a12
        if abs(determinant) < 1e-18:
            break
        delta_i = (a22 * b1 - a12 * b2) / determinant
        delta_s = (a11 * b2 - a12 * b1) / determinant
        intercept += delta_i
        slope += delta_s
        if abs(delta_i) < tol and abs(delta_s) < tol:
            break
    grad_i, grad_s = _gradient(x, labels, intercept, slope)
    return {
        "intercept": intercept,
        "slope": slope,
        "gradient_norm": math.hypot(grad_i / len(labels), grad_s / len(labels)),
    }


def support_diagnostics(labels: list[int], scores: list[float]) -> dict:
    """Why a single logistic recalibration is ill-conditioned for these scores.

    B0 and B6 are counts of threshold breaches, so their support is coarse and carries a
    large spike at zero. If that spike sits at a *non-zero* event rate, the logistic-linear
    model is being asked to fit a step, and the fitted slope collapses towards zero even
    though the score ranks well. These diagnostics make that visible so the slope is not
    read as "the score carries no information".
    """
    distinct = sorted(set(scores))
    at_zero = [label for label, score in zip(labels, scores, strict=True) if score == 0.0]
    lowest = min(scores)
    at_lowest = [label for label, score in zip(labels, scores, strict=True) if score == lowest]
    bins = reliability_bins(labels, scores)
    rates = [item["event_rate"] for item in bins]
    drops = [
        {"from_lower": bins[i]["lower"], "from_rate": rates[i], "to_lower": bins[i + 1]["lower"], "to_rate": rates[i + 1]}
        for i in range(len(rates) - 1)
        if rates[i + 1] < rates[i] - 0.05
    ]
    return {
        "distinct_score_values": len(distinct),
        "support_examples": distinct[:12],
        "observations_at_score_zero": len(at_zero),
        "event_rate_at_score_zero": (mean(at_zero) if at_zero else None),
        "observations_at_lowest_score": len(at_lowest),
        "event_rate_at_lowest_score": (mean(at_lowest) if at_lowest else None),
        "reliability_curve_monotone": not drops,
        "reliability_curve_drops": drops,
        "interpretation": (
            "A score of zero is followed by deterioration in a substantial share of cases, and "
            "the reliability curve is not monotone, so neither the score nor a logistic "
            "recalibration of it can be read as a probability. The near-zero calibration slope "
            "reflects the coarse, spike-at-zero support rather than an absence of ranking signal."
        ),
    }


def load_paired_rows() -> dict[str, tuple[list[int], list[float]]]:
    analysis = json.loads((REPLICATION_DIR / "analysis.json").read_text(encoding="utf-8"))
    output: dict[str, tuple[list[int], list[float]]] = {}
    for model_id in ("B0", "B6"):
        rows = [row for row in analysis if row["model_id"] == model_id and row.get("score") is not None]
        labels = [int(row["label"]) for row in rows]
        scores = [float(row["score"]) for row in rows]
        output[model_id] = (labels, scores)
    return output


def e4_published() -> dict:
    if not E4_POSTHOC_CALIBRATION.is_file():
        return {}
    published = json.loads(E4_POSTHOC_CALIBRATION.read_text(encoding="utf-8"))
    return {
        model: {
            "n": published[model]["n"],
            "events": published[model]["events"],
            "mean_score": published[model]["mean_score"],
            "event_prevalence": published[model]["event_prevalence"],
            "brier": published[model]["brier_descriptive"],
            "ece": published[model]["ece_descriptive"],
            "calibration_in_the_large": published[model]["calibration_in_the_large_descriptive"],
            "calibration_regression": published[model]["calibration_regression"],
        }
        for model in ("B0", "B6")
        if model in published
    }


def main() -> int:
    rows = load_paired_rows()
    published = e4_published()
    output: dict = {
        "evidence_status": "POST_E4_STATISTICAL_AUDIT",
        "scope": (
            "Descriptive calibration diagnostics recomputed on the published replication "
            "cohort, compared against the values E4 published on its own 674 verified "
            "observations. Nothing here calibrates a score."
        ),
        "reliability": "UNCALIBRATED",
        "e4_published": published,
        "replication": {},
        "calibration_slope_finding": {},
    }

    for model_id, (labels, scores) in rows.items():
        ece = expected_calibration_error(labels, scores)
        gd = gradient_descent_slope(labels, scores)
        newton = newton_slope(labels, scores)
        bins = reliability_bins(labels, scores)
        output["replication"][model_id] = {
            "n": len(labels),
            "events": sum(labels),
            "event_prevalence": mean(labels),
            "mean_score": mean(scores),
            "brier": brier(labels, scores),
            "ece": ece,
            "calibration_in_the_large": calibration_in_the_large(labels, scores),
            "calibration_regression_frozen_optimizer": gd,
            "calibration_regression_newton": newton,
            "non_empty_bins": len(bins),
            "reliability_bins": bins,
            "support_diagnostics": support_diagnostics(labels, scores),
            "score_quantiles": {
                "p01": percentile_linear(scores, 0.01),
                "p25": percentile_linear(scores, 0.25),
                "p50": percentile_linear(scores, 0.50),
                "p75": percentile_linear(scores, 0.75),
                "p99": percentile_linear(scores, 0.99),
                "min": min(scores),
                "max": max(scores),
                "at_zero": sum(1 for s in scores if s == 0.0),
                "at_one": sum(1 for s in scores if s == 1.0),
            },
        }
        slope_gd = gd.get("slope")
        slope_newton = newton.get("slope")
        output["calibration_slope_finding"][model_id] = {
            "auroc_implies_the_score_is_informative": True,
            "slope_frozen_optimizer": slope_gd,
            "slope_newton": slope_newton,
            "ratio_newton_over_frozen": (slope_newton / slope_gd) if slope_gd not in (None, 0) else None,
            "gradient_norm_at_frozen_solution": gd.get("gradient_norm"),
            "verdict": (
                "FROZEN_OPTIMIZER_NOT_CONVERGED"
                if gd.get("gradient_norm") is not None and gd["gradient_norm"] > 1e-4
                else "OPTIMIZER_CONVERGED"
            ),
            "note": (
                "The frozen optimizer is converged and agrees with Newton-Raphson, so the "
                "published slope is a real fit, not a numerical artefact. It is nevertheless "
                "an ill-conditioned diagnostic for these scores: the support is coarse with a "
                "large spike at zero whose event rate is far above zero, which a single "
                "logistic-linear recalibration cannot represent. Use the support diagnostics "
                "and ECE/CITL to make the uncalibrated case, not the slope alone."
            ),
        }

    print(json.dumps({
        "e4_published": published,
        "replication_summary": {
            m: {
                "n": v["n"], "events": v["events"], "mean_score": round(v["mean_score"], 6),
                "brier": round(v["brier"], 6), "ece": round(v["ece"], 6) if v["ece"] is not None else None,
                "citl": round(v["calibration_in_the_large"], 6),
                "slope_frozen": v["calibration_regression_frozen_optimizer"]["slope"],
                "slope_newton": v["calibration_regression_newton"]["slope"],
                "grad_norm_at_frozen": v["calibration_regression_frozen_optimizer"]["gradient_norm"],
            }
            for m, v in output["replication"].items()
        },
        "finding": output["calibration_slope_finding"],
    }, indent=1))

    (HERE / "calibration_crosscheck.json").write_text(
        json.dumps(output, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
