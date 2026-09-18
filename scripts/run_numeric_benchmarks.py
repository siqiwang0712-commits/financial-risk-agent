from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from finrisk.empirical_validation import (
    canonical_hash,
    company_clustered_bootstrap_delta,
    empirical_binary_metrics,
    freeze_experiment,
    structured_error_cases,
    verify_experiment_freeze,
)
from finrisk.numeric_benchmark import (
    LogisticBaseline,
    ratio_risk_score,
    temporal_risk_score,
    temporal_trajectories,
)
from finrisk.reproducibility import prospective_experiment_metadata
from finrisk.rules import RuleEngine

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/empirical_v1"
OUTPUT = ROOT / "research/results/v0.3.2/empirical_numeric"
FREEZE = OUTPUT / "experiment_manifest.json"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "NOT_AVAILABLE"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_numeric_experiment(observations: list[dict], labels: list[dict]) -> dict:
    configuration = {
        "experiment_id": "v0.3.2-numeric-prospective",
        "dataset_hash": canonical_hash(observations),
        "feature_source_hash": canonical_hash(sorted({row["source_hash"] for row in observations})),
        "outcome_source_hash": canonical_hash(sorted({
            row.get("outcome_source_hash") for row in labels if row.get("outcome_source_hash")
        })),
        "split_hash": canonical_hash(sorted((row["ticker"], row["split"]) for row in observations)),
        "rule_version": file_hash(ROOT / "rules/rules.json"),
        "model_config": {
            "B0": "ratio_risk_score_v2_missing_abstains",
            "B1": "logistic_lr0.1_iter800_train_only_preprocessing",
            "B2": "rules_score_delta_div100",
            "B6": "temporal_risk_score_v1",
            "threshold": 0.5,
            "code_hashes": {
                "numeric_benchmark": file_hash(ROOT / "backend/finrisk/numeric_benchmark.py"),
                "sec_bulk": file_hash(ROOT / "backend/finrisk/sec_bulk.py"),
                "empirical_validation": file_hash(ROOT / "backend/finrisk/empirical_validation.py"),
                "benchmark_runner": file_hash(ROOT / "scripts/run_numeric_benchmarks.py"),
            },
        },
        "fusion_config": "NOT_USED_NUMERIC_BASELINES",
        "prompt_version": "NOT_USED",
        "llm_model": "NOT_USED",
        "label_schema_hash": file_hash(ROOT / "research/label_schema_v2.json"),
        "label_data_hash": canonical_hash(labels),
        "random_seed": 31,
        # Same fallback `prepare_empirical_foundation` already uses: the Docker
        # image ships no `.git`, and an unguarded call aborted the run there.
        "git_commit": _git_commit(),
        **prospective_experiment_metadata(ROOT),
    }
    frozen = freeze_experiment(configuration)
    if FREEZE.exists():
        existing = json.loads(FREEZE.read_text(encoding="utf-8"))
        if not verify_experiment_freeze(existing):
            raise RuntimeError("frozen numeric experiment manifest failed integrity verification")
        raise RuntimeError("prospective experiment already frozen; choose a new experiment version")
    FREEZE.parent.mkdir(parents=True, exist_ok=True)
    FREEZE.write_text(json.dumps(frozen, indent=2, sort_keys=True), encoding="utf-8")
    return frozen


def main() -> int:
    corpus_path = DATA / "numeric_corpus.json"
    label_path = DATA / "deterioration_labels.json"
    if not corpus_path.exists() or not label_path.exists():
        result = {"status": "INSUFFICIENT_DATA", "reason": "numeric corpus or deterministic forward labels missing", "benchmarks": {name: "NOT RUN" for name in ("B0", "B1", "B2", "B6")}}
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "status.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 2
    observations = json.loads(corpus_path.read_text(encoding="utf-8"))
    label_rows = json.loads(label_path.read_text(encoding="utf-8"))
    frozen = freeze_numeric_experiment(observations, label_rows)
    labels = {row["observation_id"]: row["financial_deterioration_12m"] for row in label_rows if row.get("label_status") == "VERIFIED" and row.get("financial_deterioration_12m") in (0, 1)}
    labelled = [row for row in observations if row["observation_id"] in labels]
    train = [row for row in labelled if row["split"] == "train"]
    if not labelled:
        print("No verified forward labels; numeric benchmarks NOT RUN")
        return 2
    rules = RuleEngine.from_file(ROOT / "rules/rules.json")
    predictions: dict[str, list[dict]] = {name: [] for name in ("B0", "B1", "B2", "B6")}
    try:
        logistic = LogisticBaseline().fit(train, [labels[row["observation_id"]] for row in train])
        logistic_scores = dict(zip((row["observation_id"] for row in labelled), logistic.predict_scores(labelled), strict=True))
    except ValueError:
        logistic_scores = {}
    for row in labelled:
        base = {"observation_id": row["observation_id"], "company_id": row["ticker"], "label": labels[row["observation_id"]], "split": row["split"]}
        b0_score = ratio_risk_score(row["metrics"])
        predictions["B0"].append({**base, "score": b0_score, "prediction": int(b0_score >= 0.5)})
        signals = rules.evaluate(row["metrics"])
        b2_score = min(1.0, sum(signal.score_delta for signal in signals) / 100.0)
        predictions["B2"].append({**base, "score": b2_score, "prediction": int(b2_score >= 0.5), "triggered_rules": [signal.rule_id for signal in signals]})
        b6_score = temporal_risk_score(row["metrics"])
        predictions["B6"].append({**base, "score": b6_score, "prediction": int(b6_score >= 0.5)})
        if row["observation_id"] in logistic_scores:
            score = logistic_scores[row["observation_id"]]
            predictions["B1"].append({**base, "score": score, "prediction": int(score >= 0.5)})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, rows in predictions.items():
        test = [row for row in rows if row["split"] == "test"]
        positives = sum(row["label"] == 1 for row in test)
        negatives = len(test) - positives
        results[name] = {
            "status": "EMPIRICALLY_RUN" if test else "INSUFFICIENT_DATA",
            "metrics": empirical_binary_metrics(test) if test else None,
            "n": len(test),
            "positive_count": positives,
            "negative_count": negatives,
            "power_status": "INSUFFICIENT_POWER" if len(test) < 30 or min(positives, negatives) < 10 else "ADEQUATE_FOR_PLANNED_ANALYSIS",
            "interpretation": "SUPERIORITY NOT ESTABLISHED" if test else "NOT RUN",
        }
        (OUTPUT / f"{name.lower()}_predictions.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    paired = [{
        "company_id": left["company_id"], "label": left["label"],
        "prediction_a": left["prediction"], "prediction_b": right["prediction"],
    } for left, right in zip(predictions["B0"], predictions["B6"], strict=True) if left["split"] == "test"]
    def balanced_metric(rows: list[dict]) -> float:
        measured = empirical_binary_metrics([{**row, "score": row["prediction"]} for row in rows])
        return float(measured["balanced_accuracy"] or 0.0)

    results["B6_MINUS_B0_BOOTSTRAP"] = company_clustered_bootstrap_delta(
        paired, balanced_metric, "prediction_a", "prediction_b", samples=1000, seed=31
    ) if paired else {"status": "INSUFFICIENT_DATA"}
    (OUTPUT / "temporal_trajectories.json").write_text(json.dumps(temporal_trajectories(observations), indent=2), encoding="utf-8")
    results["experiment_hash"] = frozen["experiment_hash"]
    errors = {}
    for name, rows in predictions.items():
        test_errors = []
        for row in rows:
            if row["split"] != "test" or row["prediction"] == row["label"]:
                continue
            category = "TEMPORAL_ERROR" if name == "B6" else "RULE_THRESHOLD" if name == "B2" else "NUMERIC_OVERWEIGHT"
            test_errors.append({**row, "error_category": category, "review_status": "machine_generated_pending_review"})
        errors[name] = structured_error_cases(test_errors)
    (OUTPUT / "error_analysis.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
    (OUTPUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
