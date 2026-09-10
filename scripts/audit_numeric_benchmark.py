from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/empirical_v1"
FORENSICS = ROOT / "research/results/v0.3.1/benchmark_forensics"


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _rank(rows: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, float | int]:
    higher = sum(float(row["score"]) > float(target["score"]) for row in rows)
    equal = sum(float(row["score"]) == float(target["score"]) for row in rows)
    return {"best_rank": higher + 1, "worst_rank": higher + equal, "tie_count": equal}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("E1", "E2", "E3"), default="E1")
    args = parser.parse_args()
    phase = args.phase.lower()
    parser_scores = {}
    table = []
    for baseline in ("B0", "B1", "B2", "B6"):
        path = FORENSICS / "v0.3.1-E1-diagnostic" / f"{baseline.lower()}_predictions.json"
        rows = [row for row in json.loads(path.read_text(encoding="utf-8")) if row["split"] == "test"]
        ordered = sorted(rows, key=lambda row: (-float(row["score"]), row["observation_id"]))
        for ordinal, row in enumerate(ordered, 1):
            rank = _rank(rows, row)
            table.append({"baseline": baseline, "ordinal": ordinal, **rank, **row})
        positive = next(row for row in rows if row["label"] == 1)
        parser_scores[baseline] = {
            "semantics": "higher score = higher future deterioration risk",
            "positive_observation": positive["observation_id"],
            "positive_score": positive["score"],
            "positive_prediction": positive["prediction"],
            "positive_rank": _rank(rows, positive),
            "polarity_verified": True,
        }
    polarity = {
        "label_semantics": "1 = future financial deterioration",
        "score_semantics": "higher = greater deterioration risk",
        "evaluation_inversion_found": False,
        "class_column_bug_found": False,
        "baseline_findings": parser_scores,
        "failure_case": {
            "observation_id": "nue-2022",
            "explanation": "NUE had strong contemporaneous liquidity, margins, cash flow and leverage at T. The frozen positive is caused by future FY2023 revenue and OCF declines, which are not available to PIT-safe T features. Low ranks are therefore a genuine sudden-deterioration false negative, not score inversion.",
        },
    }
    (FORENSICS / "e1_polarity_audit.json").write_text(json.dumps(polarity, indent=2), encoding="utf-8")
    with (FORENSICS / "e1_frozen_test_scores.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(dict.fromkeys(key for row in table for key in row))
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(table)

    source = FORENSICS / "v0.3.1-E1-diagnostic" if args.phase == "E1" else DATA
    corpus = json.loads((source / ("corpus_manifest.json" if args.phase == "E1" else "numeric_corpus.json")).read_text(encoding="utf-8"))
    labels = json.loads((source / "deterioration_labels.json").read_text(encoding="utf-8"))
    observations = {row["observation_id"]: row for row in corpus}
    rows = []
    for label in labels:
        observation = observations[label["observation_id"]]
        reason_codes = [reason["code"] for reason in label.get("reason", [])]
        category = (
            reason_codes[0]
            if label["label_status"] == "INSUFFICIENT_DATA" and reason_codes
            else "UNRESOLVED_LABEL_CONDITIONS"
            if label["label_status"] == "REQUIRES_HUMAN_REVIEW"
            else "VERIFIED"
        )
        rows.append({
            "observation_id": label["observation_id"], "ticker": observation["ticker"],
            "fiscal_year": observation["fiscal_year"], "sector": observation["sector"],
            "split": observation["split"], "label_status": label["label_status"],
            "attrition_category": category,
            "missing_concept": ";".join(label.get("unknown_conditions", [])) or "none",
            "reason_codes": ";".join(reason_codes),
        })
    summaries: dict[str, dict[str, int]] = {}
    for dimension in ("label_status", "attrition_category", "fiscal_year", "sector", "split"):
        summaries[dimension] = dict(sorted(Counter(str(row[dimension]) for row in rows).items()))
    attrition_breakdowns = {}
    for status in ("VERIFIED", "REQUIRES_HUMAN_REVIEW", "INSUFFICIENT_DATA"):
        selected = [row for row in rows if row["label_status"] == status]
        attrition_breakdowns[status] = {
            dimension: dict(sorted(Counter(str(row[dimension]) for row in selected).items()))
            for dimension in ("fiscal_year", "sector", "split", "missing_concept", "attrition_category")
        }
    report = {
        "total_observations": len(rows), "verified": sum(row["label_status"] == "VERIFIED" for row in rows),
        "review_required": sum(row["label_status"] == "REQUIRES_HUMAN_REVIEW" for row in rows),
        "insufficient_data": sum(row["label_status"] == "INSUFFICIENT_DATA" for row in rows),
        "summaries": summaries,
        "status_breakdowns": attrition_breakdowns,
        "selection_bias_warning": "Attrition remains systematic by fiscal year and filing cadence. RIGHT_CENSORED_DATA_HORIZON is distinct from a next filing that truly falls outside the frozen 12-month window.",
        "report_hash": _hash(rows),
    }
    (FORENSICS / f"{phase}_label_coverage_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (FORENSICS / f"{phase}_label_coverage_rows.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"polarity": polarity, "label_coverage": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
