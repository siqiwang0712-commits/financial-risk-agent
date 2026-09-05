from finrisk.metrics import calculate_metrics
from finrisk.normalization import normalize_line_item, parse_number


def test_ratios_and_fcf():
    m=calculate_metrics({"current_assets":200,"current_liabilities":100,"inventory":50,"cash":25,"operating_cash_flow":80,"capital_expenditure":30,"revenue":500},2025)
    assert m["current_ratio"].value==2
    assert m["quick_ratio"].value==1.5
    assert m["free_cash_flow"].value==50

def test_missing_is_not_zero():
    m=calculate_metrics({"current_assets":200},2025)
    assert m["current_ratio"].value is None and "current_liabilities" in m["current_ratio"].missing_reason

def test_units_and_aliases():
    assert parse_number("(1,250)","millions")==-1_250_000_000
    assert parse_number("N/A") is None
    assert normalize_line_item("Trade receivables")=="accounts_receivable"

def test_multi_year_growth():
    m=calculate_metrics({"revenue":120},{2025:1} if False else 2025,{"revenue":100})
    assert round(m["revenue_growth"].value,2)==.2

