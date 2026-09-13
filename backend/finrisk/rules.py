from __future__ import annotations

import json
from pathlib import Path

from .domain import RuleSignal

OPS={"<":lambda a,b:a<b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,">=":lambda a,b:a>=b,"==":lambda a,b:a==b,"!=":lambda a,b:a!=b}


class RuleEngine:
    def __init__(self, rules: list[dict]):
        ids=[r["id"] for r in rules]
        if len(ids)!=len(set(ids)): raise ValueError("Duplicate rule IDs")
        for rule in rules:
            if rule.get("aggregation","max") not in {"max","additive"}:raise ValueError(f'Invalid aggregation for {rule["id"]}')
        self.rules=rules

    @classmethod
    def from_file(cls,path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8"))["rules"])

    def evaluate(self, facts: dict[str,float|str|bool|None]) -> list[RuleSignal]:
        out=[]
        for r in self.rules:
            matches=[]; ok=True
            for c in r["conditions"]:
                actual=facts.get(c["metric"])
                passed=actual is not None and c["operator"] in OPS and OPS[c["operator"]](actual,c["value"])
                ok &= passed
                if passed: matches.append(f'{c["metric"]}={actual} {c["operator"]} {c["value"]}')
            if ok:
                required = [condition["metric"] for condition in r["conditions"]]
                out.append(RuleSignal(r["id"],r["category"],r["severity"],r["effect"]["score_delta"],r["rationale"],matches,family=r.get("family"),required_inputs=required))
        return out


def producible_fact_names() -> set[str]:
    """Every fact name the pipeline can actually produce for a rule to read.

    Derived from the producers rather than hand-listed, so adding a metric or a
    narrative signal automatically widens the set. Imports are local to avoid a
    module-level cycle (facts/pipeline both import this module).
    """
    from .facts import CHANGE_METRICS, MODEL_METRIC_NAMES, NARRATIVE_SIGNAL_RULES
    from .metrics import calculate_metrics
    from .models import ALTMAN_VARIANTS
    from .normalization import ALIASES

    # A fully-populated call yields every metric name, including `*_growth`.
    names = set(calculate_metrics({"revenue": 1}, 2025, {"revenue": 1}))
    names |= {f"{key}_change" for key in CHANGE_METRICS}
    names |= {key for key, _ in NARRATIVE_SIGNAL_RULES}
    names |= set(MODEL_METRIC_NAMES.values())
    names |= {spec["fact_key"] for spec in ALTMAN_VARIANTS.values()}
    names |= {"negative_ebitda_leverage", "total_debt", "ohlson_probability"}
    # `build_facts` (not `calculate_metrics`) owns these derived trend facts.
    names |= {"short_term_debt_growth", "accounts_receivable_growth_gap", "inventory_growth_gap"}
    names |= set(ALIASES.values())
    return names


def unproducible_rule_conditions(rules: list[dict]) -> list[tuple[str, str]]:
    """`(rule_id, metric)` pairs whose metric has no producer in the codebase.

    Such a rule can never fire. This is a diagnostic rather than a startup
    assertion: the checked-in rule set contains a number of these and failing the
    boot would be a bigger regression than the dead rules themselves.
    """
    producible = producible_fact_names()
    return [
        (rule["id"], condition["metric"])
        for rule in rules
        for condition in rule["conditions"]
        if condition["metric"] not in producible
    ]
