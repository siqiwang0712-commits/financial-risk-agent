from .domain import Contradiction, NarrativeClaim


def detect_contradictions(claims:list[NarrativeClaim],facts:dict[str,float|None])->list[Contradiction]:
    out=[]
    for c in claims:
        if c.risk_category=="liquidity" and c.polarity=="positive":
            conflicts=[]
            checks=[("Cash declined",facts.get("cash_growth"),lambda x:x<-.1),("Operating cash flow declined",facts.get("operating_cash_flow_growth"),lambda x:x<-.1),("Short-term debt increased",facts.get("short_term_debt_growth"),lambda x:x>.2),("Current ratio fell below 1",facts.get("current_ratio"),lambda x:x<1)]
            conflicts=[label for label,val,test in checks if val is not None and test(val)]
            if len(conflicts)>=2:out.append(Contradiction("liquidity",c.claim,conflicts,"Management language appears more optimistic than the underlying liquidity indicators; this is a consistency signal, not evidence of fraud.",c.evidence))
    return out

