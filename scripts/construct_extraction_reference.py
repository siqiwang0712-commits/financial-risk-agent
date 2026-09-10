from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from finrisk.extraction_reference import (
    construct_pre_num_reference,
    load_pre_num_reference_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Construct a non-adjudicated SEC pre.txt/num.txt extraction reference")
    parser.add_argument("--input", type=Path, default=ROOT / "data/sec-bulk")
    parser.add_argument("--corpus", type=Path, default=ROOT / "research/empirical_v1/numeric_corpus.json")
    parser.add_argument("--output", type=Path, default=ROOT / "research/empirical_v1")
    args = parser.parse_args()
    observations = json.loads(args.corpus.read_text(encoding="utf-8"))
    archives = sorted(args.input.glob("*.zip"))
    presentations, numbers, sources = load_pre_num_reference_rows(
        archives, {str(row["accession"]) for row in observations}
    )
    rows, report = construct_pre_num_reference(observations, presentations, numbers, sources)
    args.output.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row})
    with (args.output / "extraction_reference.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "evidence_locator": json.dumps(row.get("evidence_locator"), sort_keys=True)})
    (args.output / "extraction_reference_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["reconciled_fields"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
