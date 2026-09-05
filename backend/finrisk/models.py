from __future__ import annotations

import math

from .domain import ModelResult


def _missing(v, keys): return [k for k in keys if v.get(k) is None]


def altman_z(v: dict, entity_type="public_manufacturer") -> ModelResult:
    keys=["working_capital","retained_earnings","ebit","market_value_equity","total_liabilities","revenue","total_assets"]
    if entity_type in {"bank","financial_institution"}: return ModelResult("Altman Z-Score",None,"Model not applicable","Excluded for financial institutions",{},"Public manufacturing Z-score",keys)
    miss=_missing(v,keys)
    if miss:return ModelResult("Altman Z-Score",None,"Insufficient data","Applicable to public manufacturers only",v,"1.2X1+1.4X2+3.3X3+0.6X4+1.0X5",miss)
    z=1.2*v["working_capital"]/v["total_assets"]+1.4*v["retained_earnings"]/v["total_assets"]+3.3*v["ebit"]/v["total_assets"]+0.6*v["market_value_equity"]/v["total_liabilities"]+v["revenue"]/v["total_assets"]
    return ModelResult("Altman Z-Score",round(z,4),"Distress zone" if z<1.81 else "Grey zone" if z<2.99 else "Safe zone","Public manufacturing companies; heuristic outside original population",v,"1.2X1+1.4X2+3.3X3+0.6X4+1.0X5")


def beneish_m(c: dict, p: dict) -> ModelResult:
    required=["accounts_receivable","revenue","gross_profit","current_assets","ppe","total_assets","depreciation","sga","total_debt","net_income","operating_cash_flow"]
    miss=sorted(set(_missing(c,required)+_missing(p,required)))
    if miss:return ModelResult("Beneish M-Score",None,"Insufficient data","Screening signal, not proof of manipulation",{},"-4.84+0.920DSRI+0.528GMI+0.404AQI+0.892SGI+0.115DEPI-0.172SGAI+4.679TATA-0.327LVGI",miss)
    safe=lambda a,b: a/b if b else None
    vals={
      "DSRI":safe(c["accounts_receivable"]/c["revenue"],p["accounts_receivable"]/p["revenue"]),
      "GMI":safe((p["gross_profit"]/p["revenue"]),(c["gross_profit"]/c["revenue"])),
      "AQI":safe(1-(c["current_assets"]+c["ppe"])/c["total_assets"],1-(p["current_assets"]+p["ppe"])/p["total_assets"]),
      "SGI":safe(c["revenue"],p["revenue"]), "DEPI":safe(p["depreciation"]/(p["depreciation"]+p["ppe"]),c["depreciation"]/(c["depreciation"]+c["ppe"])),
      "SGAI":safe(c["sga"]/c["revenue"],p["sga"]/p["revenue"]), "TATA":(c["net_income"]-c["operating_cash_flow"])/c["total_assets"],
      "LVGI":safe(c["total_debt"]/c["total_assets"],p["total_debt"]/p["total_assets"])}
    if any(x is None for x in vals.values()):return ModelResult("Beneish M-Score",None,"Invalid denominator","Screening signal, not proof of manipulation",vals,"Beneish 8-variable formula",["non-zero denominators"])
    m=-4.84+.920*vals["DSRI"]+.528*vals["GMI"]+.404*vals["AQI"]+.892*vals["SGI"]+.115*vals["DEPI"]-.172*vals["SGAI"]+4.679*vals["TATA"]-.327*vals["LVGI"]
    return ModelResult("Beneish M-Score",round(m,4),"Elevated manipulation risk signal" if m>-1.78 else "No elevated signal","Screening signal, not proof of manipulation",vals,"Beneish 8-variable formula")


def piotroski_f(c: dict,p: dict) -> ModelResult:
    keys=["net_income","operating_cash_flow","total_assets","long_term_debt","current_assets","current_liabilities","shares_outstanding","gross_profit","revenue"]
    miss=sorted(set(_missing(c,keys)+_missing(p,keys)))
    if miss:return ModelResult("Piotroski F-Score",None,"Insufficient data","Originally designed for value stocks",{},"Nine binary signals (0-9)",miss)
    roa=lambda x:x["net_income"]/x["total_assets"]
    cr=lambda x:x["current_assets"]/x["current_liabilities"]
    gm=lambda x:x["gross_profit"]/x["revenue"]
    turn=lambda x:x["revenue"]/x["total_assets"]
    signals=[roa(c)>0,c["operating_cash_flow"]>0,roa(c)>roa(p),c["operating_cash_flow"]>c["net_income"],c["long_term_debt"]/c["total_assets"]<p["long_term_debt"]/p["total_assets"],cr(c)>cr(p),c["shares_outstanding"]<=p["shares_outstanding"],gm(c)>gm(p),turn(c)>turn(p)]
    score=sum(signals)
    return ModelResult("Piotroski F-Score",score,"Strong" if score>=7 else "Weak" if score<=3 else "Mixed","Originally designed for value stocks",{f"signal_{i+1}":int(x) for i,x in enumerate(signals)},"Sum of nine binary signals (0-9)")


def ohlson_o(v: dict) -> ModelResult:
    keys=["total_assets","total_liabilities","working_capital","current_liabilities","current_assets","net_income","funds_from_operations","prior_net_income","gnp_price_index"]
    miss=_missing(v,keys)
    if miss:return ModelResult("Ohlson O-Score",None,"Insufficient data","Industrial firms; coefficient-era and input limitations apply",v,"Ohlson (1980) nine-factor logit",miss)
    size=math.log(v["total_assets"]/v["gnp_price_index"])
    o=-1.32-.407*size+6.03*v["total_liabilities"]/v["total_assets"]-1.43*v["working_capital"]/v["total_assets"]+.0757*v["current_liabilities"]/v["current_assets"]-2.37*v["net_income"]/v["total_assets"]-1.83*v["funds_from_operations"]/v["total_liabilities"]+.285*(1 if v["total_liabilities"]>v["total_assets"] else 0)-1.72*(1 if v["net_income"]<0 and v["prior_net_income"]<0 else 0)-.521*(v["net_income"]-v["prior_net_income"])/(abs(v["net_income"])+abs(v["prior_net_income"]))
    probability=1/(1+math.exp(-o))
    return ModelResult("Ohlson O-Score",round(o,4),f"Model-implied distress probability {probability:.1%}","Industrial firms; not the FinRisk overall score",v,"Ohlson (1980) nine-factor logit")

