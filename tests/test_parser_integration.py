import json
from pathlib import Path

from finrisk.parser import DocumentParser
from finrisk.pipeline import FinRiskPipeline
from finrisk.report import render_text_report

ROOT=Path(__file__).resolve().parents[1]
def test_text_parsing():
    pages={1:"CONSOLIDATED BALANCE SHEET\nCash and cash equivalents 1,250"}
    p=DocumentParser();assert 1 in p.identify_sections(pages)["balance_sheet"]
    assert p.extract_values(pages,"sample",2025)[0].value==1250

def test_end_to_end_synthetic():
    d=json.loads((ROOT/"examples"/"synthetic_company.json").read_text())
    a=FinRiskPipeline(ROOT).assess(d["company"],d["fiscal_year"],d["current"],d["previous"],{int(k):v for k,v in d["pages"].items()})
    assert 0<=a.overall_score<=100 and 0<a.confidence<=1
    assert a.triggered_rules and a.contradictions
    assert "not bankruptcy probabilities" in render_text_report(a)

