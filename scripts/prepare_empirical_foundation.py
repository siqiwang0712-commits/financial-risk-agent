from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "research/benchmark/candidate_registry_30.csv"
OUTPUT = ROOT / "research/empirical_v1"
YEARS = (2021, 2022, 2023)


def main() -> None:
    candidates = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
    if len(candidates) != 30:
        raise SystemExit("pre-registered registry must contain exactly 30 companies")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    plans = []
    for index, company in enumerate(candidates):
        split = "train" if index < 18 else "validation" if index < 24 else "test"
        for year in YEARS:
            plans.append(
                {
                    "observation_id": f"{company['ticker'].lower()}-{year}",
                    "ticker": company["ticker"],
                    "sector": company["sector"],
                    "fiscal_year": year,
                    "split": split,
                    "acquisition_status": "NOT AVAILABLE",
                    "annotation_status": "pending",
                    "included_in_benchmark": "false",
                }
            )
    with (OUTPUT / "acquisition_plan.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(plans[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(plans)
    annotation_fields = [
        "observation_id", "endpoint", "reviewer_a_label", "reviewer_a_source",
        "reviewer_b_label", "reviewer_b_source", "disagreement", "adjudicated_label",
        "adjudicator_source", "review_status", "label_generated_by", "label_schema_version",
        "information_cutoff", "outcome_window_end", "evidence_event_date", "evidence_available_at",
        "evidence_locator", "evidence_hash", "reviewer_a_reason", "reviewer_b_reason",
        "packet_hash", "reviewer_a_run_id", "reviewer_b_run_id", "adjudicator_run_id",
    ]
    with (OUTPUT / "outcome_annotations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=annotation_fields, lineterminator="\n")
        writer.writeheader()
        for item in plans:
            for endpoint in ("hard_distress_12m", "financial_deterioration_12m"):
                writer.writerow({"observation_id": item["observation_id"], "endpoint": endpoint, "review_status": "pending", "label_schema_version": "finrisk-forward-label-v1.0.0"})
    gold_fields = ["observation_id", "field", "gold_value", "gold_unit", "gold_fiscal_year", "gold_source", "reviewer_a", "reviewer_b", "adjudicated_value", "review_status", "error_category"]
    with (OUTPUT / "extraction_gold.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=gold_fields, lineterminator="\n").writeheader()
    plan_bytes = (OUTPUT / "acquisition_plan.csv").read_bytes()
    status = {
        "dataset": "FinRisk Evaluation Corpus v1",
        "target_observations": 90,
        "planned_companies": 30,
        "planned_periods_per_company": 3,
        "real_observations_acquired": 0,
        "adjudicated_outcome_labels": 0,
        "adjudicated_extraction_fields": 0,
        "status": "NOT AVAILABLE",
        "blocking_reasons": ["SEC_USER_AGENT not configured", "independent reviewers not available"],
        "registry_sha256": hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
        "split_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "claim": "This is an acquisition and annotation plan, not a real corpus manifest.",
    }
    (OUTPUT / "corpus_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    configurations = {
        "status": "NOT RUN",
        "common_information_set": "PIT-admitted filing evidence available at each observation cutoff",
        "configurations": [
            "B0_RATIOS_ONLY", "B1_LOGISTIC_REGRESSION", "B2_RULES_ONLY", "B3_LLM_ONLY",
            "B4_EXISTING_HYBRID", "B5_EVIDENCE_VERIFICATION", "B6_TEMPORAL_RISK",
            "B7_SELECTIVE_PREDICTION", "B8_CRITIC_VERIFIER",
        ],
        "fairness_constraint": "same observation, cutoff and available filing information",
    }
    (OUTPUT / "benchmark_configurations.json").write_text(json.dumps(configurations, indent=2), encoding="utf-8")
    def file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        git_commit = "NOT_AVAILABLE"
    experiment = {
        "experiment_version": "empirical-v1-draft",
        "status": "BLOCKED_NOT_FROZEN",
        "immutable": False,
        "dataset_hash": "NOT_AVAILABLE",
        "split_hash": status["split_plan_sha256"],
        "rule_version": file_hash(ROOT / "rules/rules.json"),
        "model_config": {"traditional_ml": "logistic_regression", "fitted": False},
        "fusion_config": {"source": "config/decision_policy.json", "hash": file_hash(ROOT / "config/decision_policy.json")},
        # Must match StructuredLLMProvider.PROMPT_VERSION; a mismatch would make the
        # manifest claim a prompt that never produced the results.
        "prompt_version": "narrative-v1.2.0-untrusted-data-delimited",
        "llm_model": "NOT_CONFIGURED",
        "label_schema_hash": file_hash(ROOT / "research/label_schema.json"),
        "random_seed": 20260907,
        "git_commit": git_commit,
        "blocking_reasons": status["blocking_reasons"],
        "note": "A true immutable experiment hash is created only after corpus and independent labels pass integrity gates.",
    }
    (OUTPUT / "experiment_manifest.draft.json").write_text(json.dumps(experiment, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
