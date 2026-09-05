import json
from pathlib import Path

from finrisk.pipeline import FinRiskPipeline
from finrisk.report import export_pdf, render_text_report

ROOT=Path(__file__).resolve().parents[1]
data=json.loads((ROOT/"research/benchmark/public_company_observations.json").read_text(encoding="utf-8"))
example=next(x for x in data["examples"] if x["id"]=="intc-2024")
assessment=FinRiskPipeline(ROOT).assess(example["company"],example["fiscal_year"],example["current"],example["previous"],{int(k):v for k,v in example["pages"].items()},example["filing_url"])
(ROOT/"examples/intel_2024_sample_report.txt").write_text(render_text_report(assessment),encoding="utf-8")
export_pdf(assessment,ROOT/"examples/intel_2024_sample_report.pdf")
print(f"generated Intel sample: score={assessment.overall_score}, level={assessment.risk_level}, confidence={assessment.confidence}")
