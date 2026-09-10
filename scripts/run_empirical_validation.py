from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from finrisk.empirical_validation import (
    benchmark_readiness,
    calibration_eligibility,
    canonical_hash,
    independent_label_report,
    validate_dataset_integrity,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "research/empirical_v1/corpus_manifest.json"
REPORT = ROOT / "research/empirical_v1/integrity_report.json"
ANNOTATIONS = ROOT / "research/empirical_v1/outcome_annotations.csv"
READINESS = ROOT / "research/empirical_v1/readiness.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed empirical validation entry point")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--allow-not-available", action="store_true", help="write an honest blocked report and exit successfully; never runs a benchmark")
    args = parser.parse_args()
    if not args.manifest.exists():
        report = {
            "gate": "STOP",
            "status": "NOT AVAILABLE",
            "benchmark_status": "NOT RUN",
            "reason": f"real corpus manifest not found: {args.manifest.name}",
            "sec_user_agent_configured": bool(os.getenv("SEC_USER_AGENT")),
            "openai_api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if args.allow_not_available else 2
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))
    integrity = validate_dataset_integrity(rows)
    integrity["dataset_hash"] = canonical_hash(rows)
    integrity["calibration"] = calibration_eligibility(
        {"population_prevalence_preserved": False, "case_control_sampling": True}
    )
    annotation_rows = list(csv.DictReader(ANNOTATIONS.open(encoding="utf-8"))) if ANNOTATIONS.exists() else []
    integrity["independent_labels"] = independent_label_report(annotation_rows)
    capabilities = json.loads(READINESS.read_text(encoding="utf-8")) if READINESS.exists() else {}
    integrity["capabilities"] = capabilities
    integrity["benchmarks"] = benchmark_readiness(capabilities)
    integrity["benchmark_status"] = "PARTIALLY_READY" if any(
        item["status"] == "READY" for item in integrity["benchmarks"].values()
    ) else "NOT RUN"
    REPORT.write_text(json.dumps(integrity, indent=2), encoding="utf-8")
    print(json.dumps(integrity, indent=2))
    return 0 if integrity["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
