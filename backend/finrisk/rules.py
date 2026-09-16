from __future__ import annotations

import json
import math
from pathlib import Path

from .domain import RuleSignal

OPS={"<":lambda a,b:a<b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,">=":lambda a,b:a>=b,"==":lambda a,b:a==b,"!=":lambda a,b:a!=b}


def _disabled_rules() -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / "rules" / "disabled_rules.json"
    return json.loads(path.read_text(encoding="utf-8")).get("rules", {}) if path.exists() else {}


DISABLED_RULES = _disabled_rules()


class RuleEngine:
    def __init__(self, rules: list[dict]):
        ids=[r["id"] for r in rules]
        if len(ids)!=len(set(ids)): raise ValueError("Duplicate rule IDs")
        required_rule = {"id", "category", "severity", "conditions", "effect", "rationale"}
        for rule in rules:
            missing = required_rule - set(rule)
            if missing: raise ValueError(f'Rule {rule.get("id", "<unknown>")} missing fields: {sorted(missing)}')
            if not isinstance(rule["id"], str) or not rule["id"].strip(): raise ValueError("Rule ID must be a non-empty string")
            if rule.get("aggregation","max") not in {"max","additive"}:raise ValueError(f'Invalid aggregation for {rule["id"]}')
            if not isinstance(rule["category"], str) or not rule["category"].strip(): raise ValueError(f'Invalid category for {rule["id"]}')
            if not isinstance(rule["severity"], str) or not rule["severity"].strip(): raise ValueError(f'Invalid severity for {rule["id"]}')
            if not isinstance(rule["conditions"], list) or not rule["conditions"]: raise ValueError(f'Rule {rule["id"]} requires conditions')
            effect = rule["effect"]
            delta = effect.get("score_delta") if isinstance(effect, dict) else None
            if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(delta): raise ValueError(f'Invalid score_delta for {rule["id"]}')
            for condition in rule["conditions"]:
                if not isinstance(condition, dict) or set(condition) != {"metric", "operator", "value"}: raise ValueError(f'Invalid condition schema for {rule["id"]}')
                if not isinstance(condition["metric"], str) or not condition["metric"]: raise ValueError(f'Invalid metric for {rule["id"]}')
                if condition["operator"] not in OPS: raise ValueError(f'Invalid operator for {rule["id"]}')
                value=condition["value"]
                if isinstance(value, bool):
                    if condition["operator"] not in {"==", "!="}: raise ValueError(f'Boolean condition requires equality operator for {rule["id"]}')
                elif not isinstance(value,(int,float)) or not math.isfinite(value): raise ValueError(f'Invalid threshold for {rule["id"]}')
        dead = unproducible_rule_conditions(rules)
        if dead: raise ValueError(f"unproducible rule conditions: {dead}")
        self.rules=[rule for rule in rules if rule.get("enabled", True) and rule["id"] not in DISABLED_RULES]

    @classmethod
    def from_file(cls,path):
        path = Path(path)
        rules = json.loads(path.read_text(encoding="utf-8"))["rules"]
        return cls(rules)

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

    Disabled rules are retained solely as an explicit audit record.  Any enabled
    rule without a producer is rejected at startup and in CI.
    """
    producible = producible_fact_names()
    return [
        (rule["id"], condition["metric"])
        for rule in rules
        if rule.get("enabled", True) and rule["id"] not in DISABLED_RULES
        for condition in rule["conditions"]
        if condition["metric"] not in producible
    ]
