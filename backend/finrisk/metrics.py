from __future__ import annotations

from .domain import Metric


def _safe_div(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None or b == 0 else a / b


def _metric(name, value, formula, inputs, year):
    missing = [k for k, v in inputs.items() if v is None]
    reason = f"Required input(s) not reliably identified: {', '.join(missing)}." if missing else ("Denominator is zero." if value is None else None)
    return Metric(name, value, formula, inputs, year, reason)


def calculate_metrics(v: dict[str, float | None], year: int, previous: dict[str, float | None] | None = None) -> dict[str, Metric]:
    debt = v.get("total_debt")
    if debt is None and (v.get("short_term_debt") is not None or v.get("long_term_debt") is not None):
        debt = (v.get("short_term_debt") or 0) + (v.get("long_term_debt") or 0)
    capex = v.get("capital_expenditure")
    fcf = None if v.get("operating_cash_flow") is None or capex is None else v["operating_cash_flow"] - abs(capex)
    ebit = v.get("ebit", v.get("operating_income"))
    cogs = None if v.get("revenue") is None or v.get("gross_profit") is None else v["revenue"] - v["gross_profit"]
    def average_balance(key):
        current=v.get(key); prior=previous.get(key) if previous else None
        return current if prior is None or current is None else (current+prior)/2
    avg_assets = average_balance("total_assets")
    avg_equity = average_balance("shareholder_equity")
    avg_ar = average_balance("accounts_receivable")
    avg_inventory = average_balance("inventory")
    avg_ap = average_balance("accounts_payable")
    m: dict[str, Metric] = {}
    specs = {
      "current_ratio": (_safe_div(v.get("current_assets"), v.get("current_liabilities")), "current_assets / current_liabilities", {"current_assets":v.get("current_assets"),"current_liabilities":v.get("current_liabilities")}),
      "quick_ratio": (_safe_div(None if v.get("current_assets") is None or v.get("inventory") is None else v["current_assets"]-v["inventory"], v.get("current_liabilities")), "(current_assets - inventory) / current_liabilities", {"current_assets":v.get("current_assets"),"inventory":v.get("inventory"),"current_liabilities":v.get("current_liabilities")}),
      "cash_ratio": (_safe_div(v.get("cash"), v.get("current_liabilities")), "cash / current_liabilities", {"cash":v.get("cash"),"current_liabilities":v.get("current_liabilities")}),
      "working_capital": (None if v.get("current_assets") is None or v.get("current_liabilities") is None else v["current_assets"]-v["current_liabilities"], "current_assets - current_liabilities", {"current_assets":v.get("current_assets"),"current_liabilities":v.get("current_liabilities")}),
      "debt_to_equity": (_safe_div(debt, v.get("shareholder_equity")), "total_debt / shareholder_equity", {"total_debt":debt,"shareholder_equity":v.get("shareholder_equity")}),
      "debt_to_assets": (_safe_div(debt, v.get("total_assets")), "total_debt / total_assets", {"total_debt":debt,"total_assets":v.get("total_assets")}),
      "liabilities_to_assets": (_safe_div(v.get("total_liabilities"),v.get("total_assets")), "total_liabilities / total_assets", {"total_liabilities":v.get("total_liabilities"),"total_assets":v.get("total_assets")}),
      "net_debt": (None if debt is None or v.get("cash") is None else debt-v["cash"], "total_debt - cash", {"total_debt":debt,"cash":v.get("cash")}),
      "interest_coverage": (_safe_div(ebit, v.get("interest_expense")), "EBIT / interest_expense", {"EBIT":ebit,"interest_expense":v.get("interest_expense")}),
      "debt_to_ebitda": (_safe_div(debt,v.get("ebitda")), "total_debt / EBITDA", {"total_debt":debt,"EBITDA":v.get("ebitda")}),
      "gross_margin": (_safe_div(v.get("gross_profit"),v.get("revenue")), "gross_profit / revenue", {"gross_profit":v.get("gross_profit"),"revenue":v.get("revenue")}),
      "operating_margin": (_safe_div(v.get("operating_income"),v.get("revenue")), "operating_income / revenue", {"operating_income":v.get("operating_income"),"revenue":v.get("revenue")}),
      "net_margin": (_safe_div(v.get("net_income"),v.get("revenue")), "net_income / revenue", {"net_income":v.get("net_income"),"revenue":v.get("revenue")}),
      "roa": (_safe_div(v.get("net_income"),avg_assets), "net_income / average_total_assets" if previous else "net_income / ending_total_assets (single-year proxy)", {"net_income":v.get("net_income"),"assets_basis":avg_assets}),
      "roe": (_safe_div(v.get("net_income"),avg_equity), "net_income / average_shareholder_equity" if previous else "net_income / ending_shareholder_equity (single-year proxy)", {"net_income":v.get("net_income"),"equity_basis":avg_equity}),
      "cfo_to_net_income": (_safe_div(v.get("operating_cash_flow"),v.get("net_income")), "operating_cash_flow / net_income", {"operating_cash_flow":v.get("operating_cash_flow"),"net_income":v.get("net_income")}),
      "free_cash_flow": (fcf, "operating_cash_flow - abs(capital_expenditure)", {"operating_cash_flow":v.get("operating_cash_flow"),"capital_expenditure":capex}),
      "fcf_margin": (_safe_div(fcf,v.get("revenue")), "free_cash_flow / revenue", {"free_cash_flow":fcf,"revenue":v.get("revenue")}),
      "receivable_days": (_safe_div(avg_ar,v.get("revenue"))*365 if _safe_div(avg_ar,v.get("revenue")) is not None else None, "average_accounts_receivable / revenue * 365" if previous else "ending_accounts_receivable / revenue * 365 (single-year proxy)", {"receivables_basis":avg_ar,"revenue":v.get("revenue")}),
      "inventory_days": (_safe_div(avg_inventory,cogs)*365 if _safe_div(avg_inventory,cogs) is not None else None, "average_inventory / COGS * 365" if previous else "ending_inventory / COGS * 365 (single-year proxy)", {"inventory_basis":avg_inventory,"COGS":cogs}),
      "payable_days": (_safe_div(avg_ap,cogs)*365 if _safe_div(avg_ap,cogs) is not None else None, "average_accounts_payable / COGS * 365" if previous else "ending_accounts_payable / COGS * 365 (single-year proxy)", {"payables_basis":avg_ap,"COGS":cogs}),
    }
    for name,(value,formula,inputs) in specs.items(): m[name]=_metric(name,value,formula,inputs,year)
    if all(m[x].value is not None for x in ("receivable_days","inventory_days","payable_days")):
        val=m["receivable_days"].value+m["inventory_days"].value-m["payable_days"].value
        m["cash_conversion_cycle"]=_metric("cash_conversion_cycle",val,"receivable_days + inventory_days - payable_days",{},year)
    else: m["cash_conversion_cycle"]=_metric("cash_conversion_cycle",None,"receivable_days + inventory_days - payable_days",{"components":None},year)
    if previous:
        for key in ("revenue","net_income","operating_cash_flow","free_cash_flow","total_debt","cash","accounts_receivable","inventory"):
            current = fcf if key=="free_cash_flow" else debt if key=="total_debt" else v.get(key)
            if key=="free_cash_flow":
                prev = None if previous.get("operating_cash_flow") is None or previous.get("capital_expenditure") is None else previous["operating_cash_flow"]-abs(previous["capital_expenditure"])
            elif key=="total_debt":
                prev = previous.get("total_debt")
                if prev is None and (previous.get("short_term_debt") is not None or previous.get("long_term_debt") is not None): prev=(previous.get("short_term_debt") or 0)+(previous.get("long_term_debt") or 0)
            else: prev = previous.get(key)
            value = None if current is None or prev in (None,0) else (current-prev)/abs(prev)
            m[f"{key}_growth"]=_metric(f"{key}_growth",value,f"({key}_current - {key}_prior) / abs({key}_prior)",{"current":current,"prior":prev},year)
    return m
