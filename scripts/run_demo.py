import json
from pathlib import Path

from finrisk.pipeline import FinRiskPipeline
from finrisk.report import render_text_report

root=Path(__file__).resolve().parents[1]
d=json.loads((root/"examples"/"synthetic_company.json").read_text())
a=FinRiskPipeline(root).assess(d["company"],d["fiscal_year"],d["current"],d["previous"],{int(k):v for k,v in d["pages"].items()},"Synthetic Annual Report")
print(render_text_report(a))
