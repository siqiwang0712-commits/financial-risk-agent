import json
from pathlib import Path

from finrisk.parser import DocumentParser
from finrisk.pipeline import FinRiskPipeline
from finrisk.report import export_pdf, render_text_report

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


def test_pdf_export_uses_the_current_decision_report(tmp_path):
    data = json.loads((ROOT / "examples" / "synthetic_company.json").read_text())
    pipeline = FinRiskPipeline(ROOT)
    assessment = pipeline.assess(
        data["company"],
        data["fiscal_year"],
        data["current"],
        data["previous"],
        {int(key): value for key, value in data["pages"].items()},
    )
    destination = tmp_path / "nested" / "assessment.pdf"
    assert export_pdf(assessment, destination, pipeline.decide(assessment)) == destination
    content = destination.read_bytes()
    assert content.startswith(b"%PDF-")
    assert len(content) > 1_000


def test_narrative_boolean_inherits_verified_source():
    assessment=FinRiskPipeline(ROOT).assess(
        "Issuer",2025,{"current_assets":10,"current_liabilities":5},
        pages={7:"Management identified a material weakness."},document="10-K",
    )
    signal=next(item for item in assessment.triggered_rules if item.rule_id=="ACC_005")
    assert signal.source_refs
    assert all(item.verification_status=="verified" for item in signal.source_refs)


def test_going_concern_provider_to_verified_rule_chain():
    assessment=FinRiskPipeline(ROOT).assess(
        "Issuer",2025,{},pages={9:"The auditor identified substantial doubt about the issuer's ability to continue as a going concern."},document="10-K",
    )
    signal=next(item for item in assessment.triggered_rules if item.rule_id=="BUS_001")
    assert signal.category=="business_going_concern"
    assert signal.required_inputs==["going_concern_doubt"]
    assert signal.input_provenance["going_concern_doubt"]
    assert all(item.verification_status=="verified" for item in signal.input_provenance["going_concern_doubt"])
