from __future__ import annotations

import json
from pathlib import Path

from .contradictions import detect_contradictions
from .domain import Assessment, RuleSignal
from .enterprise.applicability import enforce_applicability
from .evidence import EvidenceVerifier
from .llm import NarrativeProvider, provider_from_env
from .metrics import calculate_metrics
from .models import altman_z, beneish_m, ohlson_o, piotroski_f
from .rules import RuleEngine
from .scoring import aggregate, confidence, confidence_components


class FinRiskPipeline:
    def __init__(self,root:Path|None=None,provider:NarrativeProvider|None=None):
        self.root=root or Path(__file__).resolve().parents[2]
        self.rules=RuleEngine.from_file(self.root/"rules"/"rules.json")
        self.scoring=json.loads((self.root/"config"/"scoring.json").read_text(encoding="utf-8"))
        self.model_scoring=json.loads((self.root/"config"/"model_scoring.json").read_text(encoding="utf-8"))
        self.provider=provider or provider_from_env(); self.verifier=EvidenceVerifier()

    def assess(self,company:str,year:int,current:dict,previous:dict|None=None,pages:dict[int,str]|None=None,document="Annual Report",entity_type="industrial",source_map:dict|None=None) -> Assessment:
        pages=pages or {}
        source_map=source_map or {}
        metrics=calculate_metrics(current,year,previous)
        for metric in metrics.values():
            seen=set()
            for key in metric.inputs:
                for ev in source_map.get(key,[]):
                    identity=(ev.document,ev.page,ev.source_text)
                    if identity not in seen:metric.source_refs.append(ev);seen.add(identity)
        facts={k:m.value for k,m in metrics.items()}|current
        if previous:
            for key in ("short_term_debt",):
                facts[f"{key}_growth"]=None if current.get(key) is None or previous.get(key) in (None,0) else (current[key]-previous[key])/abs(previous[key])
            for key in ("gross_margin","operating_margin","receivable_days","inventory_days","cash_conversion_cycle"):
                prior=calculate_metrics(previous,year-1).get(key); now=metrics.get(key)
                facts[f"{key}_change"]=None if not prior or not now or prior.value is None or now.value is None else now.value-prior.value
            facts["accounts_receivable_growth_gap"] = None if facts.get("accounts_receivable_growth") is None or facts.get("revenue_growth") is None else facts["accounts_receivable_growth"]-facts["revenue_growth"]
            facts["inventory_growth_gap"] = None if facts.get("inventory_growth") is None or facts.get("revenue_growth") is None else facts["inventory_growth"]-facts["revenue_growth"]
        model_input=current|{"working_capital":metrics["working_capital"].value,"ebit":current.get("ebit",current.get("operating_income"))}
        models=[altman_z(model_input,"bank" if entity_type in {"bank","financial_institution"} else "public_manufacturer")]
        if previous: models += [beneish_m(current,previous),piotroski_f(current,previous)]
        models += [ohlson_o(model_input)]
        models = enforce_applicability(models, entity_type, model_input | current)
        model_metric_names={"Altman Z-Score":"altman_z_score","Beneish M-Score":"beneish_m_score","Piotroski F-Score":"piotroski_f_score","Ohlson O-Score":"ohlson_o_score"}
        for model in models:facts[model_metric_names[model.name]]=model.output
        ohlson=next(m for m in models if m.name=="Ohlson O-Score")
        facts["ohlson_probability"]=ohlson.derived_outputs.get("probability")
        claims=self.provider.extract(pages,document,year) if pages else []
        verified=[]; accepted=[]
        for claim in claims:
            ev=self.verifier.verify(claim.evidence,pages); verified.append(ev)
            if ev.verified: claim.evidence=ev; accepted.append(claim)
        facts.update({"going_concern_doubt":any(c.risk_category=="going_concern" and c.polarity=="negative" for c in accepted),"material_weakness":any("material weakness" in c.claim.lower() and c.polarity=="negative" for c in accepted),"refinancing_dependency":any("refinancing" in c.claim.lower() and c.polarity=="negative" for c in accepted)})
        signals=self.rules.evaluate(facts)
        ops={"<":lambda a,b:a<b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,">=":lambda a,b:a>=b}
        for mapping in self.model_scoring["mappings"]:
            value=facts.get(mapping["metric"])
            if value is not None and ops[mapping["operator"]](value,mapping["threshold"]):
                model=next(m for m in models if m.name==mapping["model"])
                refs=[]
                for key in model.inputs:refs.extend(source_map.get(key,[]))
                signals.append(RuleSignal(mapping["id"],mapping["category"],"model",mapping["delta"],f'{mapping["model"]} crossed configured risk threshold; model limitations still apply.',[f'{mapping["metric"]}={value} {mapping["operator"]} {mapping["threshold"]}'],refs,family=f'model:{mapping["model"]}'))
        for signal in signals:
            keys=[item.split("=",1)[0] for item in signal.evidence]
            refs=list(signal.source_refs)
            for key in keys:
                refs.extend(source_map.get(key,[]))
                if key in metrics:refs.extend(metrics[key].source_refs)
            signal.source_refs=list({(e.document,e.page,e.source_text):e for e in refs}.values())
        contradictions=detect_contradictions(accepted,facts)
        score,level,dimensions=aggregate(signals,contradictions,self.scoring)
        missing=[f"{m.name}: N/A — {m.missing_reason} Impact: assessment confidence reduced." for m in metrics.values() if m.value is None]
        numeric_evidence=[e for refs in source_map.values() for e in refs]
        conf=confidence(current,verified,models,previous is not None,numeric_evidence)
        components=confidence_components(current,verified,models,previous is not None,numeric_evidence)
        nodes=[];edges=[]
        for key,refs in source_map.items():
            for i,e in enumerate(refs):nodes.append({"id":f"value:{key}:{i}","type":"financial_value","label":key,"document":e.document,"page":e.page,"status":e.verification_status})
        for name,m in metrics.items():
            nodes.append({"id":f"metric:{name}","type":"metric","label":name,"formula":m.formula})
            for key in m.inputs:
                for i,_ in enumerate(source_map.get(key,[])):edges.append({"from":f"value:{key}:{i}","to":f"metric:{name}","relation":"input_to"})
        for model in models:
            model_id="model:"+model.name.lower().replace(" ","_")
            nodes.append({"id":model_id,"type":"model","label":model.name,"applicability":model.applicability})
            for key in model.inputs:
                for i,_ in enumerate(source_map.get(key,[])):edges.append({"from":f"value:{key}:{i}","to":model_id,"relation":"model_input"})
        for s in signals:
            nodes.append({"id":f"signal:{s.rule_id}","type":"signal","label":s.rule_id})
            if s.rule_id.startswith("MODEL_"):
                model_name=next((m["model"] for m in self.model_scoring["mappings"] if m["id"]==s.rule_id),None)
                if model_name:edges.append({"from":"model:"+model_name.lower().replace(" ","_"),"to":f"signal:{s.rule_id}","relation":"mapped_to"})
            for key in [x.split("=",1)[0] for x in s.evidence]:
                target=f"metric:{key}" if key in metrics else None
                if target:edges.append({"from":target,"to":f"signal:{s.rule_id}","relation":"triggers"})
            edges.append({"from":f"signal:{s.rule_id}","to":f"dimension:{s.category}","relation":"contributes_to"})
        for i,claim in enumerate(accepted):nodes.append({"id":f"claim:{i}","type":"claim","label":claim.claim,"page":claim.evidence.page})
        for i,c in enumerate(contradictions):
            nodes.append({"id":f"contradiction:{i}","type":"contradiction","label":c.category})
            edges.append({"from":f"claim:{accepted.index(next(x for x in accepted if x.claim==c.management_claim))}","to":f"contradiction:{i}","relation":"claim_input"})
            edges.append({"from":f"contradiction:{i}","to":f"dimension:{c.category}","relation":"contributes_to"})
        for category in dimensions:nodes.append({"id":f"dimension:{category}","type":"dimension","label":category});edges.append({"from":f"dimension:{category}","to":"overall","relation":"weighted_into"})
        nodes.append({"id":"overall","type":"assessment","label":"overall risk"})
        graph={"nodes":nodes,"edges":edges}
        return Assessment(company,str(year),score,level,conf,dimensions,metrics,models,signals,contradictions,missing,confidence_components=components,evidence_graph=graph)
