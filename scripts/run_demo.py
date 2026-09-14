"""Print the full text report for the repository's synthetic fixture.

Run explicitly. Importing this module used to run the whole assessment and print
a report as a side effect.
"""

from __future__ import annotations

import json
from pathlib import Path

from finrisk.pipeline import FinRiskPipeline
from finrisk.report import render_text_report


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "examples" / "synthetic_company.json").read_text())
    assessment = FinRiskPipeline(root).assess(
        data["company"],
        data["fiscal_year"],
        data["current"],
        data["previous"],
        {int(k): v for k, v in data["pages"].items()},
        "Synthetic Annual Report",
    )
    print(render_text_report(assessment))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
