from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .domain import RuleSignal

OPS={"<":lambda a,b:a<b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,">=":lambda a,b:a>=b,"==":lambda a,b:a==b,"!=":lambda a,b:a!=b}


@dataclass(frozen=True)
class RuleCoverage:
    """Declared rule count vs the rules the built-in producers can actually fire.

    The rule set is a public claim ("68 versioned expert rules"); the reachable
    subset is smaller, because 25 conditions reference governance / audit /
    disclosure facts that no extractor in this repository produces. Those rules
    are not *unreachable* in principle - a caller may supply the facts directly,
    and `FinRiskPipeline.assess` merges the caller's `current` mapping into the
    fact set - but they can never fire from a filing alone.

    Publishing the two numbers side by side is the point: a reader who sees only
    "68 rules" would reasonably assume all 68 are live.
    """

    total_rules: int
    reachable_rules: int
    unreachable_rule_ids: tuple[str, ...]
    unreachable_metrics: tuple[str, ...]

    @property
    def reachable_ratio(self) -> float:
        return self.reachable_rules / self.total_rules if self.total_rules else 0.0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["unreachable_rule_ids"] = list(self.unreachable_rule_ids)
        payload["unreachable_metrics"] = list(self.unreachable_metrics)
        payload["reachable_ratio"] = round(self.reachable_ratio, 4)
        return payload


class RuleEngine:
    def __init__(self, rules: list[dict]):
        ids=[r["id"] for r in rules]
        if len(ids)!=len(set(ids)): raise ValueError("Duplicate rule IDs")
        for rule in rules:
            if rule.get("aggregation","max") not in {"max","additive"}:raise ValueError(f'Invalid aggregation for {rule["id"]}')
        self.rules=rules
        self.coverage = rule_coverage(rules)

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

    Such a rule can never fire from a filing. This is a diagnostic rather than a
    startup assertion: the checked-in rule set contains a number of these and
    failing the boot would be a bigger regression than the dead rules themselves.
    """
    producible = producible_fact_names()
    return [
        (rule["id"], condition["metric"])
        for rule in rules
        for condition in rule["conditions"]
        if condition["metric"] not in producible
    ]


def rule_coverage(rules: list[dict]) -> RuleCoverage:
    """Quantify the gap between the declared rule set and the reachable one.

    The docstring above always admitted that dead rules exist; nothing said how
    many, so "68 versioned expert rules" was the only number anyone could quote.
    This turns the diagnostic into a published figure.
    """
    unreachable = unproducible_rule_conditions(rules)
    unreachable_ids = tuple(sorted({rule_id for rule_id, _ in unreachable}))
    return RuleCoverage(
        total_rules=len(rules),
        reachable_rules=len(rules) - len(unreachable_ids),
        unreachable_rule_ids=unreachable_ids,
        unreachable_metrics=tuple(sorted({metric for _, metric in unreachable})),
    )
