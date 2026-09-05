import pytest
from finrisk.contradictions import detect_contradictions
from finrisk.domain import Evidence, NarrativeClaim


@pytest.mark.parametrize("category,facts",[
    ("solvency_leverage",{"debt_to_assets":.8,"interest_coverage":1.0}),
    ("profitability",{"revenue_growth":-.1,"net_income_growth":-.3}),
    ("cash_flow",{"free_cash_flow":-1,"cfo_to_net_income":.5}),
    ("earnings_quality",{"cfo_to_net_income":.5,"free_cash_flow":-1}),
    ("business_going_concern",{"going_concern_doubt":True}),
])
def test_positive_claim_conflicts_across_dimensions(category,facts):
    claim=NarrativeClaim("Management reports strength",category,Evidence("10-K",1,"Management reports strength",2024),"positive")
    result=detect_contradictions([claim],facts)
    assert len(result)==1 and "not evidence of fraud" in result[0].interpretation


def test_single_weak_signal_does_not_create_contradiction():
    claim=NarrativeClaim("Profitability is strong","profitability",Evidence("10-K",1,"Profitability is strong",2024),"positive")
    assert detect_contradictions([claim],{"net_income_growth":-.2})==[]
