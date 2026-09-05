from __future__ import annotations

import json
from pathlib import Path

from .contradictions import detect_contradictions
from .domain import Assessment
from .evidence import EvidenceVerifier
from .llm import MockNarrativeProvider, NarrativeProvider
from .metrics import calculate_metrics
from .models import altman_z, beneish_m, ohlson_o, piotroski_f
from .rules import RuleEngine
from .scoring import aggregate, confidence


class FinRiskPipeline:
    def __init__(self,root:Path|None=None,provider:NarrativeProvider|None=None):
        self.root=root or Path(__file__).resolve().parents[2]
        self.rules=RuleEngine.from_file(self.root/"rules"/"rules.json")
        self.scoring=json.loads((self.root/"config"/"scoring.json").read_text(encoding="utf-8"))
        self.provider=provider or MockNarrativeProvider(); self.verifier=EvidenceVerifier()

    def assess(self,company:str,year:int,current:dict,previous:dict|None=None,pages:dict[int,str]|None=None,document="Annual Report",entity_type="industrial") -> Assessment:
        pages=pages or {}
        metrics=calculate_metrics(current,year,previous)
        facts={k:m.value for k,m in metrics.items()}|current
        if previous:
            for key in ("short_term_debt",):
                facts[f"{key}_growth"]=None if current.get(key) is None or previous.get(key) in (None,0) else (current[key]-previous[key])/abs(previous[key])
            for key in ("gross_margin","operating_margin","receivable_days","inventory_days","cash_conversion_cycle"):
                prior=calculate_metrics(previous,year-1).get(key); now=metrics.get(key)
                facts[f"{key}_change"]=None if not prior or not now or prior.value is None or now.value is None else now.value-prior.value
        model_input=current|{"working_capital":metrics["working_capital"].value,"ebit":current.get("ebit",current.get("operating_income"))}
        models=[altman_z(model_input,"bank" if entity_type in {"bank","financial_institution"} else "public_manufacturer")]
        if previous: models += [beneish_m(current,previous),piotroski_f(current,previous)]
        models += [ohlson_o(model_input)]
        for model in models:
            if model.name=="Beneish M-Score":facts["beneish_m_score"]=model.output
        claims=self.provider.extract(pages,document,year)
        verified=[]; accepted=[]
        for claim in claims:
            ev=self.verifier.verify(claim.evidence,pages); verified.append(ev)
            if ev.verified: claim.evidence=ev; accepted.append(claim)
        facts.update({"going_concern_doubt":any("going concern" in c.claim.lower() or "substantial doubt" in c.claim.lower() for c in accepted),"material_weakness":any("material weakness" in c.claim.lower() for c in accepted),"refinancing_dependency":any("refinancing" in c.claim.lower() for c in accepted)})
        signals=self.rules.evaluate(facts)
        contradictions=detect_contradictions(accepted,facts)
        score,level,dimensions=aggregate(signals,contradictions,self.scoring)
        missing=[f"{m.name}: N/A — {m.missing_reason} Impact: assessment confidence reduced." for m in metrics.values() if m.value is None]
        conf=confidence(current,verified,models,previous is not None)
        return Assessment(company,str(year),score,level,conf,dimensions,metrics,models,signals,contradictions,missing)

