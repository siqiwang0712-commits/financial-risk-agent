from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .pipeline import FinRiskPipeline

BASELINES=("llm_only","ratios_only","rules_only","models_only","full_hybrid","hybrid_without_narrative","hybrid_without_trends")

def load_manifest(path:Path)->list[dict[str,Any]]:
    data=json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind")!="synthetic_smoke" or not isinstance(data.get("examples"),list):raise ValueError("manifest must be an explicitly synthetic smoke dataset")
    return data["examples"]

def run_manifest(manifest:Path,root:Path)->list[dict[str,Any]]:
    pipeline=FinRiskPipeline(root);rows=[]
    for entry in load_manifest(manifest):
        data=json.loads((root/entry["path"]).read_text(encoding="utf-8"))
        pages={int(k):v for k,v in data.get("pages",{}).items()}
        for baseline in BASELINES:
            previous=None if baseline=="hybrid_without_trends" else data.get("previous")
            used_pages={} if baseline in {"ratios_only","rules_only","models_only","hybrid_without_narrative"} else pages
            assessment=pipeline.assess(data["company"],data["fiscal_year"],data["current"],previous,used_pages,"Synthetic fixture")
            if baseline=="llm_only":output={"verified_claim_count":len([n for n in assessment.evidence_graph["nodes"] if n["type"]=="claim"])}
            elif baseline=="ratios_only":output={"available_metric_count":sum(m.value is not None for m in assessment.metrics.values())}
            elif baseline=="rules_only":output={"rule_ids":[s.rule_id for s in assessment.triggered_rules if not s.rule_id.startswith("MODEL_")]}
            elif baseline=="models_only":output={"models":{m.name:m.output for m in assessment.models}}
            else:output={"overall_score":assessment.overall_score,"risk_level":assessment.risk_level,"coverage":assessment.confidence}
            rows.append({"dataset_kind":"synthetic_smoke","example_id":entry["id"],"baseline":baseline,"output":output})
    return rows

def write_jsonl(rows:list[dict],path:Path)->None:
    path.write_text("".join(json.dumps(row,sort_keys=True)+"\n" for row in rows),encoding="utf-8")
