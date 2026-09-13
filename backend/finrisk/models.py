from __future__ import annotations

import math

from .domain import ModelResult


def _logistic(x: float) -> float:
    """Numerically safe logistic function.

    ``1 / (1 + exp(-x))`` raises ``OverflowError`` for ``x <= -710``. That branch
    is reachable in practice (a ``math.exp(745)`` overflow is exactly what a
    mis-scaled liability produces), and because it is not caught anywhere the
    exception escapes as an HTTP 500 for the whole assessment. The logistic
    saturates to 0/1 well before the overflow point, so clamp the exponent.
    """
    if x >= 700:
        return 1.0
    if x <= -700:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _missing(v, keys): return [k for k in keys if v.get(k) is None]

def _invalid(v, keys, positive=()):
    bad=[k for k in keys if v.get(k) is not None and (not isinstance(v[k],(int,float)) or not math.isfinite(v[k]))]
    bad += [k for k in positive if v.get(k) is not None and v[k]<=0]
    return sorted(set(bad))


# Altman's three published variants. The original 1968 Z-score was fitted on
# public manufacturers; applying its 1.81/2.99 cut-offs to a REIT, a retailer or a
# private company is a category error. Each variant carries its own coefficients,
# required components and zone boundaries, and writes to its own fact key so the
# public-manufacturer mapping can never misfire on another population.
ALTMAN_VARIANTS: dict[str, dict] = {
    "public_manufacturer": {
        "fact_key": "altman_z_score",
        "equity_field": "market_value_equity",
        "components": ("working_capital", "retained_earnings", "ebit", "market_value_equity", "total_liabilities", "revenue", "total_assets"),
        "coefficients": (1.2, 1.4, 3.3, 0.6, 1.0),
        "use_revenue": True,
        "thresholds": (1.81, 2.99),
        "formula": "1.2X1+1.4X2+3.3X3+0.6X4+1.0X5",
        "interpretation": "Public manufacturing companies; heuristic outside original population",
    },
    "private": {
        "fact_key": "altman_z_prime_score",
        "equity_field": "shareholder_equity",
        "components": ("working_capital", "retained_earnings", "ebit", "shareholder_equity", "total_liabilities", "revenue", "total_assets"),
        "coefficients": (0.717, 0.847, 3.107, 0.420, 0.998),
        "use_revenue": True,
        "thresholds": (1.23, 2.90),
        "formula": "0.717X1+0.847X2+3.107X3+0.420X4+0.998X5",
        "interpretation": "Private-firm Z' variant (book equity replaces market value); heuristic",
    },
    "non_manufacturer": {
        "fact_key": "altman_z_double_prime_score",
        "equity_field": "shareholder_equity",
        "components": ("working_capital", "retained_earnings", "ebit", "shareholder_equity", "total_liabilities", "total_assets"),
        "coefficients": (6.56, 3.26, 6.72, 1.05),
        "use_revenue": False,
        "thresholds": (4.15, 5.85),
        "formula": "6.56X1+3.26X2+6.72X3+1.05X4",
        "interpretation": "Non-manufacturer Z'' variant (asset-turnover term omitted); heuristic",
    },
}

_ALTMAN_PRIVATE_TYPES = {"private", "private_company", "private_manufacturer"}
_ALTMAN_MANUFACTURING_TYPES = {"manufacturing", "industrial", "public_manufacturer", "public", ""}
_ALTMAN_FINANCIAL_TYPES = {"bank", "banking", "financial_institution"}


def altman_variant(entity_type: str) -> str:
    """Map a declared entity type onto the appropriate Altman population."""
    key = (entity_type or "").lower().strip()
    if key in _ALTMAN_PRIVATE_TYPES:
        return "private"
    if key in _ALTMAN_MANUFACTURING_TYPES:
        return "public_manufacturer"
    return "non_manufacturer"


def altman_z(v: dict, entity_type="public_manufacturer") -> ModelResult:
    variant = altman_variant(entity_type)
    spec = ALTMAN_VARIANTS[variant]
    keys = list(spec["components"])
    if (entity_type or "").lower().strip() in _ALTMAN_FINANCIAL_TYPES:
        return ModelResult("Altman Z-Score", None, "Model not applicable", "Excluded for financial institutions", {}, spec["formula"], keys)
    miss = _missing(v, keys)
    if miss:
        return ModelResult("Altman Z-Score", None, "Insufficient data", spec["interpretation"], v, spec["formula"], miss)
    invalid = _invalid(v, keys, ("total_assets", "total_liabilities"))
    if invalid:
        return ModelResult("Altman Z-Score", None, "Invalid input domain", spec["interpretation"], v, spec["formula"], invalid)
    assets = v["total_assets"]
    x1 = v["working_capital"] / assets
    x2 = v["retained_earnings"] / assets
    x3 = v["ebit"] / assets
    x4 = v[spec["equity_field"]] / v["total_liabilities"]
    coefficients = spec["coefficients"]
    z = coefficients[0] * x1 + coefficients[1] * x2 + coefficients[2] * x3 + coefficients[3] * x4
    if spec["use_revenue"]:
        z += coefficients[4] * (v["revenue"] / assets)
    distress, safe = spec["thresholds"]
    zone = "Distress zone" if z < distress else "Grey zone" if z < safe else "Safe zone"
    return ModelResult(
        "Altman Z-Score", round(z, 4), zone, spec["interpretation"], v, spec["formula"],
        derived_outputs={"variant": variant, "fact_key": spec["fact_key"],
                         "zone_boundaries": [distress, safe]},
    )


def beneish_m(c: dict, p: dict) -> ModelResult:
    required=["accounts_receivable","revenue","gross_profit","current_assets","current_liabilities","ppe","total_assets","depreciation","sga","long_term_debt","net_income","operating_cash_flow"]
    miss=sorted(set(_missing(c,required)+_missing(p,required)))
    if miss:return ModelResult("Beneish M-Score",None,"Insufficient data","Screening signal, not proof of manipulation",{},"-4.84+0.920DSRI+0.528GMI+0.404AQI+0.892SGI+0.115DEPI-0.172SGAI+4.679TATA-0.327LVGI",miss)
    invalid=sorted(set(_invalid(c,required,("revenue","total_assets"))+_invalid(p,required,("revenue","total_assets"))))
    if invalid:return ModelResult("Beneish M-Score",None,"Invalid input domain","Screening signal, not proof of manipulation",{},"Beneish 8-variable formula",invalid)
    safe=lambda a,b: None if a is None or b in (None, 0) else a/b
    prior_depreciation_rate=safe(p["depreciation"],p["depreciation"]+p["ppe"])
    current_depreciation_rate=safe(c["depreciation"],c["depreciation"]+c["ppe"])
    vals={
      "DSRI":safe(c["accounts_receivable"]/c["revenue"],p["accounts_receivable"]/p["revenue"]),
      "GMI":safe((p["gross_profit"]/p["revenue"]),(c["gross_profit"]/c["revenue"])),
      "AQI":safe(1-(c["current_assets"]+c["ppe"])/c["total_assets"],1-(p["current_assets"]+p["ppe"])/p["total_assets"]),
      "SGI":safe(c["revenue"],p["revenue"]), "DEPI":safe(prior_depreciation_rate,current_depreciation_rate),
      "SGAI":safe(c["sga"]/c["revenue"],p["sga"]/p["revenue"]), "TATA":(c["net_income"]-c["operating_cash_flow"])/c["total_assets"],
      "LVGI":safe((c["current_liabilities"]+c["long_term_debt"])/c["total_assets"],(p["current_liabilities"]+p["long_term_debt"])/p["total_assets"])}
    if any(x is None or not math.isfinite(x) for x in vals.values()):return ModelResult("Beneish M-Score",None,"Invalid denominator","Screening signal, not proof of manipulation",vals,"Beneish 8-variable formula",["non-zero denominators"])
    m=-4.84+.920*vals["DSRI"]+.528*vals["GMI"]+.404*vals["AQI"]+.892*vals["SGI"]+.115*vals["DEPI"]-.172*vals["SGAI"]+4.679*vals["TATA"]-.327*vals["LVGI"]
    return ModelResult("Beneish M-Score",round(m,4),"Elevated manipulation risk signal" if m>-1.78 else "No elevated signal","Screening signal, not proof of manipulation",vals,"Beneish 8-variable formula")


def piotroski_f(c: dict,p: dict) -> ModelResult:
    keys=["net_income","operating_cash_flow","total_assets","long_term_debt","current_assets","current_liabilities","shares_outstanding","gross_profit","revenue"]
    miss=sorted(set(_missing(c,keys)+_missing(p,keys)))
    if miss:return ModelResult("Piotroski F-Score",None,"Insufficient data","LIMITED: Piotroski-style proxy; beginning/average asset denominators unavailable",{},"Nine proxy binary signals (0-9)",miss)
    invalid=sorted(set(_invalid(c,keys,("total_assets","current_liabilities","revenue"))+_invalid(p,keys,("total_assets","current_liabilities","revenue"))))
    if invalid:return ModelResult("Piotroski F-Score",None,"Invalid input domain","LIMITED: Piotroski-style proxy; beginning/average asset denominators unavailable",{},"Nine proxy binary signals (0-9)",invalid)
    roa=lambda x:x["net_income"]/x["total_assets"]
    cr=lambda x:x["current_assets"]/x["current_liabilities"]
    gm=lambda x:x["gross_profit"]/x["revenue"]
    turn=lambda x:x["revenue"]/x["total_assets"]
    signals=[roa(c)>0,c["operating_cash_flow"]>0,roa(c)>roa(p),c["operating_cash_flow"]>c["net_income"],c["long_term_debt"]/c["total_assets"]<p["long_term_debt"]/p["total_assets"],cr(c)>cr(p),c["shares_outstanding"]<=p["shares_outstanding"],gm(c)>gm(p),turn(c)>turn(p)]
    score=sum(signals)
    return ModelResult("Piotroski F-Score",score,"Strong proxy signal" if score>=7 else "Weak proxy signal" if score<=3 else "Mixed proxy signal","LIMITED: Piotroski-style proxy; end-of-period assets replace unavailable beginning/average denominators",{f"signal_{i+1}":int(x) for i,x in enumerate(signals)},"Sum of nine Piotroski-style proxy signals (0-9)")


def ohlson_o(v: dict) -> ModelResult:
    keys=["total_assets","total_liabilities","working_capital","current_liabilities","current_assets","net_income","funds_from_operations","prior_net_income","gnp_price_index"]
    miss=_missing(v,keys)
    if miss:return ModelResult("Ohlson O-Score",None,"Insufficient data","Industrial firms; coefficient-era and input limitations apply",v,"Ohlson (1980) nine-factor logit",miss)
    invalid=_invalid(v,keys,("total_assets","total_liabilities","current_assets","gnp_price_index"))
    if invalid:return ModelResult("Ohlson O-Score",None,"Invalid input domain","Industrial firms; CPI/GNP index requires consistent base-year units",v,"Ohlson (1980) nine-factor logit",invalid)
    size=math.log(v["total_assets"]/v["gnp_price_index"])
    denominator=abs(v["net_income"])+abs(v["prior_net_income"])
    chin=0.0 if denominator == 0 else (v["net_income"]-v["prior_net_income"])/denominator
    o=-1.32-.407*size+6.03*v["total_liabilities"]/v["total_assets"]-1.43*v["working_capital"]/v["total_assets"]+.0757*v["current_liabilities"]/v["current_assets"]-2.37*v["net_income"]/v["total_assets"]-1.83*v["funds_from_operations"]/v["total_liabilities"]-1.72*(1 if v["total_liabilities"]>v["total_assets"] else 0)+.285*(1 if v["net_income"]<0 and v["prior_net_income"]<0 else 0)-.521*chin
    probability=_logistic(o)
    return ModelResult("Ohlson O-Score",round(o,4),f"Model-implied distress probability {probability:.1%}","Industrial firms; not the FinRisk overall score",v,"Ohlson (1980) nine-factor logit",derived_outputs={"probability":round(probability,6)})
