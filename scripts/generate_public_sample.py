"""Regenerate the committed Intel FY2024 sample report.

Run explicitly. Importing this module must not write anything: it used to
overwrite two tracked artifacts under `examples/` at import time, so any
`importlib` scan, IDE index, packaging step or `pytest --doctest-modules` run
silently rewrote committed files.
"""

from __future__ import annotations

import json
from pathlib import Path

from finrisk.pipeline import FinRiskPipeline
from finrisk.report import export_pdf, render_text_report

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    data = json.loads(
        (ROOT / "research/benchmark/public_company_observations.json").read_text(
            encoding="utf-8"
        )
    )
    example = next(x for x in data["examples"] if x["id"] == "intc-2024")
    # The sixth positional parameter is `document` - the document *title* recorded
    # on every `Evidence` item. `filing_url` used to be passed here, so each
    # evidence record's "document" was a URL, and the report's Source lines (once
    # populated) would have read as a link rather than as a filing name.
    document = f"{example['company']} FY{example['fiscal_year']} annual report"
    assessment = FinRiskPipeline(ROOT).assess(
        example["company"],
        example["fiscal_year"],
        example["current"],
        example["previous"],
        {int(k): v for k, v in example["pages"].items()},
        document,
    )
    (ROOT / "examples/intel_2024_sample_report.txt").write_text(
        render_text_report(assessment), encoding="utf-8"
    )
    export_pdf(assessment, ROOT / "examples/intel_2024_sample_report.pdf")
    print(
        f"generated Intel sample: score={assessment.overall_score}, "
        f"level={assessment.risk_level}, confidence={assessment.confidence}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
