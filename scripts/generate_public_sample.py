import json
from pathlib import Path

from finrisk.pipeline import FinRiskPipeline
from finrisk.report import export_pdf, render_text_report

ROOT=Path(__file__).resolve().parents[1]


def main() -> None:
    """Regenerate the committed Intel sample. Importing this module must not."""
    data=json.loads((ROOT/"research/benchmark/public_company_observations.json").read_text(encoding="utf-8"))
    example=next(x for x in data["examples"] if x["id"]=="intc-2024")
    pipeline=FinRiskPipeline(ROOT)
    assessment=pipeline.assess(example["company"],example["fiscal_year"],example["current"],example["previous"],{int(k):v for k,v in example["pages"].items()},example["filing_url"])
    # The decision payload carries the score the decision was derived from; without
    # it the report would only be able to state the weighted aggregate.
    decision=pipeline.decide(assessment)
    (ROOT/"examples/intel_2024_sample_report.txt").write_text(render_text_report(assessment,decision),encoding="utf-8")
    export_pdf(assessment,ROOT/"examples/intel_2024_sample_report.pdf",decision)
    print(f"generated Intel sample: score={assessment.overall_score}, level={assessment.risk_level}, confidence={assessment.confidence}")


if __name__ == "__main__":
    main()
