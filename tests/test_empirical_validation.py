from __future__ import annotations

import csv
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from finrisk.empirical_validation import (
    PointInTimeGuard,
    benchmark_readiness,
    calibration_eligibility,
    company_clustered_bootstrap_delta,
    empirical_binary_metrics,
    extraction_gold_metrics,
    freeze_experiment,
    independent_label_report,
    structured_error_cases,
    tension_research_label,
    validate_dataset_integrity,
    verify_experiment_freeze,
)


def test_benchmark_readiness_is_dependency_scoped():
    status = benchmark_readiness({
        "NUMERIC_READY": "VERIFIED", "LABEL_READY": "VERIFIED", "TEMPORAL_READY": "VERIFIED",
        "DOCUMENT_READY": "INSUFFICIENT_DATA", "EVIDENCE_READY": "INSUFFICIENT_DATA",
        "AGENT_READY": "BLOCKED_EXTERNAL_DEPENDENCY",
    })
    assert status["B0_RATIOS_ONLY"]["status"] == "READY"
    assert status["B2_RULES_ONLY"]["status"] == "READY"
    assert status["B6_NUMERIC_TEMPORAL"]["status"] == "READY"
    assert status["B3_LLM_AGENT_ONLY"]["status"] == "BLOCKED_EXTERNAL_DEPENDENCY"

ROOT = Path(__file__).resolve().parents[1]


def observation(identifier: str = "aaa-2023", cik: str = "1", split: str = "train") -> dict:
    return {
        "observation_id": identifier,
        "ticker": identifier.split("-")[0].upper(),
        "cik": cik,
        "sector": "Industrials",
        "fiscal_year": 2023,
        "period_end": "2023-12-31",
        "filing_date": "2024-02-01",
        "accession": f"000-{identifier}",
        "source_url": "https://www.sec.gov/example",
        "source_hash": "a" * 64,
        "source_available_time": "2024-02-01T23:59:59Z",
        "information_cutoff": "2024-02-01T23:59:59Z",
        "outcome_window_end": "2025-02-01",
        "split": split,
        "annotation_status": "pending",
        "label_generated_by": "independent_reviewers",
        "system_score_used_as_label": False,
    }


def test_point_in_time_guard_is_fail_closed() -> None:
    guard = PointInTimeGuard()
    assert guard.admits("2024-01-31", "2024-02-01")
    assert not guard.admits("2024-02-01T23:00:00Z", "2024-02-01T00:00:00Z")
    with pytest.raises(ValueError, match="missing"):
        guard.require({}, "2024-02-01")
    with pytest.raises(ValueError, match="future"):
        guard.require({"source_available_time": "2024-02-02"}, "2024-02-01")


def test_integrity_accepts_company_disjoint_rows_and_counts_splits() -> None:
    report = validate_dataset_integrity(
        [observation(), observation("bbb-2023", "2", "validation")]
    )
    assert report["gate"] == "PASS"
    assert report["company_overlap_count"] == 0
    assert report["split_company_counts"]["train"] == 1


def test_integrity_rejects_empty_dataset() -> None:
    report = validate_dataset_integrity([])
    assert report["gate"] == "STOP"
    assert report["errors"] == [{"row": None, "code": "EMPTY_DATASET"}]


def test_integrity_rejects_cross_filing_fact_provenance() -> None:
    row = observation()
    row["facts"] = {"revenue": 1.0}
    row["fact_provenance"] = {
        "revenue": {
            "concept": "Revenues",
            "unit": "USD",
            "source_row": {
                "adsh": "wrong-accession",
                "ddate": "20231231",
                "tag": "Revenues",
                "uom": "USD",
                "coreg": "",
                "segments": "",
            }
        }
    }
    report = validate_dataset_integrity([row])
    assert report["gate"] == "STOP"
    assert "FACT_ACCESSION_MISMATCH" in {error["code"] for error in report["errors"]}


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda rows: rows.append(deepcopy(rows[0])), "DUPLICATE_OBSERVATION"),
        (lambda rows: rows[0].update(source_hash="bad"), "MISSING_OR_INVALID_HASH"),
        (lambda rows: rows[0].pop("sector"), "SCHEMA_ERROR"),
        (lambda rows: rows[0].update(source_available_time="2024-03-01"), "INVALID_OR_FUTURE_AVAILABILITY"),
        (lambda rows: rows[0].update(filing_date="2024-03-01"), "FUTURE_FILING_LEAKAGE"),
        (lambda rows: rows[0].update(label_generated_by="finrisk"), "LABEL_CONTAMINATION"),
        (lambda rows: rows[0].update(label_available_at="2024-01-01"), "OUTCOME_AVAILABLE_AT_PREDICTION"),
    ],
)
def test_integrity_gate_stops_known_failures(mutate, code: str) -> None:
    rows = [observation()]
    mutate(rows)
    report = validate_dataset_integrity(rows)
    assert report["gate"] == "STOP"
    assert code in {error["code"] for error in report["errors"]}


def test_integrity_rejects_company_split_overlap_and_future_restatement() -> None:
    first = observation()
    second = observation("aaa-2022", "1", "test")
    second.update(
        restatement_filed_at="2024-03-01",
        restatement_used_in_features=True,
    )
    codes = {item["code"] for item in validate_dataset_integrity([first, second])["errors"]}
    assert {"COMPANY_SPLIT_OVERLAP", "FUTURE_RESTATEMENT_LEAKAGE"} <= codes


def test_calibration_guardrail_distinguishes_ranking_from_probability() -> None:
    assert calibration_eligibility({"case_control_sampling": True})["status"] == "RANKING_ONLY"
    eligible = calibration_eligibility({"population_prevalence_preserved": True})
    assert eligible["status"] == "ELIGIBLE"
    assert eligible["warning"] is None


def test_independent_extraction_gold_and_error_taxonomy() -> None:
    rows = [
        {"review_status": "adjudicated", "gold_source": "annual_report", "gold_value": 10,
         "gold_unit": "USDm", "gold_fiscal_year": 2023, "predicted_value": 10,
         "predicted_unit": "USDm", "predicted_fiscal_year": 2023},
        {"review_status": "adjudicated", "gold_source": "annual_report", "gold_value": 20,
         "gold_unit": "USDm", "gold_fiscal_year": 2023, "predicted_value": 20,
         "predicted_unit": "USD", "predicted_fiscal_year": 2023, "error_category": "unit"},
        {"review_status": "adjudicated", "gold_source": "system", "gold_value": 1},
    ]
    metrics = extraction_gold_metrics(rows)
    assert metrics["n"] == 2
    assert metrics["exact_accuracy"] == 0.5
    assert metrics["error_categories"] == {"unit": 1}


def test_independent_label_report_requires_complete_dual_review() -> None:
    complete = {
        "review_status": "adjudicated", "reviewer_a_label": "1", "reviewer_a_source": "source-a",
        "reviewer_b_label": "1", "reviewer_b_source": "source-b", "adjudicated_label": "1",
        "adjudicator_source": "source-c", "label_generated_by": "human_review",
    }
    report = independent_label_report([complete])
    assert report["status"] == "READY"
    assert report["percent_agreement"] == 1
    assert report["human_adjudicated_count"] == 1
    machine = dict(complete, label_generated_by="machine_review")
    assert independent_label_report([machine])["status"] == "MACHINE_REVIEW_ONLY"
    incomplete = dict(complete, reviewer_b_source="")
    report = independent_label_report([incomplete])
    assert report["status"] == "NOT AVAILABLE"
    assert report["errors"][0]["code"] == "INCOMPLETE_ADJUDICATION"


def test_empirical_metrics_and_clustered_bootstrap_are_reproducible() -> None:
    rows = [
        {"company_id": "a", "label": 0, "score": 0.1, "prediction": 0, "base": 0, "new": 0},
        {"company_id": "a", "label": 1, "score": 0.8, "prediction": 1, "base": 0, "new": 1},
        {"company_id": "b", "label": 0, "score": 0.3, "prediction": 0, "base": 1, "new": 0},
        {"company_id": "b", "label": 1, "score": 0.9, "prediction": 1, "base": 1, "new": 1, "abstained": True},
    ]
    metrics = empirical_binary_metrics(rows)
    assert metrics["auroc"] == 1
    assert metrics["false_negative_rate"] == 0
    assert metrics["coverage"] == 0.75

    def accuracy(sample: list[dict]) -> float:
        return sum(row["prediction"] == row["label"] for row in sample) / len(sample)

    one = company_clustered_bootstrap_delta(rows, accuracy, "base", "new", samples=100, seed=7)
    two = company_clustered_bootstrap_delta(rows, accuracy, "base", "new", samples=100, seed=7)
    assert one == two
    assert one["cluster_count"] == 2
    assert one["status"] == "CI_NOT_ESTIMABLE"
    assert one["valid_replicates"] + one["invalid_replicates"] == 100


def test_clustered_bootstrap_rejects_single_class_replicates() -> None:
    rows = [{"company_id": "a", "label": 0, "prediction": 0, "base": 0, "new": 0}]

    def accuracy(sample: list[dict]) -> float:
        return sum(row["prediction"] == row["label"] for row in sample) / len(sample)

    result = company_clustered_bootstrap_delta(rows, accuracy, "base", "new", samples=25, seed=1)
    assert result["status"] == "CI_NOT_ESTIMABLE"
    assert result["invalid_replicates"] == 25


def test_error_analysis_freeze_and_tension_mapping() -> None:
    errors = structured_error_cases([
        {"observation_id": "a", "prediction": 0, "label": 1, "error_category": "FUSION_ERROR"},
        {"observation_id": "b", "prediction": 1, "label": 0, "error_category": "unknown"},
        {"observation_id": "c", "prediction": 1, "label": 1},
    ])
    assert [item["error_type"] for item in errors] == ["FN", "FP"]
    assert errors[1]["category"] == "LABEL_AMBIGUITY"
    assert tension_research_label("Material Contradiction") == "CONTRADICTION"
    with pytest.raises(ValueError):
        tension_research_label("invented")

    configuration = {
        "dataset_hash": "d", "split_hash": "s", "rule_version": "r",
        "model_config": {}, "fusion_config": {}, "prompt_version": "p",
        "llm_model": "NOT_CONFIGURED", "label_schema_hash": "l",
        "random_seed": 7, "git_commit": "abc",
    }
    frozen = freeze_experiment(configuration)
    assert verify_experiment_freeze(frozen)
    frozen["random_seed"] = 8
    assert not verify_experiment_freeze(frozen)
    with pytest.raises(ValueError, match="missing"):
        freeze_experiment({})


def test_preregistered_acquisition_plan_is_30_by_3_and_company_disjoint() -> None:
    plan = list(csv.DictReader((ROOT / "research/empirical_v1/acquisition_plan.csv").open(encoding="utf-8")))
    assert len(plan) == 90
    company_splits: dict[str, set[str]] = {}
    for row in plan:
        company_splits.setdefault(row["ticker"], set()).add(row["split"])
        assert row["included_in_benchmark"] == "false"
    assert all(len(splits) == 1 for splits in company_splits.values())
    assert {split: sum(next(iter(v)) == split for v in company_splits.values()) for split in ("train", "validation", "test")} == {"train": 18, "validation": 6, "test": 6}


def test_acquisition_helpers_filter_future_facts_and_choose_earliest_filing() -> None:
    spec = importlib.util.spec_from_file_location("acquire_empirical", ROOT / "scripts/acquire_empirical_corpus.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = {"facts": {"us-gaap": {"Revenue": {"units": {"USD": [
        {"filed": "2024-01-01", "val": 1}, {"filed": "2024-03-01", "val": 2}
    ]}}}}}
    filtered = module.pit_companyfacts(payload, "2024-02-01")
    assert [item["val"] for item in filtered["facts"]["us-gaap"]["Revenue"]["units"]["USD"]] == [1]
    submissions = {"filings": {"recent": {
        "form": ["10-K/A", "10-K"], "reportDate": ["2023-12-31", "2023-12-31"],
        "accessionNumber": ["amended", "original"], "primaryDocument": ["a.htm", "o.htm"],
        "filingDate": ["2024-03-01", "2024-02-01"],
    }}}
    assert module.annual_filing(submissions, 2023)["accession"] == "original"


def test_reviewer_b_replacement_is_candidate_blind() -> None:
    path = ROOT / "research/empirical_v1/machine_reviews/reviewer_b_independent.json"
    review = json.loads(path.read_text(encoding="utf-8"))
    assert review["reviewer_type"] == "MACHINE_REVIEWED"
    assert review["candidate_labels_seen"] is False
    assert review["other_reviewer_outputs_seen"] is False
    assert review["record_count"] == 90
    assert all(record["status"] == "MACHINE_REVIEW" for record in review["records"])
# Historical snapshot-only assertions are replaced by the E4 public release gate.
