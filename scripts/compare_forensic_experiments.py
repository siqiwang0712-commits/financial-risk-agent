from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research/results/v0.3.1/benchmark_forensics"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def label_distribution(path: Path) -> dict[str, int]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {
        "verified": sum(row["label_status"] == "VERIFIED" for row in rows),
        "positive": sum(row.get("financial_deterioration_12m") == 1 for row in rows),
        "negative": sum(row.get("financial_deterioration_12m") == 0 for row in rows),
        "review_required": sum(row["label_status"] == "REQUIRES_HUMAN_REVIEW" for row in rows),
        "insufficient_data": sum(row["label_status"] == "INSUFFICIENT_DATA" for row in rows),
    }


def main() -> int:
    e1, e2 = BASE / "v0.3.1-E1-diagnostic", BASE / "v0.3.1-E2"
    results1 = json.loads((e1 / "results.json").read_text(encoding="utf-8"))
    results2 = json.loads((e2 / "results.json").read_text(encoding="utf-8"))
    rows = []
    ranks = {}
    for baseline in ("B0", "B1", "B2", "B6"):
        first, second = results1[baseline], results2[baseline]
        rows.append({
            "baseline": baseline,
            "e1_auroc": first["metrics"]["auroc"], "e2_auroc": second["metrics"]["auroc"],
            "delta_auroc": second["metrics"]["auroc"] - first["metrics"]["auroc"],
            "e1_pr_auc": first["metrics"]["pr_auc"], "e2_pr_auc": second["metrics"]["pr_auc"],
            "e1_recall": first["metrics"]["recall"], "e2_recall": second["metrics"]["recall"],
            "e1_balanced_accuracy": first["metrics"]["balanced_accuracy"],
            "e2_balanced_accuracy": second["metrics"]["balanced_accuracy"],
            "e1_fnr": first["metrics"]["false_negative_rate"], "e2_fnr": second["metrics"]["false_negative_rate"],
        })
        predictions = json.loads((e2 / f"{baseline.lower()}_predictions.json").read_text(encoding="utf-8"))
        test = [row for row in predictions if row["split"] == "test"]
        # A test split with no positive used to abort the comparison with
        # StopIteration; rank reporting is skipped for that baseline instead.
        positive = next((row for row in test if row["label"] == 1), None)
        if positive is None:
            ranks[baseline] = {"score": None, "best_rank": None, "worst_rank": None}
            continue
        higher = sum(float(row["score"]) > float(positive["score"]) for row in test)
        equal = sum(float(row["score"]) == float(positive["score"]) for row in test)
        ranks[baseline] = {"score": positive["score"], "best_rank": higher + 1, "worst_rank": higher + equal}
    comparison = {
        "e1": {"experiment_id": "v0.3.1-E1-diagnostic", "labels": label_distribution(e1 / "deterioration_labels.json")},
        "e2": {"experiment_id": "v0.3.1-E2", "labels": label_distribution(e2 / "deterioration_labels.json")},
        "metric_changes": rows, "e2_positive_ranks": ranks,
        "change_attribution": [
            "Added SEC taxonomy-equivalent PaymentsToAcquireProductiveAssets for CapEx.",
            "Resolved the frozen two-subsequent-reported-period FCF condition from PIT-safe 10-Q/10-K rows.",
            "Replaced field-count sufficiency with per-condition TRUE/FALSE/UNKNOWN logic.",
            "Excluded single-class bootstrap replicates and suppresses CI under inadequate cluster/class power.",
        ],
        "performance_optimization": False, "thresholds_changed": False, "cohort_changed": False,
        "conclusion": "Correctness changed label composition and some rankings; recall remains zero and superiority is not established.",
    }
    comparison["comparison_hash"] = digest(comparison)
    (BASE / "e1_to_e2_comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    with (BASE / "e1_to_e2_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(key for row in rows for key in row)))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
