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
    score,_,dims=aggregate(rules,[],cfg)
    assert 0<=score<=100 and dims["liquidity"]["score"]==100

def test_confidence_reduces_with_missing_data():
    assert confidence({"a":1,"b":None},[],[])<confidence({"a":1,"b":2},[],[])

