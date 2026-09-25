"""Prespecified statistics and robustness analyses for E4."""

from __future__ import annotations

import csv
import gzip
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from .e4_core import canonical_hash, md5_file
from .evaluation import average_precision, brier_score, roc_auc
from .metrics import calculate_metrics
from .numeric_benchmark import ratio_risk_score, temporal_risk_score

BOOTSTRAP_SAMPLES = 5000
PERMUTATION_SAMPLES = 2000
SEED = 20260924
THRESHOLDS = tuple(round(value / 10, 1) for value in range(2, 9))
PRIMARY = (("P1", "B6", "B0"), ("P2", "H0", "B0"), ("P3", "H0", "A2"))
ZENODO_MD5 = {
    "companies.csv.gz": "3d26f01ccf6269d276c88d90ac4408c6",
    "us-public-company-fundamentals.csv.gz": "ce90318a455da1207373e114116fef6b",
    "README.md": "66940b5558d576775cff927aa726a341",
}
CONCORDANCE_MAP = {
    "revenue": "revenue",
    "net_income": "net_income",
    "total_assets": "assets",
    "total_liabilities": "liabilities",
    "current_assets": "current_assets",
    "current_liabilities": "current_liabilities",
    "cash": "cash",
    "operating_cash_flow": "ocf",
    "capital_expenditure": "capex",
    "shareholder_equity": "equity",
    "accounts_receivable": "receivables",
    "inventory": "inventory",
    "long_term_debt": "long_term_debt",
}


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * probability))]


def performance(rows: list[dict[str, Any]], threshold: float = 0.5) -> dict[str, Any]:
    decided = [row for row in rows if row.get("score") is not None]
    labels = [int(row["label"]) for row in decided]
    scores = [float(row["score"]) for row in decided]
    predictions = [int(score >= threshold) for score in scores]
    tp = sum(label == 1 and prediction == 1 for label, prediction in zip(labels, predictions, strict=True))
    tn = sum(label == 0 and prediction == 0 for label, prediction in zip(labels, predictions, strict=True))
    fp = sum(label == 0 and prediction == 1 for label, prediction in zip(labels, predictions, strict=True))
    fn = sum(label == 1 and prediction == 0 for label, prediction in zip(labels, predictions, strict=True))
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    precision = tp / (tp + fp) if tp + fp else None
    f1 = 0.0 if not precision or not recall else 2 * precision * recall / (precision + recall)
    events = sum(labels)
    companies = {row["masked_company_id"] for row in decided}
    event_companies = {row["masked_company_id"] for row in decided if int(row["label"]) == 1}
    prevalence = events / len(labels) if labels else None
    return {
        "n": len(rows),
        "n_decisions": len(decided),
        "company_count": len(companies),
        "events": events,
        "event_companies": len(event_companies),
        "event_prevalence": prevalence,
        "coverage": len(decided) / len(rows) if rows else 0.0,
        "threshold": threshold,
        "auroc": roc_auc(labels, scores) if len(set(labels)) == 2 else None,
        "pr_auc": average_precision(labels, scores) if events and len(set(labels)) == 2 else None,
        "balanced_accuracy": None if recall is None or specificity is None else (recall + specificity) / 2,
        "recall": recall,
        "specificity": specificity,
        "precision": precision,
        "f1": f1,
        "false_negative_rate": None if recall is None else 1 - recall,
        "brier_descriptive": brier_score(labels, scores) if scores else None,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "inference_status": "ADEQUATE" if events >= 20 and len(event_companies) >= 10 else "EXPLORATORY_INSUFFICIENT_POWER",
        "reliability": "UNCALIBRATED",
    }


def bootstrap_interval(rows: list[dict[str, Any]], metric: str, samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["masked_company_id"]].append(row)
    companies = sorted(groups)
    rng = random.Random(seed)
    values = []
    invalid = 0
    for _ in range(samples):
        sampled = [item for _ in companies for item in groups[rng.choice(companies)]]
        value = performance(sampled).get(metric)
        if value is None:
            invalid += 1
        else:
            values.append(float(value))
    observed = performance(rows).get(metric)
    return {
        "metric": metric,
        "observed": observed,
        "ci_low": _percentile(values, 0.025),
        "ci_high": _percentile(values, 0.975),
        "valid_replicates": len(values),
        "invalid_replicates": invalid,
        "cluster_count": len(companies),
    }


def paired_rows(rows: list[dict[str, Any]], challenger: str, reference: str) -> list[dict[str, Any]]:
    left = {row["observation_id"]: row for row in rows if row["model_id"] == reference and row.get("score") is not None}
    right = {row["observation_id"]: row for row in rows if row["model_id"] == challenger and row.get("score") is not None}
    common = sorted(set(left) & set(right))
    return [
        {
            "observation_id": key,
            "masked_company_id": left[key]["masked_company_id"],
            "sector": left[key]["sector"],
            "label": left[key]["label"],
            "reference_score": left[key]["score"],
            "challenger_score": right[key]["score"],
        }
        for key in common
        if left[key]["label"] == right[key]["label"]
    ]


def _paired_metric(rows: list[dict[str, Any]], key: str, metric: str) -> float | None:
    measured = performance([{**row, "score": row[key]} for row in rows])
    value = measured.get(metric)
    return None if value is None else float(value)


def paired_delta(rows: list[dict[str, Any]], challenger: str, reference: str, metric: str = "auroc", samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED) -> dict[str, Any]:
    paired = paired_rows(rows, challenger, reference)
    base = _paired_metric(paired, "reference_score", metric)
    tested = _paired_metric(paired, "challenger_score", metric)
    observed = None if base is None or tested is None else tested - base
    rng = random.Random(seed)
    groups = {row["masked_company_id"]: row for row in paired}
    companies = sorted(groups)
    deltas = []
    invalid = 0
    for _ in range(samples):
        sample = [groups[rng.choice(companies)] for _ in companies]
        left = _paired_metric(sample, "reference_score", metric)
        right = _paired_metric(sample, "challenger_score", metric)
        if left is None or right is None:
            invalid += 1
        else:
            deltas.append(right - left)
    return {
        "challenger": challenger,
        "reference": reference,
        "metric": metric,
        "n_pairs": len(paired),
        "events": sum(int(row["label"]) for row in paired),
        "observed_delta": observed,
        "ci_low": _percentile(deltas, 0.025),
        "ci_high": _percentile(deltas, 0.975),
        "valid_replicates": len(deltas),
        "invalid_replicates": invalid,
    }


def paired_permutation(rows: list[dict[str, Any]], challenger: str, reference: str, samples: int = PERMUTATION_SAMPLES, seed: int = SEED) -> dict[str, Any]:
    paired = paired_rows(rows, challenger, reference)
    observed = paired_delta(rows, challenger, reference, samples=10, seed=seed)["observed_delta"]
    if observed is None:
        return {"p_value": None, "valid_permutations": 0}
    labels = [int(row["label"]) for row in paired]
    rng = random.Random(seed)
    null = []
    for _ in range(samples):
        shuffled = list(labels)
        rng.shuffle(shuffled)
        sample = [{**row, "label": label} for row, label in zip(paired, shuffled, strict=True)]
        left = _paired_metric(sample, "reference_score", "auroc")
        right = _paired_metric(sample, "challenger_score", "auroc")
        if left is not None and right is not None:
            null.append(right - left)
    return {
        "observed_delta": observed,
        "p_value": (1 + sum(abs(value) >= abs(observed) for value in null)) / (len(null) + 1),
        "valid_permutations": len(null),
        "null_ci_low": _percentile(null, 0.025),
        "null_ci_high": _percentile(null, 0.975),
    }


def holm_adjust(tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = [(index, item["p_value"]) for index, item in enumerate(tests) if item.get("p_value") is not None]
    ordered = sorted(indexed, key=lambda pair: pair[1])
    adjusted: dict[int, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, (index, value) in enumerate(ordered):
        running = max(running, min(1.0, (count - rank) * float(value)))
        adjusted[index] = running
    return [{**item, "holm_adjusted_p": adjusted.get(index)} for index, item in enumerate(tests)]


def assemble_analysis(features: list[dict[str, Any]], predictions: list[dict[str, Any]], labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_by_id = {row["observation_id"]: row for row in features}
    verified = {
        row["observation_id"]: int(row["financial_deterioration_12m"])
        for row in labels
        if row.get("label_status") == "VERIFIED" and row.get("financial_deterioration_12m") in {0, 1}
    }
    output = []
    for prediction in predictions:
        if prediction["observation_id"] not in verified:
            continue
        feature = feature_by_id[prediction["observation_id"]]
        output.append({
            **prediction,
            "label": verified[prediction["observation_id"]],
            "sector": feature["sector"],
        })
    return output


def positive_improvement_claim_allowed(comparison: dict[str, Any]) -> bool:
    """Apply the prespecified README claim gate to a paired comparison."""
    return float(comparison["ci_low"]) > 0 and float(comparison["holm_adjusted_p"]) < 0.05


def evaluate(features: list[dict[str, Any]], predictions: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, Any]:
    analysis = assemble_analysis(features, predictions, labels)
    model_ids = sorted({row["model_id"] for row in predictions})
    summaries = {}
    intervals = {}
    for model_id in model_ids:
        rows = [row for row in analysis if row["model_id"] == model_id]
        summaries[model_id] = performance(rows)
        intervals[model_id] = {
            metric: bootstrap_interval(rows, metric, seed=SEED + index)
            for index, metric in enumerate(("auroc", "pr_auc"))
        }
    primary = []
    for index, (hypothesis, challenger, reference) in enumerate(PRIMARY):
        delta = paired_delta(analysis, challenger, reference, seed=SEED + 100 + index)
        permutation = paired_permutation(analysis, challenger, reference, seed=SEED + 200 + index)
        primary.append({"hypothesis": hypothesis, **delta, **permutation})
    primary = holm_adjust(primary)
    return {
        "analysis_rows": analysis,
        "summaries": summaries,
        "intervals": intervals,
        "primary_comparisons": primary,
        "verified_observations": len({row["observation_id"] for row in analysis}),
        "verified_events": len({row["observation_id"] for row in analysis if row["label"] == 1}),
        "analysis_hash": canonical_hash(analysis),
    }


def threshold_sensitivity(analysis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"model_id": model_id, "threshold": threshold, **performance([row for row in analysis if row["model_id"] == model_id], threshold)}
        for model_id in sorted({row["model_id"] for row in analysis})
        for threshold in THRESHOLDS
    ]


def sector_heterogeneity(analysis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for sector in sorted({row["sector"] for row in analysis}):
        for model_id in sorted({row["model_id"] for row in analysis}):
            measured = performance([row for row in analysis if row["sector"] == sector and row["model_id"] == model_id])
            non_events = measured["n_decisions"] - measured["events"]
            output.append({
                "sector": sector,
                "model_id": model_id,
                **measured,
                "subgroup_status": "ANALYTIC" if measured["n_decisions"] >= 20 and measured["events"] >= 5 and non_events >= 5 else "DESCRIPTIVE_ONLY",
            })
    return output


def missingness(features: list[dict[str, Any]], labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    verified = {row["observation_id"]: int(row["financial_deterioration_12m"]) for row in labels if row.get("label_status") == "VERIFIED"}
    output = []
    for mode in ("metric", "raw_fact"):
        for rate in (0.1, 0.3):
            for repeat in range(20):
                for feature in features:
                    if feature["observation_id"] not in verified:
                        continue
                    rng = random.Random(f"{SEED}:{mode}:{rate}:{repeat}:{feature['observation_id']}")
                    if mode == "metric":
                        metrics = dict(feature["metrics"])
                        present = sorted(key for key, value in metrics.items() if value is not None)
                        for key in rng.sample(present, min(len(present), max(1, round(len(present) * rate)))) if present else []:
                            metrics[key] = None
                    else:
                        current = dict(feature["current"])
                        present = sorted(key for key, value in current.items() if value is not None)
                        for key in rng.sample(present, min(len(present), max(1, round(len(present) * rate)))) if present else []:
                            current[key] = None
                        metrics = {key: value.value for key, value in calculate_metrics(current, 2024, feature["previous"]).items()}
                    for model_id, score in (("B0", ratio_risk_score(metrics)), ("B6", temporal_risk_score(metrics))):
                        output.append({
                            "mode": mode,
                            "rate": rate,
                            "repeat": repeat,
                            "observation_id": feature["observation_id"],
                            "masked_company_id": feature["masked_company_id"],
                            "sector": feature["sector"],
                            "model_id": model_id,
                            "score": score,
                            "label": verified[feature["observation_id"]],
                        })
    summaries = []
    for mode in ("metric", "raw_fact"):
        for rate in (0.1, 0.3):
            for model_id in ("B0", "B6"):
                by_repeat = [performance([row for row in output if row["mode"] == mode and row["rate"] == rate and row["model_id"] == model_id and row["repeat"] == repeat]) for repeat in range(20)]
                summaries.append({
                    "mode": mode,
                    "rate": rate,
                    "model_id": model_id,
                    "auroc_median": median([row["auroc"] for row in by_repeat if row["auroc"] is not None]),
                    "coverage_median": median(row["coverage"] for row in by_repeat),
                    "balanced_accuracy_median": median([row["balanced_accuracy"] for row in by_repeat if row["balanced_accuracy"] is not None]),
                })
    return summaries


def label_attrition(features: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, Any]:
    counts = dict(sorted(defaultdict(int, {key: 0 for key in ("VERIFIED", "REQUIRES_HUMAN_REVIEW", "INSUFFICIENT_DATA")}).items()))
    for row in labels:
        counts[row["label_status"]] = counts.get(row["label_status"], 0) + 1
    verified = counts.get("VERIFIED", 0)
    return {"cohort": len(features), "status_counts": counts, "verified_coverage": verified / len(features) if features else 0.0}


def _select_concordance_candidate(options: list[dict[str, str]]) -> dict[str, str] | None:
    """Resolve exact-period duplicate rows only when their numeric values agree."""
    parsed = []
    for row in options:
        try:
            parsed.append((float(row["value"]), row))
        except (KeyError, ValueError):
            continue
    if not parsed:
        return None
    values = {value for value, _ in parsed}
    if len(values) != 1:
        return None
    return min((row for _, row in parsed), key=lambda row: (row.get("quality", ""), row.get("formula", ""), row.get("value", "")))


def source_concordance(zenodo_dir: Path, features: list[dict[str, Any]]) -> dict[str, Any]:
    for name, expected in ZENODO_MD5.items():
        if md5_file(zenodo_dir / name) != expected:
            raise RuntimeError(f"Zenodo MD5 mismatch for {name}")
    target = {str(row["cik"]).zfill(10) for row in features}
    allowed_metrics = set(CONCORDANCE_MAP.values())
    secondary: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(zenodo_dir / "us-public-company-fundamentals.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            cik = str(row.get("cik", "")).zfill(10)
            if cik in target and row.get("fiscal_year") == "2024" and row.get("fiscal_period") == "FY" and row.get("unit") == "USD" and row.get("metric") in allowed_metrics:
                secondary[(cik, str(row["metric"]), str(row.get("end_date", "")))].append(row)
    comparisons = []
    ambiguous_duplicates = 0
    for feature in features:
        cik = str(feature["cik"]).zfill(10)
        for fact, metric in CONCORDANCE_MAP.items():
            primary = feature["current"].get(fact)
            options = secondary.get((cik, metric, feature["period_end"]), [])
            candidate = _select_concordance_candidate(options)
            if options and candidate is None:
                ambiguous_duplicates += 1
            if primary is None or candidate is None:
                continue
            try:
                other = float(candidate["value"])
            except (KeyError, ValueError):
                continue
            relative = abs(float(primary) - other) / max(abs(float(primary)), abs(other), 1.0)
            comparisons.append({"observation_id": feature["observation_id"], "fact": fact, "quality": candidate.get("quality"), "relative_difference": relative})
    relative = sorted(row["relative_difference"] for row in comparisons)
    return {
        "n": len(comparisons),
        "company_count": len({row["observation_id"] for row in comparisons}),
        "within_1pct": sum(row["relative_difference"] <= 0.01 for row in comparisons) / len(comparisons) if comparisons else None,
        "within_5pct": sum(row["relative_difference"] <= 0.05 for row in comparisons) / len(comparisons) if comparisons else None,
        "median_relative_difference": median(relative) if relative else None,
        "p95_relative_difference": _percentile(relative, 0.95),
        "period_matching": "exact feature period_end",
        "ambiguous_duplicates_excluded": ambiguous_duplicates,
        "interpretation": "Independent measurement concordance only; not extraction accuracy. Zenodo was not used for cohort, features, scoring, thresholds, or labels.",
    }


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for position in order[start:end]:
            ranks[position] = rank
        start = end
    return ranks


def spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    x, y = _ranks(left), _ranks(right)
    x_mean, y_mean = mean(x), mean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True))
    denominator = math.sqrt(sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y))
    return numerator / denominator if denominator else 1.0


def stability_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        groups[(row["model_id"], row["observation_id"])].append(row)
    per_case = []
    for (model_id, observation_id), values in sorted(groups.items()):
        scores = [float(row["score"]) for row in values if row.get("score") is not None]
        predictions = [int(row["prediction"]) for row in values if row.get("prediction") is not None]
        per_case.append({
            "model_id": model_id,
            "observation_id": observation_id,
            "score_sd": pstdev(scores) if len(scores) >= 2 else None,
            "decision_agreement": max(predictions.count(0), predictions.count(1)) / len(predictions) if predictions else 0.0,
            "successful_runs": len(scores),
        })
    return {
        "cases": per_case,
        "mean_score_sd": mean([row["score_sd"] for row in per_case if row["score_sd"] is not None]) if per_case else None,
        "mean_decision_agreement": mean(row["decision_agreement"] for row in per_case) if per_case else None,
        "schema_failure_count": sum(row.get("abstained", False) for row in runs),
    }
