from finrisk.models import altman_z, ohlson_o, piotroski_f


def test_altman_formula():
    v={"working_capital":20,"retained_earnings":30,"ebit":15,"market_value_equity":100,"total_liabilities":50,"revenue":120,"total_assets":100}
    assert altman_z(v).output==3.555

def test_model_missing_and_not_applicable():
    assert altman_z({}).output is None
    assert altman_z({},"bank").interpretation=="Model not applicable"

def test_models_reject_invalid_domains():
    v={"working_capital":1,"retained_earnings":1,"ebit":1,"market_value_equity":1,"total_liabilities":1,"revenue":1,"total_assets":0}
    assert altman_z(v).interpretation=="Invalid input domain"
    o={"total_assets":-1,"total_liabilities":1,"working_capital":1,"current_liabilities":1,"current_assets":1,"net_income":1,"funds_from_operations":1,"prior_net_income":1,"gnp_price_index":1}
    assert ohlson_o(o).interpretation=="Invalid input domain"

def test_piotroski_range():
    p={"net_income":2,"operating_cash_flow":3,"total_assets":100,"long_term_debt":30,"current_assets":40,"current_liabilities":30,"shares_outstanding":10,"gross_profit":30,"revenue":100}
    c={"net_income":5,"operating_cash_flow":7,"total_assets":100,"long_term_debt":20,"current_assets":50,"current_liabilities":30,"shares_outstanding":10,"gross_profit":40,"revenue":110}
    assert piotroski_f(c,p).output==9

def test_ohlson_exposes_probability_separately_from_log_odds():
    v={"total_assets":100,"total_liabilities":50,"working_capital":10,"current_liabilities":20,"current_assets":40,"net_income":5,"funds_from_operations":7,"prior_net_income":4,"gnp_price_index":1}
    result=ohlson_o(v)
    assert result.output is not None
    assert 0<result.derived_outputs["probability"]<1
    assert result.output!=result.derived_outputs["probability"]
