from __future__ import annotations

from collections import defaultdict

CATEGORIES=["liquidity","solvency_leverage","profitability","cash_flow","earnings_quality","accounting","governance_audit","business_going_concern"]


def risk_level(score): return "Very Low" if score<20 else "Low" if score<40 else "Moderate" if score<60 else "High" if score<80 else "Critical"


def aggregate(signals,contradictions,config:dict):
    base=config.get("base_score",10); caps=config.get("category_cap",100); scores=defaultdict(lambda:base); covered=set()
    grouped={};ungrouped=[]
    for s in signals:
        if len(s.evidence)>1:ungrouped.append(s);continue
        metric=s.evidence[0].split("=",1)[0] if s.evidence else s.rule_id
        key=(s.category,metric)
        if key not in grouped or s.score_delta>grouped[key].score_delta:grouped[key]=s
    effective=list(grouped.values())+ungrouped
    for s in effective:scores[s.category]+=s.score_delta;covered.add(s.category)
    for c in contradictions:scores[c.category]+=config.get("contradiction_delta",10);covered.add(c.category)
    dims={c:({"score":round(min(caps,max(0,scores[c])),1),"level":risk_level(min(caps,max(0,scores[c]))),"trend":"unknown","coverage":1.0,"key_drivers":[s.rule_id for s in effective if s.category==c]} if c in covered else {"score":None,"level":"N/A","trend":"unknown","coverage":0.0,"key_drivers":[]}) for c in CATEGORIES}
    weights=config["weights"]
    active=sum(weights.get(c,0) for c in covered)
    minimum=config.get("minimum_dimension_coverage",2)
    if active==0 or len(covered)<minimum:return None,"N/A",dims
    overall=sum(dims[c]["score"]*weights.get(c,0) for c in covered)/active
    return round(overall,1),risk_level(overall),dims


REQUIRED_FIELDS=("cash","current_assets","total_assets","current_liabilities","total_liabilities","shareholder_equity","revenue","operating_income","net_income","operating_cash_flow")

def confidence_components(values,verified_evidence,models,multi_year=False):
    completeness=sum(values.get(k) is not None for k in REQUIRED_FIELDS)/len(REQUIRED_FIELDS)
    ev=sum(e.verified for e in verified_evidence)/max(1,len(verified_evidence)) if verified_evidence else .5
    applicable=sum(m.output is not None for m in models)/max(1,len(models))
    components={"core_data_completeness":completeness,"verified_evidence_coverage":ev,"applicable_model_coverage":applicable,"multi_year_coverage":1.0 if multi_year else 0.5}
    return {k:round(v,3) for k,v in components.items()}

def confidence(values,verified_evidence,models,multi_year=False):
    c=confidence_components(values,verified_evidence,models,multi_year)
    score=.5*c["core_data_completeness"]+.25*c["verified_evidence_coverage"]+.15*c["applicable_model_coverage"]+.1*c["multi_year_coverage"]
    return round(min(.99,max(.05,score)),2)
