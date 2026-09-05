import json
from pathlib import Path

from finrisk.rules import RuleEngine
from finrisk.scoring import aggregate, confidence

ROOT=Path(__file__).resolve().parents[1]
def test_rule_count_unique_and_cross_metric():
    data=json.loads((ROOT/"rules"/"rules.json").read_text())
    assert 60<=len(data["rules"])<=100
    assert len({r["id"] for r in data["rules"]})==len(data["rules"])
    out=RuleEngine(data["rules"]).evaluate({"current_ratio":.8,"short_term_debt_growth":.4,"cash_growth":-.2})
    assert "LIQ_007" in {x.rule_id for x in out}

def test_aggregation_is_bounded():
    rules=RuleEngine([{"id":"X","category":"liquidity","severity":"high","conditions":[{"metric":"x","operator":">","value":0}],"effect":{"score_delta":500},"rationale":"x"}]).evaluate({"x":1})
    cfg=json.loads((ROOT/"config"/"scoring.json").read_text())
    cfg["minimum_dimension_coverage"]=1
    score,_,dims=aggregate(rules,[],cfg)
    assert 0<=score<=100 and dims["liquidity"]["score"]==100

def test_no_evidence_is_not_very_low():
    cfg=json.loads((ROOT/"config"/"scoring.json").read_text())
    score,level,dims=aggregate([],[],cfg)
    assert score is None and level=="N/A"
    assert all(d["score"] is None for d in dims.values())

def test_nested_thresholds_are_deduplicated():
    rules=RuleEngine.from_file(ROOT/"rules"/"rules.json").evaluate({"current_ratio":.8})
    cfg=json.loads((ROOT/"config"/"scoring.json").read_text());cfg["minimum_dimension_coverage"]=1
    _,_,dims=aggregate(rules,[],cfg)
    assert dims["liquidity"]["score"]==28

def test_confidence_reduces_with_missing_data():
    partial={"cash":1,"current_assets":2}
    complete={k:1 for k in ("cash","current_assets","total_assets","current_liabilities","total_liabilities","shareholder_equity","revenue","operating_income","net_income","operating_cash_flow")}
    assert confidence(partial,[],[])<confidence(complete,[],[])
