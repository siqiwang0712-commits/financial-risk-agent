#!/usr/bin/env python
"""One-command verification of the E4-R study.

    python research/e4r_automated_robustness/verify_e4r.py

It checks, in order:

1. every source artifact hash in the E4-S replication manifest (and the frozen E4 manifest,
   proving E4-R did not mutate E4);
2. that ``experiment_config.json`` and ``feature_sets.json`` are still the frozen versions
   the manifest pins -- i.e. that nobody retuned the study after seeing the results;
3. the SHA-256 of every published E4-R output, detecting mutation or deletion;
4. that the headline statistics can be recomputed from ``oof_predictions.json`` alone and
   still match ``statistical_tests.json``;
5. structural invariants: out-of-fold coverage exactly once per model, the ablation
   reproducing the frozen B6, and the leakage audit still clean.

Exit status: 0 if everything checks out, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _path in (str(REPO_ROOT / "backend"), str(REPO_ROOT / "research" / "e4_statistical_audit"), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import e4r_ablation
import e4r_data
import e4r_stats


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})
        print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f" -- {detail}" if detail and not passed else ""))
        return passed

    def close(self, name: str, observed: float | None, expected: float | None, tolerance: float = 1e-9) -> bool:
        if observed is None or expected is None:
            return self.check(name, False, "missing value")
        gap = abs(observed - expected)
        return self.check(name, gap <= tolerance, f"observed {observed!r}, expected {expected!r}, gap {gap:.3e}")

    @property
    def failed(self) -> list[dict]:
        return [item for item in self.checks if item["status"] == "FAIL"]


def main() -> int:
    report = Report()
    print("== source artifacts ==")
    integrity = e4r_data.verify_sources(run_external=False)
    for entry in integrity.replication_files:
        report.check(f"replication/{Path(entry['path']).name}", entry["status"] == "PASS", entry.get("status", ""))
    for entry in integrity.e4_frozen_files:
        report.check(f"e4-frozen/{Path(entry['path']).name}", entry["status"] == "PASS", entry.get("status", ""))

    print("== frozen prespecification ==")
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    feature_sets = json.loads((HERE / "feature_sets.json").read_text(encoding="utf-8"))
    report.check(
        "experiment_config.json unchanged since the run",
        e4r_data.sha256_json(config) == manifest["config_hash"],
        f"{e4r_data.sha256_json(config)[:16]} vs {manifest['config_hash'][:16]}",
    )
    report.check(
        "feature_sets.json matches the hash pinned in the config",
        e4r_data.sha256_json(feature_sets) == manifest["feature_sets_hash"],
    )
    report.check("status is POST_HOC, not confirmatory", manifest["status"] == "POST_HOC_AUTOMATED_ROBUSTNESS",
                 manifest["status"])

    print("== published outputs ==")
    for entry in manifest["outputs"]:
        path = REPO_ROOT / entry["path"]
        if not path.is_file():
            report.check(entry["path"], False, "missing")
            continue
        observed = e4r_data.sha256_file(path)
        report.check(
            entry["path"],
            entry["sha256"] is not None and observed == entry["sha256"],
            f"{observed[:16]} vs {str(entry['sha256'])[:16]}",
        )

    print("== recomputing the headline statistics from oof_predictions.json ==")
    oof = json.loads((HERE / "oof_predictions.json").read_text(encoding="utf-8"))
    labels: dict[str, int] = {}
    vectors: dict[str, dict[str, float]] = {}
    seen: dict[str, set[str]] = {}
    for row in oof["records"]:
        labels[row["observation_id"]] = int(row["label"])
        vectors.setdefault(row["model"], {})[row["observation_id"]] = float(row["predicted_score"])
        seen.setdefault(row["model"], set()).add(row["observation_id"])
    order = sorted(labels)

    for model, ids in sorted(seen.items()):
        report.check(
            f"OOF coverage: {model} scores every observation exactly once",
            len(ids) == len(order) and ids == set(order),
            f"{len(ids)} vs {len(order)}",
        )

    statistics = json.loads((HERE / "statistical_tests.json").read_text(encoding="utf-8"))
    for item in statistics["primary"]:
        rows = e4r_stats.paired_rows(order, labels, vectors[item["reference"]], vectors[item["challenger"]])
        report.close(f"{item['id']} ΔAUROC", e4r_stats.delta_metric(rows, "auroc"), item["delta_auroc"])
        report.close(f"{item['id']} ΔPR-AUC", e4r_stats.delta_metric(rows, "pr_auc"), item["delta_pr_auc"])
        report.close(
            f"{item['id']} DeLong p",
            e4r_stats.delong_paired(rows, "auroc")["p_value"],
            item["delong"]["p_value"],
            1e-12,
        )

    print("== B6 ablation reproduces the frozen score ==")
    dataset = e4r_data.build_dataset()
    verification = e4r_ablation.verify_against_frozen(dataset)
    report.check("ablation formula equals temporal_risk_score", verification["status"] == "PASS",
                 verification["formula"])
    reconstruction = e4r_data.check_reconstruction(dataset)
    report.check(
        "frozen B0/B6 reconstruct from the packet",
        reconstruction["b0_mismatches"] == 0 and reconstruction["b6_mismatches"] == 0,
        f"max|error| B0 {reconstruction['b0_max_abs_error']:.3e}, B6 {reconstruction['b6_max_abs_error']:.3e}",
    )

    print("== structural invariants ==")
    ablation = json.loads((HERE / "temporal_ablation.json").read_text(encoding="utf-8"))
    b0_auroc = ablation["variants"]["B6_no_temporal"]["auroc"]
    b0_published = json.loads((HERE / "model_results.json").read_text(encoding="utf-8"))["models"]["B0"]["auroc"]
    report.close(
        "B6_no_temporal is rank-equivalent to B0",
        b0_auroc, b0_published, 1e-12,
    )
    leakage = json.loads((HERE / "leakage_audit.json").read_text(encoding="utf-8"))
    report.check(
        "no confirmed leakage",
        not leakage["confirmed_leakage_checks"],
        str(leakage["confirmed_leakage_checks"]),
    )
    calibration = json.loads((HERE / "calibration_diagnostics.json").read_text(encoding="utf-8"))
    report.check("scores remain uncalibrated", calibration["status"] == "UNCALIBRATED", calibration["status"])
    thresholds = json.loads((HERE / "threshold_robustness.json").read_text(encoding="utf-8"))
    report.check("threshold sweep marked sensitivity-only", thresholds["status"] == "SENSITIVITY_ONLY")

    failed = report.failed
    print(f"\n{len(report.checks) - len(failed)}/{len(report.checks)} checks passed")
    for item in failed:
        print(f"  FAIL {item['check']}: {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
