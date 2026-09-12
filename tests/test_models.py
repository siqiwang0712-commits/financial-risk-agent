import math

from finrisk.models import altman_z, beneish_m, ohlson_o, piotroski_f


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


def test_ohlson_canonical_dummy_coefficients_and_zero_chin():
    base={"total_assets":100,"total_liabilities":50,"working_capital":10,"current_liabilities":20,"current_assets":40,"net_income":0,"funds_from_operations":7,"prior_net_income":0,"gnp_price_index":1}
    neutral=ohlson_o(base).output
    oeneg=ohlson_o({**base,"total_liabilities":110,"funds_from_operations":15}).output
    expected_oeneg=-1.32-.407*math.log(100)+6.03*1.1-1.43*.1+.0757*.5-1.83*15/110-1.72
    assert oeneg == round(expected_oeneg,4)
    intwo=ohlson_o({**base,"net_income":-1,"prior_net_income":-1}).output
    expected_intwo=-1.32-.407*math.log(100)+6.03*.5-1.43*.1+.0757*.5+2.37/100-1.83*7/50+.285
    assert intwo == round(expected_intwo,4)
    assert neutral is not None


def test_beneish_canonical_lvgi_and_exact_score():
    p={"accounts_receivable":10,"revenue":100,"gross_profit":40,"current_assets":60,"current_liabilities":20,"ppe":20,"total_assets":100,"depreciation":5,"sga":10,"long_term_debt":30,"net_income":8,"operating_cash_flow":9}
    c={"accounts_receivable":15,"revenue":120,"gross_profit":42,"current_assets":65,"current_liabilities":30,"ppe":22,"total_assets":110,"depreciation":6,"sga":13,"long_term_debt":25,"net_income":7,"operating_cash_flow":8}
    result=beneish_m(c,p)
    lvgi=((30+25)/110)/((20+30)/100)
    assert math.isclose(result.inputs["LVGI"],lvgi)
    vals=result.inputs
    expected=-4.84+.920*vals["DSRI"]+.528*vals["GMI"]+.404*vals["AQI"]+.892*vals["SGI"]+.115*vals["DEPI"]-.172*vals["SGAI"]+4.679*vals["TATA"]-.327*vals["LVGI"]
    assert result.output == round(expected,4)
    assert beneish_m({**c,"revenue":0},p).output is None


def test_piotroski_is_explicitly_limited_proxy():
    p={"net_income":2,"operating_cash_flow":3,"total_assets":100,"long_term_debt":30,"current_assets":40,"current_liabilities":30,"shares_outstanding":10,"gross_profit":30,"revenue":100}
    assert "LIMITED" in piotroski_f({**p,"net_income":3},p).applicability
