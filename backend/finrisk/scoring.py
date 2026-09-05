from __future__ import annotations

from collections import defaultdict

CATEGORIES=["liquidity","solvency_leverage","profitability","cash_flow","earnings_quality","accounting","governance_audit","business_going_concern"]


def risk_level(score): return "Very Low" if score<20 else "Low" if score<40 else "Moderate" if score<60 else "High" if score<80 else "Critical"


def aggregate(signals,contradictions,config:dict):
    base=config.get("base_score",10); caps=config.get("category_cap",100); scores=defaultdict(lambda:base)
    for s in signals:scores[s.category]+=s.score_delta
    for c in contradictions:scores[c.category]+=config.get("contradiction_delta",10)
    dims={c:{"score":round(min(caps,max(0,scores[c])),1),"level":risk_level(min(caps,max(0,scores[c]))),"trend":"unknown","key_drivers":[s.rule_id for s in signals if s.category==c]} for c in CATEGORIES}
    weights=config["weights"]
    overall=sum(dims[c]["score"]*weights.get(c,0) for c in CATEGORIES)/sum(weights.values())
    return round(overall,1),risk_level(overall),dims


def confidence(values,verified_evidence,models,multi_year=False):
    completeness=sum(v is not None for v in values.values())/max(1,len(values))
    ev=sum(e.verified for e in verified_evidence)/max(1,len(verified_evidence)) if verified_evidence else .5
    applicable=sum(m.output is not None for m in models)/max(1,len(models))
    score=.5*completeness+.25*ev+.15*applicable+.1*(1 if multi_year else .5)
    return round(min(.99,max(.05,score)),2)
