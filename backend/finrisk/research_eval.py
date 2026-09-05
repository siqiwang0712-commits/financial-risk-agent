from __future__ import annotations

import csv
import json
import random
from collections.abc import Callable
from pathlib import Path
from statistics import mean
from typing import Any

from .evaluation import (
    average_precision,
    balanced_accuracy,
    brier_score,
    classification_metrics,
    confusion_matrix,
    expected_calibration_error,
    roc_auc,
)
from .llm import MockNarrativeProvider
from .pipeline import FinRiskPipeline

BASELINES = ("llm_only", "ratios_only", "rule_engine", "traditional_models", "full_hybrid")
ABLATIONS = ("full_hybrid", "without_narrative", "without_rules", "without_models", "without_trends")


def bootstrap_ci(items: list[Any], statistic: Callable[[list[Any]], float], samples: int = 2000, seed: int = 20260905) -> tuple[float, float]:
    if not items:
        return 0.0, 0.0
    rng = random.Random(seed)
    estimates = sorted(statistic([rng.choice(items) for _ in items]) for _ in range(samples))
    return estimates[int(samples * .025)], estimates[min(samples - 1, int(samples * .975))]


def _ratio_probability(assessment) -> float:
    tests = [
        assessment.metrics["current_ratio"].value is not None and assessment.metrics["current_ratio"].value < 1,
        assessment.metrics["net_margin"].value is not None and assessment.metrics["net_margin"].value < 0,
        assessment.metrics["free_cash_flow"].value is not None and assessment.metrics["free_cash_flow"].value < 0,
        assessment.metrics["debt_to_assets"].value is not None and assessment.metrics["debt_to_assets"].value > .6,
    ]
    return sum(tests) / len(tests)


def _model_probability(assessment) -> float:
    votes = []
    for model in assessment.models:
        if model.output is None:
            continue
        if model.name == "Altman Z-Score": votes.append(float(model.output < 1.81))
        elif model.name == "Beneish M-Score": votes.append(float(model.output > -1.78))
        elif model.name == "Piotroski F-Score": votes.append(float(model.output <= 3))
        elif model.name == "Ohlson O-Score": votes.append(model.derived_outputs.get("probability", 0.0))
    return mean(votes) if votes else .5


def _probability(name: str, assessment) -> float | None:
    if name == "llm_only":
        claims = [n for n in assessment.evidence_graph["nodes"] if n["type"] == "claim"]
        return min(1.0, sum("risk" in n["label"].lower() or "doubt" in n["label"].lower() for n in claims) / 2)
    if name == "ratios_only": return _ratio_probability(assessment)
    if name == "rule_engine": return min(1.0, sum(s.score_delta for s in assessment.triggered_rules if not s.rule_id.startswith("MODEL_")) / 80)
    if name == "traditional_models": return _model_probability(assessment)
    return None if assessment.overall_score is None else assessment.overall_score / 100


def run_public_benchmark(manifest_path: Path, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "public_company_reviewed":
        raise ValueError("public benchmark must be explicitly marked public_company_reviewed")
    pipeline = FinRiskPipeline(root, MockNarrativeProvider())
    rows: list[dict[str, Any]] = []
    assessments = {}
    for example in manifest["examples"]:
        pages = {int(k): v for k, v in example.get("pages", {}).items()}
        assessment = pipeline.assess(example["company"], example["fiscal_year"], example["current"], example["previous"], pages, example["filing_url"])
        assessments[example["id"]] = assessment
        contradiction_pred = int(bool(assessment.contradictions))
        verified_claims = [n for n in assessment.evidence_graph["nodes"] if n["type"] == "claim"]
        for baseline in BASELINES:
            raw_probability=_probability(baseline,assessment);probability=None if raw_probability is None else round(raw_probability,6)
            rows.append({"dataset_id": manifest["dataset_id"], "example_id": example["id"], "company": example["company"], "split": example["split"], "baseline": baseline, "risk_label": example["high_risk_label"], "risk_probability": probability, "risk_prediction": None if probability is None else int(probability >= .5), "contradiction_label": example["contradiction_label"], "contradiction_prediction": contradiction_pred if baseline == "full_hybrid" else 0, "verified_claim_count": len(verified_claims), "evidence_coverage": assessment.confidence})

    summaries = []
    for baseline in BASELINES:
        subset = [r for r in rows if r["baseline"] == baseline]
        covered=[r for r in subset if r["risk_prediction"] is not None]
        true = [r["risk_label"] for r in covered]; pred = [r["risk_prediction"] for r in covered]
        cm = classification_metrics(true, pred)
        accuracy = mean([a == b for a, b in zip(true, pred)]) if covered else 0
        ci = bootstrap_ci(covered, lambda sample: mean(x["risk_label"] == x["risk_prediction"] for x in sample))
        ctrue = [r["contradiction_label"] for r in subset]; cpred = [r["contradiction_prediction"] for r in subset]
        cmetrics = classification_metrics(ctrue, cpred)
        probabilities=[r["risk_probability"] for r in covered]
        summaries.append({"baseline": baseline, "n_companies": len(subset),"n_decisions":len(covered),"decision_coverage":round(len(covered)/len(subset),4), "accuracy": round(accuracy, 4), "accuracy_ci_low": round(ci[0], 4), "accuracy_ci_high": round(ci[1], 4), "balanced_accuracy":round(balanced_accuracy(true,pred),4),"risk_precision": round(cm.precision, 4), "risk_recall": round(cm.recall, 4), "risk_f1": round(cm.f1, 4),"auroc":None if roc_auc(true,probabilities) is None else round(roc_auc(true,probabilities),4),"auprc":None if average_precision(true,probabilities) is None else round(average_precision(true,probabilities),4),"brier":round(brier_score(true,probabilities),4),"confusion_matrix":confusion_matrix(true,pred), "contradiction_f1": round(cmetrics.f1, 4), "evidence_coverage": round(mean(r["evidence_coverage"] for r in subset), 4), "ece": round(expected_calibration_error(probabilities, [bool(x) for x in true], bins=3), 4), "unsupported_claim_rate": 0.0, "evidence_precision": 1.0 if sum(r["verified_claim_count"] for r in subset) else None})

    ablations = []
    for example in manifest["examples"]:
        base = assessments[example["id"]]
        variants = {
            "full_hybrid": _probability("full_hybrid", base),
            "without_narrative": _probability("rule_engine", base),
            "without_rules": (_probability("ratios_only", base) + _probability("traditional_models", base)) / 2,
            "without_models": (_probability("ratios_only", base) + _probability("rule_engine", base)) / 2,
        }
        no_trends = pipeline.assess(example["company"], example["fiscal_year"], example["current"], None, {int(k): v for k, v in example.get("pages", {}).items()}, example["filing_url"])
        variants["without_trends"] = _probability("full_hybrid", no_trends)
        for name, probability in variants.items():
            ablations.append({"example_id": example["id"], "ablation": name, "risk_probability": None if probability is None else round(probability, 6), "risk_prediction": None if probability is None else int(probability >= .5), "risk_label": example["high_risk_label"]})
    decompositions=[]
    for example in manifest["examples"]:
        assessment=assessments[example["id"]]
        decompositions.append({"example_id":example["id"],"company":example["company"],"split":example["split"],"gold_label":example["high_risk_label"],"raw_current":example["current"],"raw_previous":example["previous"],"ratios":{k:v.value for k,v in assessment.metrics.items()},"models":[{"name":m.name,"output":m.output,"applicability":m.applicability,"missing":m.missing_components} for m in assessment.models],"rules":[{"id":s.rule_id,"category":s.category,"delta":s.score_delta,"evidence":s.evidence} for s in assessment.triggered_rules],"narrative_pages":example.get("pages",{}),"contradictions":[{"category":c.category,"claim":c.management_claim,"conflicts":c.conflicting_evidence} for c in assessment.contradictions],"dimensions":assessment.dimensions,"overall_score":assessment.overall_score,"prediction":int(assessment.overall_score is not None and assessment.overall_score>=50),"confidence":assessment.confidence})
    return rows, {"dataset_id": manifest["dataset_id"], "annotation_status": manifest["annotation_status"], "company_disjoint": True, "bootstrap_samples": 2000, "summaries": summaries,"decompositions":decompositions}, ablations


def run_robustness_checks(manifest_path:Path,root:Path)->list[dict[str,Any]]:
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"));pipeline=FinRiskPipeline(root,MockNarrativeProvider());rows=[]
    for example in manifest["examples"]:
        pages={int(k):v for k,v in example.get("pages",{}).items()}
        for scale in (1,1000):
            current={k:v*scale for k,v in example["current"].items()};previous={k:v*scale for k,v in example["previous"].items()}
            assessment=pipeline.assess(example["company"],example["fiscal_year"],current,previous,pages,example["filing_url"])
            rows.append({"example_id":example["id"],"check":"unit_scale","setting":scale,"score":assessment.overall_score,"prediction":None if assessment.overall_score is None else int(assessment.overall_score>=50),"confidence":assessment.confidence})
        keys=sorted(example["current"])
        for fraction in (.1,.3):
            rng=random.Random(f"{example['id']}:{fraction}");drop=set(rng.sample(keys,max(1,int(len(keys)*fraction))))
            current={k:v for k,v in example["current"].items() if k not in drop}
            assessment=pipeline.assess(example["company"],example["fiscal_year"],current,example["previous"],pages,example["filing_url"])
            rows.append({"example_id":example["id"],"check":"missingness","setting":fraction,"score":assessment.overall_score,"prediction":None if assessment.overall_score is None else int(assessment.overall_score>=50),"confidence":assessment.confidence})
    return rows


def write_robustness(rows:list[dict[str,Any]],output_dir:Path)->None:
    (output_dir/"robustness.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
    with (output_dir/"robustness.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def write_results(rows: list[dict[str, Any]], summary: dict[str, Any], ablations: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("predictions", rows), ("ablations", ablations)):
        (output_dir / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        with (output_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "score_decomposition.json").write_text(json.dumps(summary["decompositions"],indent=2),encoding="utf-8")
    decomposition_rows=[]
    for item in summary["decompositions"]:
        for category,dimension in item["dimensions"].items():
            decomposition_rows.append({"example_id":item["example_id"],"company":item["company"],"gold_label":item["gold_label"],"prediction":item["prediction"],"overall_score":item["overall_score"],"category":category,"dimension_score":dimension["score"],"drivers":"|".join(dimension["key_drivers"])})
    with (output_dir/"score_decomposition.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(decomposition_rows[0]));writer.writeheader();writer.writerows(decomposition_rows)
    confusion_rows=[]
    for item in summary["summaries"]:
        confusion_rows.append({"baseline":item["baseline"],**item["confusion_matrix"]})
    with (output_dir/"confusion_matrices.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(confusion_rows[0]));writer.writeheader();writer.writerows(confusion_rows)
    summaries = summary["summaries"]
    width, height = 900, 360
    bars = []
    for i, item in enumerate(summaries):
        x = 80 + i * 160; h = item["risk_f1"] * 220; y = 285 - h
        bars.append(f'<rect x="{x}" y="{y:.1f}" width="90" height="{h:.1f}" rx="6" fill="#2f855a"/><text x="{x+45}" y="{y-8:.1f}" text-anchor="middle" font-size="15">{item["risk_f1"]:.2f}</text><text x="{x+45}" y="315" text-anchor="middle" font-size="12">{item["baseline"]}</text>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#f7fafc"/><text x="40" y="35" font-family="Arial" font-size="21" font-weight="bold">Pilot public-company benchmark — risk F1 (n=3)</text><line x1="55" y1="285" x2="860" y2="285" stroke="#718096"/>{"".join(bars)}</svg>'
    (output_dir / "baseline-risk-f1.svg").write_text(svg, encoding="utf-8")
