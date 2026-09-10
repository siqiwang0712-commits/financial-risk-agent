from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from finrisk.sec_bulk import (
    FROZEN_CIKS,
    build_annual_outcome_corpus,
    build_companyfacts_corpus,
    build_deterioration_labels,
    build_numeric_corpus,
    build_reported_fcf_periods,
    enrich_metrics,
    load_companyfacts_archive,
    load_statement_archives,
    readiness_report,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "research/empirical_v1/acquisition_plan.csv"
DEFAULT_INPUT = ROOT / "data/sec-bulk"
DEFAULT_OUTPUT = ROOT / "research/empirical_v1"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import real SEC Financial Statement Data Set ZIPs into the frozen v0.3.1 corpus")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    archives = sorted(args.input.glob("*.zip")) if args.input.exists() else []
    if not archives:
        report = {
            "status": "BLOCKED_EXTERNAL_DEPENDENCY", "source": "SEC_FSDS_BULK",
            "reason": f"No official SEC Financial Statement Data Set ZIPs in {args.input}",
            "numeric_observations": 0,
        }
        write_json(args.output / "bulk_import_report.json", report)
        write_json(args.output / "readiness.json", readiness_report([]))
        print(json.dumps(report, indent=2))
        return 2
    with args.plan.open(encoding="utf-8", newline="") as handle:
        plan = list(csv.DictReader(handle))
    companyfacts = next((path for path in archives if path.name.lower() == "companyfacts.zip"), None)
    if companyfacts:
        companies, source = load_companyfacts_archive(companyfacts)
        observations, report = build_companyfacts_corpus(plan, companies, source)
    else:
        target_ciks = {FROZEN_CIKS[row["ticker"]] for row in plan}
        submissions, numbers, sources = load_statement_archives(archives, target_ciks)
        observations, report = build_numeric_corpus(plan, submissions, numbers, sources)
    enrich_metrics(observations)
    reported_periods = build_reported_fcf_periods(submissions, numbers) if not companyfacts else []
    annual_outcomes = build_annual_outcome_corpus(submissions, numbers, sources) if not companyfacts else observations
    outcome_data_available_through = max(
        (row["source_available_time"] for row in annual_outcomes), default=None
    )
    labels = build_deterioration_labels(
        observations, reported_periods, annual_outcomes, outcome_data_available_through
    )
    write_json(args.output / "numeric_corpus.json", observations)
    # Numeric and document corpora are deliberately decoupled.  The numeric
    # observation manifest remains the canonical input to the PIT integrity
    # gate even when no narrative documents are locally available.
    write_json(args.output / "corpus_manifest.json", observations)
    write_json(args.output / "deterioration_labels.json", labels)
    write_json(args.output / "reported_fcf_periods.json", reported_periods)
    write_json(args.output / "annual_outcome_corpus.json", annual_outcomes)
    report["status"] = "EMPIRICALLY_RUN"
    report["verified_labels"] = sum(row["label_status"] == "VERIFIED" for row in labels)
    write_json(args.output / "bulk_import_report.json", report)
    write_json(args.output / "readiness.json", readiness_report(observations, labels))
    print(json.dumps(report, indent=2))
    return 0 if observations else 2


if __name__ == "__main__":
    raise SystemExit(main())
