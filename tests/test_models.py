from finrisk.models import altman_z, piotroski_f


def test_altman_formula():
    v={"working_capital":20,"retained_earnings":30,"ebit":15,"market_value_equity":100,"total_liabilities":50,"revenue":120,"total_assets":100}
    assert altman_z(v).output==3.555

def test_model_missing_and_not_applicable():
    assert altman_z({}).output is None
    assert altman_z({},"bank").interpretation=="Model not applicable"

def test_piotroski_range():
    p={"net_income":2,"operating_cash_flow":3,"total_assets":100,"long_term_debt":30,"current_assets":40,"current_liabilities":30,"shares_outstanding":10,"gross_profit":30,"revenue":100}
    c={"net_income":5,"operating_cash_flow":7,"total_assets":100,"long_term_debt":20,"current_assets":50,"current_liabilities":30,"shares_outstanding":10,"gross_profit":40,"revenue":110}
    assert piotroski_f(c,p).output==9
