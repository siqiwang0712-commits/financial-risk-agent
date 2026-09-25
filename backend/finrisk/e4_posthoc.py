"""Deterministic post-E4 diagnostics that never mutate frozen E4 artifacts."""

from __future__ import annotations

import csv
import gzip
import hashlib
import math
import subprocess
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median
from typing import Any

from .e4_core import canonical_hash, read_json, sha256_file, write_json
from .e4_evaluation import CONCORDANCE_MAP, performance, spearman
from .evaluation import brier_score, roc_auc

SEED = 20260925
STATUS_ORDER = ("VERIFIED", "REQUIRES_HUMAN_REVIEW", "INSUFFICIENT_DATA")


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(len(ordered) - 1, low + 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def _safe_log(value: float | None) -> float | None:
    if value is None:
        return None
    return math.copysign(math.log1p(abs(float(value))), float(value))


def _raw_diagnostics(
    features: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    status = {row["observation_id"]: row["label_status"] for row in labels}
    scores = {
        (row["observation_id"], row["model_id"]): row.get("score")
        for row in predictions
        if row["model_id"] in {"B0", "B6"}
    }
    origin = date(2024, 7, 1)
    output = []
    for row in features:
        current = row["current"]
        metrics = row["metrics"]
        all_values = [*current.values(), *metrics.values()]
        revenue = current.get("revenue")
        ocf = current.get("operating_cash_flow")
        output.append({
            "observation_id": row["observation_id"],
            "status": status[row["observation_id"]],
            "sector": row["sector"],
            "log_assets": _safe_log(current.get("total_assets")),
            "log_revenue": _safe_log(revenue),
            "leverage": metrics.get("debt_to_assets"),
            "profitability": metrics.get("net_margin"),
            "ocf_margin": None if revenue in {None, 0} or ocf is None else float(ocf) / abs(float(revenue)),
            "missingness": sum(value is None for value in all_values) / len(all_values),
            "filing_timing_days": (date.fromisoformat(row["filing_date"]) - origin).days,
            "fact_count": sum(value is not None for value in row["provenance"].values()),
            "B0": scores[(row["observation_id"], "B0")],
            "B6": scores[(row["observation_id"], "B6")],
        })
    return output


def _ks(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    values = sorted(set(left + right))
    return max(
        abs(sum(item <= value for item in left) / len(left) - sum(item <= value for item in right) / len(right))
        for value in values
    )


def _smd(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    left_mean, right_mean = mean(left), mean(right)
    left_var = mean((value - left_mean) ** 2 for value in left)
    right_var = mean((value - right_mean) ** 2 for value in right)
    pooled = math.sqrt((left_var + right_var) / 2)
    return (left_mean - right_mean) / pooled if pooled else 0.0


def _group_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = (
        "log_assets", "log_revenue", "leverage", "profitability", "ocf_margin",
        "missingness", "filing_timing_days", "fact_count", "B0", "B6",
    )
    summaries: dict[str, Any] = {}
    for status in STATUS_ORDER:
        group = [row for row in rows if row["status"] == status]
        summaries[status] = {
            "n": len(group),
            "sector_counts": dict(sorted(Counter(row["sector"] for row in group).items())),
            "variables": {},
        }
        for name in numeric:
            values = [float(row[name]) for row in group if row[name] is not None]
            summaries[status]["variables"][name] = {
                "observed": len(values),
                "missing_rate": 1 - len(values) / len(group),
                "mean": mean(values) if values else None,
                "median": median(values) if values else None,
            }
    contrasts = []
    verified = [row for row in rows if row["status"] == "VERIFIED"]
    for other_status in STATUS_ORDER[1:]:
        other = [row for row in rows if row["status"] == other_status]
        for name in numeric:
            left = [float(row[name]) for row in verified if row[name] is not None]
            right = [float(row[name]) for row in other if row[name] is not None]
            contrasts.append({
                "contrast": f"VERIFIED_vs_{other_status}",
                "variable": name,
                "smd": _smd(left, right),
                "ks": _ks(left, right),
            })
    return {"groups": summaries, "contrasts": contrasts}


class _Logistic:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.means: list[float] = []
        self.scales: list[float] = []
        self.weights: list[float] = []

    @staticmethod
    def _dict(row: dict[str, Any]) -> dict[str, float | None]:
        values: dict[str, float | None] = {
            name: row[name]
            for name in (
                "log_assets", "log_revenue", "leverage", "profitability", "ocf_margin",
                "missingness", "filing_timing_days", "fact_count", "B0", "B6",
            )
        }
        for sector in (
            "Construction", "Manufacturing", "Mining", "Other_Nonfinancial", "Retail",
            "Services", "Transportation_Utilities", "Wholesale",
        ):
            values[f"sector_{sector}"] = float(row["sector"] == sector)
        for name in tuple(values):
            values[f"missing_{name}"] = float(values[name] is None)
        return values

    def _matrix(self, rows: list[dict[str, Any]], fit: bool) -> list[list[float]]:
        values = [self._dict(row) for row in rows]
        if fit:
            self.names = sorted({name for value in values for name in value})
            self.means, self.scales = [], []
            for name in self.names:
                observed = [float(value[name]) for value in values if value.get(name) is not None]
                center = mean(observed) if observed else 0.0
                scale = math.sqrt(mean((item - center) ** 2 for item in observed)) if observed else 1.0
                self.means.append(center)
                self.scales.append(scale or 1.0)
        matrix = []
        for value in values:
            matrix.append([1.0] + [
                ((self.means[index] if value.get(name) is None else float(value[name])) - self.means[index]) / self.scales[index]
                for index, name in enumerate(self.names)
            ])
        return matrix

    def fit(self, rows: list[dict[str, Any]], labels: list[int]) -> None:
        matrix = self._matrix(rows, True)
        self.weights = [0.0] * len(matrix[0])
        for _ in range(1200):
            gradient = [0.0] * len(self.weights)
            for vector, label in zip(matrix, labels, strict=True):
                linear = max(-30.0, min(30.0, sum(a * b for a, b in zip(self.weights, vector, strict=True))))
                estimate = 1 / (1 + math.exp(-linear))
                for index, item in enumerate(vector):
                    gradient[index] += (estimate - label) * item
            for index in range(len(self.weights)):
                penalty = 0.0 if index == 0 else 0.01 * self.weights[index]
                self.weights[index] -= 0.05 * (gradient[index] / len(matrix) + penalty)

    def predict(self, rows: list[dict[str, Any]]) -> list[float]:
        matrix = self._matrix(rows, False)
        return [
            1 / (1 + math.exp(-max(-30.0, min(30.0, sum(a * b for a, b in zip(self.weights, vector, strict=True))))))
            for vector in matrix
        ]


def _weighted_auc(labels: list[int], scores: list[float], weights: list[float]) -> float | None:
    positive = sum(weight for label, weight in zip(labels, weights, strict=True) if label == 1)
    negative = sum(weight for label, weight in zip(labels, weights, strict=True) if label == 0)
    if not positive or not negative:
        return None
    total = 0.0
    for left_label, left_score, left_weight in zip(labels, scores, weights, strict=True):
        if left_label != 1:
            continue
        for right_label, right_score, right_weight in zip(labels, scores, weights, strict=True):
            if right_label != 0:
                continue
            total += left_weight * right_weight * (1.0 if left_score > right_score else 0.5 if left_score == right_score else 0.0)
    return total / (positive * negative)


def verification_bias(
    features: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = _raw_diagnostics(features, outcomes, predictions)
    estimates: dict[str, float] = {}
    for fold in range(5):
        held = [row for row in rows if int(hashlib.sha256(row["observation_id"].encode()).hexdigest(), 16) % 5 == fold]
        train = [row for row in rows if row not in held]
        model = _Logistic()
        model.fit(train, [int(row["status"] == "VERIFIED") for row in train])
        estimates.update(zip((row["observation_id"] for row in held), model.predict(held), strict=True))
    labels = [int(row["status"] == "VERIFIED") for row in rows]
    propensity = [estimates[row["observation_id"]] for row in rows]
    prevalence = mean(labels)
    outcome_by_id = {row["observation_id"]: row for row in outcomes}
    pred = {(row["observation_id"], row["model_id"]): row for row in predictions if row["model_id"] in {"B0", "B6"}}
    verified = [row for row in rows if row["status"] == "VERIFIED"]
    raw_weights = [prevalence / max(0.01, min(0.99, estimates[row["observation_id"]])) for row in verified]
    sensitivities = []
    for name, cap in (("untruncated", None), ("cap_10", 10.0), ("cap_5", 5.0), ("p99", percentile(raw_weights, 0.99)), ("p95", percentile(raw_weights, 0.95))):
        weights = [weight if cap is None else min(weight, float(cap)) for weight in raw_weights]
        binary = [int(outcome_by_id[row["observation_id"]]["financial_deterioration_12m"]) for row in verified]
        b0 = [float(pred[(row["observation_id"], "B0")]["score"]) for row in verified]
        b6 = [float(pred[(row["observation_id"], "B6")]["score"]) for row in verified]
        b0_auc, b6_auc = _weighted_auc(binary, b0, weights), _weighted_auc(binary, b6, weights)
        sensitivities.append({
            "scheme": name,
            "cap": cap,
            "effective_sample_size": sum(weights) ** 2 / sum(weight**2 for weight in weights),
            "weighted_event_prevalence": sum(w * y for w, y in zip(weights, binary, strict=True)) / sum(weights),
            "B0_weighted_auroc": b0_auc,
            "B6_weighted_auroc": b6_auc,
            "delta_weighted_auroc": None if b0_auc is None or b6_auc is None else b6_auc - b0_auc,
        })
    return {
        "interpretation": "Verification weighting is sensitivity analysis only; MAR is not established and missing outcomes are not imputed.",
        "prediction_time_group_diagnostics": _group_diagnostics(rows),
        "propensity_model": {
            "method": "deterministic 5-fold cross-fitted logistic regression",
            "features": "sector, assets, revenue, leverage, profitability, OCF margin, missingness, filing timing, fact count, B0, B6; prediction-time only",
            "verification_prevalence": prevalence,
            "auroc": roc_auc(labels, propensity),
            "propensity_distribution": {key: percentile(propensity, value) for key, value in (("p01", 0.01), ("p05", 0.05), ("median", 0.5), ("p95", 0.95), ("p99", 0.99))},
        },
        "verified_weight_distribution": {
            "min": min(raw_weights), "median": median(raw_weights), "mean": mean(raw_weights),
            "p90": percentile(raw_weights, 0.90), "p95": percentile(raw_weights, 0.95),
            "p99": percentile(raw_weights, 0.99), "max": max(raw_weights),
        },
        "weighted_sensitivity": sensitivities,
    }


def agent_power_funnel(
    feature_report: dict[str, Any], outcomes: list[dict[str, Any]], agent: list[dict[str, Any]]
) -> dict[str, Any]:
    selected = set(feature_report["e4b_ids"])
    labels = {row["observation_id"]: row for row in outcomes}
    by_model = {model: [row for row in agent if row["model_id"] == model] for model in ("A0", "A1", "A2")}
    endpoint_verified = {item for item in selected if labels[item]["label_status"] == "VERIFIED"}
    valid_a2 = {row["observation_id"] for row in by_model["A2"] if row.get("score") is not None}
    paired = endpoint_verified & valid_a2
    return {
        "selected_companies": len(selected),
        "packet_available": {model: len(rows) for model, rows in by_model.items()},
        "agent_callable": {model: len(rows) for model, rows in by_model.items()},
        "valid_schema": {model: sum(row.get("score") is not None for row in rows) for model, rows in by_model.items()},
        "agent_schema_failures": {model: sum(row.get("score") is None for row in rows) for model, rows in by_model.items()},
        "endpoint_verified": len(endpoint_verified),
        "endpoint_attrition": len(selected - endpoint_verified),
        "a2_failures_among_verified": len(endpoint_verified - valid_a2),
        "paired_observations": len(paired),
        "paired_positive_events": sum(int(labels[item]["financial_deterioration_12m"]) for item in paired),
        "decomposition": {
            "selection_to_endpoint_loss": len(selected - endpoint_verified),
            "verified_to_schema_loss": len(endpoint_verified - valid_a2),
            "comparison_intersection_additional_loss": 0,
        },
        "inference": "P2/P3 are exploratory: five paired positive events are below the frozen inference gate.",
    }


def _kendall(left: list[float], right: list[float]) -> float | None:
    concordant = discordant = 0
    for i in range(len(left)):
        for j in range(i + 1, len(left)):
            product = (left[i] - left[j]) * (right[i] - right[j])
            concordant += product > 0
            discordant += product < 0
    return (concordant - discordant) / (concordant + discordant) if concordant + discordant else None


def batch_sensitivity(
    summary: dict[str, Any],
    outcomes: list[dict[str, Any]],
    features: list[dict[str, Any]],
    size_two: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    labels = {row["observation_id"]: row for row in outcomes}
    feature_map = {row["observation_id"]: row for row in features}
    pairs = summary["pairs"]
    deltas = [float(row["absolute_difference"]) for row in pairs]
    batch_scores = [float(row["batched_score"]) for row in pairs]
    single_scores = [float(row["single_score"]) for row in pairs]
    valid = [row for row in pairs if labels[row["observation_id"]]["label_status"] == "VERIFIED"]
    by_model = {}
    for model in ("A0", "A1", "A2"):
        subset = [row for row in valid if row["model_id"] == model]
        binary = [int(labels[row["observation_id"]]["financial_deterioration_12m"]) for row in subset]
        if len(set(binary)) == 2:
            batch_auc = roc_auc(binary, [float(row["batched_score"]) for row in subset])
            single_auc = roc_auc(binary, [float(row["single_score"]) for row in subset])
        else:
            batch_auc = single_auc = None
        by_model[model] = {
            "n_verified": len(subset), "events": sum(binary), "batch_auroc": batch_auc,
            "single_auroc": single_auc,
            "delta_single_minus_batch": None if batch_auc is None else single_auc - batch_auc,
        }
    high = sorted(pairs, key=lambda row: row["absolute_difference"], reverse=True)[:5]
    result = {
        "n_pairs": len(pairs),
        "absolute_score_difference": {
            "median": median(deltas), "mean": mean(deltas), "p90": percentile(deltas, 0.90),
            "p95": percentile(deltas, 0.95), "max": max(deltas),
        },
        "spearman": spearman(batch_scores, single_scores),
        "kendall_tau_a": _kendall(batch_scores, single_scores),
        "decision_agreement": summary["decision_agreement"],
        "threshold_flips": [row for row in pairs if (row["single_score"] >= 0.5) != (row["batched_score"] >= 0.5)],
        "verified_predictive_sensitivity": by_model,
        "high_sensitivity_characteristics": [{
            "model_id": row["model_id"],
            "absolute_difference": row["absolute_difference"],
            "sector": feature_map[row["observation_id"]]["sector"],
            "missingness": sum(value is None for value in feature_map[row["observation_id"]]["current"].values()) / len(feature_map[row["observation_id"]]["current"]),
        } for row in high],
        "interpretation": "High binary agreement does not establish stable continuous ranking; all batch-size analyses are post-hoc.",
    }
    if size_two is not None:
        original = {(row["observation_id"], row["model_id"]): row for row in pairs}
        single = {(row["observation_id"], row["model_id"]): float(row["single_score"]) for row in pairs}
        comparisons = []
        for row in size_two:
            key = (row["observation_id"], row["model_id"])
            if row.get("score") is None or key not in original:
                continue
            comparisons.append({
                "model_id": row["model_id"],
                "absolute_delta_vs_single": abs(float(row["score"]) - single[key]),
                "absolute_delta_vs_original_batch": abs(float(row["score"]) - float(original[key]["batched_score"])),
                "decision_matches_single": int(float(row["score"]) >= 0.5) == int(single[key] >= 0.5),
                "decision_matches_original_batch": int(float(row["score"]) >= 0.5) == int(float(original[key]["batched_score"]) >= 0.5),
            })
        result["batch_size_2"] = {
            "n": len(comparisons),
            "representations": sorted({row["model_id"] for row in comparisons}),
            "mean_absolute_delta_vs_single": mean(row["absolute_delta_vs_single"] for row in comparisons),
            "mean_absolute_delta_vs_original_batch": mean(row["absolute_delta_vs_original_batch"] for row in comparisons),
            "decision_agreement_with_single": mean(row["decision_matches_single"] for row in comparisons),
            "decision_agreement_with_original_batch": mean(row["decision_matches_original_batch"] for row in comparisons),
            "note": "A2 frozen packets already required batch size 1, so size-2 testing is limited to A0/A1.",
        }
    return result


def schema_failure_diagnostics(raw: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    batches = {row["batch_id"]: row for row in manifest["batches"]}
    run_map = {row["batch_id"]: row for row in raw["raw_runs"]}
    failures = []
    for failure in raw["failures"]:
        batch = batches[failure["batch_id"]]
        records = run_map[failure["batch_id"]]["records"]
        failures.append({
            "representation": failure["representation"],
            "error_class": failure["error"],
            "parent_batch_size": len(batch["case_ids"]),
            "attempt_records": len(records),
            "response_payload_retained": any("response" in record for record in records),
        })
    return {
        "failure_count": len(failures),
        "rate_per_prediction": len(failures) / raw["prediction_count"],
        "by_representation": dict(sorted(Counter(row["representation"] for row in failures).items())),
        "by_error_class": dict(sorted(Counter(row["error_class"] for row in failures).items())),
        "failures": failures,
        "root_cause_identifiability": "LIMITED: E4 retained error classes but not schema-invalid response payloads.",
        "e4_treatment": "Original failures remain AGENT_FAILED and are not repaired or imputed.",
    }


def fusion_sensitivity(evaluation: dict[str, Any]) -> dict[str, Any]:
    rows = evaluation["analysis_rows"]
    b6 = {row["observation_id"]: row for row in rows if row["model_id"] == "B6" and row.get("score") is not None}
    output: dict[str, Any] = {"interpretation": "POST_HOC only; E4 labels were visible and no weight may replace frozen H0."}
    for agent_model in ("A0", "A1", "A2"):
        agent = {row["observation_id"]: row for row in rows if row["model_id"] == agent_model and row.get("score") is not None}
        common = sorted(set(b6) & set(agent))
        grid = []
        for step in range(11):
            weight = step / 10
            combined = [{**b6[key], "score": weight * float(b6[key]["score"]) + (1 - weight) * float(agent[key]["score"])} for key in common]
            measured = performance(combined)
            grid.append({"b6_weight": weight, "agent_weight": 1 - weight, "n": measured["n_decisions"], "events": measured["events"], "auroc": measured["auroc"], "pr_auc": measured["pr_auc"], "brier_descriptive": measured["brier_descriptive"]})
        output[agent_model] = grid
    return output


def _calibration_slope(labels: list[int], scores: list[float]) -> dict[str, float | None]:
    if len(set(labels)) < 2 or len(labels) < 10:
        return {"intercept": None, "slope": None}
    logits = [math.log(max(1e-6, min(1 - 1e-6, score)) / (1 - max(1e-6, min(1 - 1e-6, score)))) for score in scores]
    intercept = slope = 0.0
    for _ in range(1500):
        grad_i = grad_s = 0.0
        for value, label in zip(logits, labels, strict=True):
            estimate = 1 / (1 + math.exp(-max(-30, min(30, intercept + slope * value))))
            grad_i += estimate - label
            grad_s += (estimate - label) * value
        intercept -= 0.03 * grad_i / len(labels)
        slope -= 0.03 * grad_s / len(labels)
    return {"intercept": intercept, "slope": slope}


def calibration_diagnostics(evaluation: dict[str, Any]) -> dict[str, Any]:
    output = {"interpretation": "POST_HOC descriptive diagnostics only; no score is calibrated or a probability."}
    for model in sorted({row["model_id"] for row in evaluation["analysis_rows"]}):
        rows = [row for row in evaluation["analysis_rows"] if row["model_id"] == model and row.get("score") is not None]
        labels = [int(row["label"]) for row in rows]
        scores = [float(row["score"]) for row in rows]
        bins = []
        for index in range(10):
            subset = [(label, score) for label, score in zip(labels, scores, strict=True) if index / 10 <= score < (index + 1) / 10 or index == 9 and score == 1]
            if subset:
                bins.append({"lower": index / 10, "upper": (index + 1) / 10, "n": len(subset), "mean_score": mean(score for _, score in subset), "event_rate": mean(label for label, _ in subset)})
        ece = sum(item["n"] * abs(item["mean_score"] - item["event_rate"]) for item in bins) / len(rows) if rows else None
        output[model] = {
            "n": len(rows), "events": sum(labels), "mean_score": mean(scores) if scores else None,
            "event_prevalence": mean(labels) if labels else None,
            "calibration_in_the_large_descriptive": None if not scores else mean(scores) - mean(labels),
            "brier_descriptive": brier_score(labels, scores) if scores else None,
            "ece_descriptive": ece, "calibration_regression": _calibration_slope(labels, scores), "reliability_bins": bins,
        }
    return output


def zenodo_forensics(zenodo_dir: Path, features: list[dict[str, Any]]) -> dict[str, Any]:
    target = {str(row["cik"]).zfill(10) for row in features}
    allowed = set(CONCORDANCE_MAP.values())
    candidates: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(zenodo_dir / "us-public-company-fundamentals.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            cik = str(row.get("cik", "")).zfill(10)
            if cik in target and row.get("fiscal_year") == "2024" and row.get("fiscal_period") == "FY" and row.get("unit") == "USD" and row.get("metric") in allowed:
                candidates[(cik, str(row["metric"]))].append(row)
    comparisons = []
    for feature in features:
        cik = str(feature["cik"]).zfill(10)
        for fact, metric in CONCORDANCE_MAP.items():
            primary = feature["current"].get(fact)
            options = candidates.get((cik, metric), [])
            if primary is None or not options:
                continue
            candidate = options[-1]
            try:
                other = float(candidate["value"])
            except ValueError:
                continue
            relative = abs(float(primary) - other) / max(abs(float(primary)), abs(other), 1.0)
            ratio = None if other == 0 else abs(float(primary) / other)
            comparisons.append({
                "metric": metric, "quality": candidate.get("quality") or "unknown", "relative_difference": relative,
                "sign_mismatch": float(primary) * other < 0, "period_match": candidate.get("end_date") == feature["period_end"],
                "duplicate_candidates": len(options),
                "scaling_suspect": ratio is not None and any(0.9 * scale <= ratio <= 1.1 * scale or 0.9 / scale <= ratio <= 1.1 / scale for scale in (1_000, 1_000_000)),
            })
    by_metric = []
    for metric in sorted({row["metric"] for row in comparisons}):
        rows = [row for row in comparisons if row["metric"] == metric]
        by_metric.append({
            "metric": metric, "n": len(rows), "within_5pct": mean(row["relative_difference"] <= 0.05 for row in rows),
            "median_relative_difference": median(row["relative_difference"] for row in rows),
            "p95_relative_difference": percentile([row["relative_difference"] for row in rows], 0.95),
            "sign_mismatch_rate": mean(row["sign_mismatch"] for row in rows),
            "period_mismatch_rate": mean(not row["period_match"] for row in rows),
            "duplicate_candidate_rate": mean(row["duplicate_candidates"] > 1 for row in rows),
            "scaling_suspect_rate": mean(row["scaling_suspect"] for row in rows),
        })
    mismatch = [row for row in comparisons if row["relative_difference"] > 0.05]
    return {
        "interpretation": "Independent source/processing concordance, not extraction accuracy.",
        "n": len(comparisons),
        "mismatches_over_5pct": len(mismatch),
        "by_metric": sorted(by_metric, key=lambda row: row["within_5pct"]),
        "taxonomy": {
            "sign_mismatch": sum(row["sign_mismatch"] for row in mismatch),
            "period_mismatch": sum(not row["period_match"] for row in mismatch),
            "duplicate_selection_present": sum(row["duplicate_candidates"] > 1 for row in mismatch),
            "unit_scaling_suspect": sum(row["scaling_suspect"] for row in mismatch),
            "reported_vs_derived": dict(sorted(Counter(row["quality"] for row in mismatch).items())),
            "unresolved_taxonomy_or_restatement_or_definition": sum(not row["sign_mismatch"] and row["period_match"] and row["duplicate_candidates"] == 1 and not row["scaling_suspect"] for row in mismatch),
        },
        "limitations": "Restatements, taxonomy semantics, and upstream derivation cannot always be distinguished from the two snapshots alone.",
    }


def integrity(root: Path, artifacts: Path) -> dict[str, Any]:
    features = read_json(artifacts / "features.json")
    outcomes = read_json(artifacts / "outcomes.json")
    predictions = read_json(artifacts / "predictions.json")
    feature_report = read_json(artifacts / "feature_report.json")
    outcome_report = read_json(artifacts / "outcome_report.json")
    prediction_freeze = read_json(artifacts / "prediction_freeze.json")
    evaluation = read_json(artifacts / "evaluation.json")
    primary = {row["hypothesis"]: row for row in evaluation["primary_comparisons"]}
    freeze = read_json(root / "research/e4/protocol/protocol_freeze.json")
    config = read_json(root / "research/e4/protocol/experiment_config.json")
    public_summary = read_json(root / "research/e4/public/readme_summary.json")
    historical_diff = subprocess.run(
        ["git", "diff", "--name-only", "--", "research/results"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    checks = {
        "source_commit": freeze["source_commit"] == "4273b070678240fe7cbdf01a17527afcc71c500e",
        "protocol_sha256": sha256_file(root / "research/e4/protocol/STUDY_PROTOCOL.md") == freeze["protocol_sha256"],
        "config_hash_consistent": config["config_hash"] == freeze["config_hash"] == prediction_freeze["config_hash"],
        "feature_hash": canonical_hash(features) == feature_report["feature_hash"],
        "label_hash": canonical_hash(outcomes) == outcome_report["label_hash"],
        "prediction_hash": canonical_hash(predictions) == prediction_freeze["prediction_hash"],
        "prediction_count": len(predictions) == prediction_freeze["count"] == 10200,
        "cohort_count": len(features) == len(outcomes) == 2000,
        "p1_frozen_values": round(primary["P1"]["observed_delta"], 12) == round(0.03030582077254884, 12),
        "nonverified_not_binary": all(row["financial_deterioration_12m"] is None for row in outcomes if row["label_status"] != "VERIFIED"),
        "public_summary_source": public_summary["source_commit"] == freeze["source_commit"],
        "agent_response_replay": read_json(artifacts / "agent_replay_verification.json")["canonical_byte_identical"],
        "deterministic_replay": read_json(artifacts / "reproducibility_summary.json")["canonical_byte_identical"],
        "historical_research_diff_absent": not historical_diff,
    }
    return {
        "valid": all(checks.values()), "checks": checks,
        "frozen_artifact_sha256": {path.name: sha256_file(path) for path in sorted(artifacts.glob("*.json"))},
        "conclusion": "E4 remains valid" if all(checks.values()) else "E4 INTEGRITY REVIEW REQUIRED",
    }


def write(path: Path, value: Any) -> None:
    write_json(path, value)
