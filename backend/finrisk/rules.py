from __future__ import annotations

import json
from pathlib import Path

from .domain import RuleSignal

OPS={"<":lambda a,b:a<b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,">=":lambda a,b:a>=b,"==":lambda a,b:a==b,"!=":lambda a,b:a!=b}


class RuleEngine:
    def __init__(self, rules: list[dict]):
        ids=[r["id"] for r in rules]
        if len(ids)!=len(set(ids)): raise ValueError("Duplicate rule IDs")
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
            if ok: out.append(RuleSignal(r["id"],r["category"],r["severity"],r["effect"]["score_delta"],r["rationale"],matches))
        return out

