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

def test_multi_year_scale_currency_and_statement_context():
    pages={1:"CONSOLIDATED BALANCE SHEET\nAmounts in millions USD\n2025 2024\nCash and cash equivalents 1,250 900"}
    values=DocumentParser().extract_values(pages,"sample",2025)
    assert [(v.fiscal_year,v.value) for v in values]==[(2025,1_250_000_000),(2024,900_000_000)]
    assert all(v.currency=="USD" and v.statement=="balance_sheet" for v in values)

def test_end_to_end_synthetic():
    d=json.loads((ROOT/"examples"/"synthetic_company.json").read_text())
    a=FinRiskPipeline(ROOT).assess(d["company"],d["fiscal_year"],d["current"],d["previous"],{int(k):v for k,v in d["pages"].items()})
    assert 0<=a.overall_score<=100 and 0<a.confidence<=1
    assert a.triggered_rules and a.contradictions
    assert "not bankruptcy probabilities" in render_text_report(a)
