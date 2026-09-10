from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from .evaluation import (
    average_precision,
    balanced_accuracy,
    classification_metrics,
    roc_auc,
)

REQUIRED_OBSERVATION_FIELDS = {
    "observation_id",
    "ticker",
    "cik",
    "sector",
    "fiscal_year",
    "period_end",
    "filing_date",
    "accession",
    "source_url",
    "source_hash",
    "source_available_time",
    "information_cutoff",
    "outcome_window_end",
    "split",
    "annotation_status",
}
ALLOWED_SPLITS = {"train", "validation", "test"}
SYSTEM_LABEL_SOURCES = {"finrisk", "model", "system", "prediction"}

BENCHMARK_REQUIREMENTS = {
    "B0_RATIOS_ONLY": {"NUMERIC_READY", "LABEL_READY"},
    "B1_LOGISTIC_REGRESSION": {"NUMERIC_READY", "LABEL_READY"},
    "B2_RULES_ONLY": {"NUMERIC_READY", "LABEL_READY"},
    "B3_LLM_AGENT_ONLY": {"DOCUMENT_READY", "LABEL_READY", "AGENT_READY"},
    "B4_EXISTING_HYBRID": {"NUMERIC_READY", "DOCUMENT_READY", "LABEL_READY"},
    "B5_EVIDENCE_VERIFICATION": {"DOCUMENT_READY", "EVIDENCE_READY", "LABEL_READY"},
    "B6_NUMERIC_TEMPORAL": {"TEMPORAL_READY", "NUMERIC_READY", "LABEL_READY"},
    "B7_SELECTIVE_PREDICTION": {"BASE_PREDICTION_READY", "RELIABILITY_READY"},
    "B8_CRITIC_VERIFIER": {"DOCUMENT_READY", "EVIDENCE_READY", "AGENT_READY", "LABEL_READY"},
}


def benchmark_readiness(capabilities: dict[str, str]) -> dict[str, dict[str, Any]]:
    ready_values = {"VERIFIED", "EMPIRICALLY_RUN"}
    result = {}
    for benchmark, requirements in BENCHMARK_REQUIREMENTS.items():
        missing = sorted(key for key in requirements if capabilities.get(key) not in ready_values)
        result[benchmark] = {
            "status": "READY" if not missing else "BLOCKED_EXTERNAL_DEPENDENCY" if any(
                capabilities.get(key) == "BLOCKED_EXTERNAL_DEPENDENCY" for key in missing
            ) else "INSUFFICIENT_DATA",
            "missing_capabilities": missing,
        }
    return result


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class PointInTimeGuard:
    @staticmethod
    def _instant(value: str) -> datetime:
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def admits(source_available_time: str, information_cutoff: str) -> bool:
        return PointInTimeGuard._instant(source_available_time) <= PointInTimeGuard._instant(information_cutoff)

    def require(self, evidence: dict[str, Any], information_cutoff: str) -> None:
        available = evidence.get("source_available_time")
        if not available:
            raise ValueError("evidence missing source_available_time")
        if not self.admits(available, information_cutoff):
            raise ValueError("future evidence rejected by PointInTimeGuard")

    def filter(
        self, evidence: list[dict[str, Any]], information_cutoff: str
    ) -> list[dict[str, Any]]:
        accepted = []
        for item in evidence:
            self.require(item, information_cutoff)
            accepted.append(item)
        return accepted


def validate_dataset_integrity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not rows:
        errors.append({"row": None, "code": "EMPTY_DATASET"})
    guard = PointInTimeGuard()
    observation_ids: set[str] = set()
    accessions: set[str] = set()
    company_splits: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(rows):
        missing = sorted(REQUIRED_OBSERVATION_FIELDS - set(row))
        if missing:
            errors.append({"row": index, "code": "SCHEMA_ERROR", "detail": missing})
            continue
        observation_id = str(row["observation_id"])
        if observation_id in observation_ids:
            errors.append({"row": index, "code": "DUPLICATE_OBSERVATION"})
        observation_ids.add(observation_id)
        accession = str(row["accession"])
        if accession in accessions:
            errors.append({"row": index, "code": "DUPLICATE_FILING"})
        accessions.add(accession)
        split = str(row["split"])
        if split not in ALLOWED_SPLITS:
            errors.append({"row": index, "code": "INVALID_SPLIT"})
        company_splits[str(row["cik"])].add(split)
        if not re.fullmatch(r"[0-9a-f]{64}", str(row["source_hash"])):
            errors.append({"row": index, "code": "MISSING_OR_INVALID_HASH"})
        try:
            guard.require(row, str(row["information_cutoff"]))
            if date.fromisoformat(str(row["filing_date"])[:10]) > date.fromisoformat(
                str(row["information_cutoff"])[:10]
            ):
                errors.append({"row": index, "code": "FUTURE_FILING_LEAKAGE"})
            if (
                row.get("restatement_filed_at")
                and not PointInTimeGuard.admits(
                str(row["restatement_filed_at"]), str(row["information_cutoff"])
                )
                and row.get("restatement_used_in_features")
            ):
                errors.append({"row": index, "code": "FUTURE_RESTATEMENT_LEAKAGE"})
        except (TypeError, ValueError):
            errors.append({"row": index, "code": "INVALID_OR_FUTURE_AVAILABILITY"})
        expected_period = str(row.get("period_end", "")).replace("-", "")
        expected_accession = str(row.get("accession", ""))
        provenance_map = row.get("fact_provenance") or {}
        for field, value in (row.get("facts") or {}).items():
            if value is not None and field not in provenance_map:
                errors.append({"row": index, "code": "FACT_PROVENANCE_MISSING", "detail": field})
        for field, provenance in (row.get("fact_provenance") or {}).items():
            if not provenance or "source_row" not in provenance:
                if (row.get("facts") or {}).get(field) is not None:
                    errors.append({"row": index, "code": "FACT_PROVENANCE_INCOMPLETE", "detail": field})
                continue
            source_row = provenance["source_row"] or {}
            required_provenance = {
                "adsh": source_row.get("adsh"),
                "tag": source_row.get("tag"),
                "ddate": source_row.get("ddate"),
                "uom": source_row.get("uom"),
                "source_hash": row.get("source_hash"),
                "source_available_time": row.get("source_available_time"),
            }
            missing_provenance = sorted(
                key for key, value in required_provenance.items() if value in (None, "")
            )
            if missing_provenance:
                errors.append({"row": index, "code": "FACT_PROVENANCE_INCOMPLETE", "detail": {field: missing_provenance}})
            if source_row.get("adsh") != expected_accession:
                errors.append({"row": index, "code": "FACT_ACCESSION_MISMATCH", "detail": field})
            if source_row.get("ddate") != expected_period:
                errors.append({"row": index, "code": "FACT_PERIOD_MISMATCH", "detail": field})
            if not source_row.get("tag"):
                errors.append({"row": index, "code": "FACT_CONCEPT_MISSING", "detail": field})
            if source_row.get("uom") != "USD":
                errors.append({"row": index, "code": "FACT_UNIT_MISMATCH", "detail": field})
            if (source_row.get("coreg") or "").strip() or (source_row.get("segments") or "").strip():
                errors.append({"row": index, "code": "DIMENSIONAL_FACT_IN_CONSOLIDATED_FEATURE", "detail": field})
        label_source = str(row.get("label_generated_by", "")).lower()
        if label_source in SYSTEM_LABEL_SOURCES or row.get("system_score_used_as_label"):
            errors.append({"row": index, "code": "LABEL_CONTAMINATION"})
        if row.get("label_available_at") and PointInTimeGuard.admits(
            str(row["label_available_at"]), str(row["information_cutoff"])
        ):
            errors.append({"row": index, "code": "OUTCOME_AVAILABLE_AT_PREDICTION"})
    overlapping = sorted(cik for cik, splits in company_splits.items() if len(splits) > 1)
    for cik in overlapping:
        errors.append({"row": None, "code": "COMPANY_SPLIT_OVERLAP", "detail": cik})
    counts = {split: sum(split in values for values in company_splits.values()) for split in ALLOWED_SPLITS}
    return {
        "valid": not errors,
        "gate": "PASS" if not errors else "STOP",
        "observation_count": len(rows),
        "company_count": len(company_splits),
        "company_overlap_count": len(overlapping),
        "future_leakage_count": sum("LEAKAGE" in item["code"] or item["code"] == "OUTCOME_AVAILABLE_AT_PREDICTION" for item in errors),
        "split_company_counts": counts,
        "errors": errors,
    }


def calibration_eligibility(dataset_metadata: dict[str, Any]) -> dict[str, Any]:
    disallowed = bool(
        dataset_metadata.get("outcome_balanced")
        or dataset_metadata.get("case_control_sampling")
        or not dataset_metadata.get("population_prevalence_preserved", False)
    )
    return {
        "eligible_for_probability_calibration": not disallowed,
        "status": "ELIGIBLE" if not disallowed else "RANKING_ONLY",
        "warning": None
        if not disallowed
        else "Sampling does not preserve real-world prevalence; Brier/ECE cannot be interpreted as population PD calibration.",
    }


def extraction_gold_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if row.get("review_status") == "adjudicated"
        and row.get("gold_source") not in SYSTEM_LABEL_SOURCES
    ]
    correct = sum(
        row.get("predicted_value") == row.get("gold_value")
        and row.get("predicted_unit") == row.get("gold_unit")
        and row.get("predicted_fiscal_year") == row.get("gold_fiscal_year")
        for row in eligible
    )
    categories = defaultdict(int)
    for row in eligible:
        if row.get("error_category"):
            categories[str(row["error_category"])] += 1
    return {
        "n": len(eligible),
        "exact_accuracy": correct / len(eligible) if eligible else None,
        "error_categories": dict(categories),
        "status": "MEASURED" if eligible else "NOT AVAILABLE",
    }


def independent_label_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate dual-review labels without consulting system predictions."""
    ready = []
    errors = []
    for index, row in enumerate(rows):
        if row.get("review_status") != "adjudicated":
            continue
        required = (
            "reviewer_a_label",
            "reviewer_a_source",
            "reviewer_b_label",
            "reviewer_b_source",
            "adjudicated_label",
        )
        if str(row.get("reviewer_a_label")) != str(row.get("reviewer_b_label")):
            required += ("adjudicator_source",)
        missing = [field for field in required if row.get(field) in (None, "")]
        if missing:
            errors.append({"row": index, "code": "INCOMPLETE_ADJUDICATION", "detail": missing})
            continue
        if row.get("label_generated_by") not in {"machine_review", "human_review"}:
            errors.append({"row": index, "code": "UNKNOWN_LABEL_PROVENANCE"})
            continue
        if str(row.get("label_generated_by", "")).lower() in SYSTEM_LABEL_SOURCES:
            errors.append({"row": index, "code": "LABEL_CONTAMINATION"})
            continue
        ready.append(row)
    agreements = [str(row["reviewer_a_label"]) == str(row["reviewer_b_label"]) for row in ready]
    human_ready = [row for row in ready if row.get("label_generated_by") == "human_review"]
    return {
        "status": "READY" if human_ready and not errors else "MACHINE_REVIEW_ONLY" if ready and not errors else "NOT AVAILABLE",
        "adjudicated_count": len(ready),
        "human_adjudicated_count": len(human_ready),
        "percent_agreement": sum(agreements) / len(agreements) if agreements else None,
        "errors": errors,
    }


def empirical_binary_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Research metrics for independently labelled observations.

    Scores are used for ranking only unless ``calibration_eligibility`` separately
    admits probability interpretation.
    """
    if not rows:
        raise ValueError("metrics require independently labelled observations")
    labels = [int(row["label"]) for row in rows]
    scores = [float(row["score"]) for row in rows]
    predictions = [int(row.get("prediction", score >= 0.5)) for row, score in zip(rows, scores)]
    classification = classification_metrics(labels, predictions)
    false_negatives = sum(label == 1 and prediction == 0 for label, prediction in zip(labels, predictions))
    positives = sum(labels)
    decided = [row for row in rows if not row.get("abstained", False)]
    decided_metrics = None
    if decided:
        decided_labels = [int(row["label"]) for row in decided]
        decided_predictions = [int(row.get("prediction", float(row["score"]) >= 0.5)) for row in decided]
        measured = classification_metrics(decided_labels, decided_predictions)
        decided_metrics = {
            "f1": measured.f1,
            "recall": measured.recall,
            "balanced_accuracy": balanced_accuracy(decided_labels, decided_predictions),
        }
    return {
        "auroc": roc_auc(labels, scores),
        "pr_auc": average_precision(labels, scores),
        "f1": classification.f1,
        "recall": classification.recall,
        "balanced_accuracy": balanced_accuracy(labels, predictions),
        "false_negative_rate": false_negatives / positives if positives else None,
        "coverage": len(decided) / len(rows),
        "abstention_rate": 1 - len(decided) / len(rows),
        "overall_performance": {
            "f1": classification.f1,
            "recall": classification.recall,
            "balanced_accuracy": balanced_accuracy(labels, predictions),
        },
        "decided_only_performance": decided_metrics,
        "risk_coverage": [
            {"coverage": round((index + 1) / len(rows), 6), "score": row["score"]}
            for index, row in enumerate(sorted(decided, key=lambda item: float(item["score"]), reverse=True))
        ],
    }


TENSION_RESEARCH_TAXONOMY = {
    "supported": "STRONG_SUPPORT",
    "weakly_supported": "WEAK_SUPPORT",
    "context_dependent": "NEUTRAL",
    "insufficient_evidence": "NEUTRAL",
    "tension": "WEAK_TENSION",
    "material_contradiction": "CONTRADICTION",
}


def tension_research_label(runtime_label: str) -> str:
    try:
        return TENSION_RESEARCH_TAXONOMY[runtime_label.strip().lower().replace(" ", "_")]
    except KeyError as exc:
        raise ValueError(f"unsupported tension label: {runtime_label}") from exc


def company_clustered_bootstrap_delta(
    rows: list[dict[str, Any]],
    metric: Callable[[list[dict[str, Any]]], float],
    baseline_key: str,
    challenger_key: str,
    samples: int = 2000,
    seed: int = 20260907,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["company_id"])].append(row)
    companies = sorted(groups)
    if not companies:
        raise ValueError("company-clustered bootstrap requires observations")
    labels = {int(row["label"]) for row in rows}
    positive_companies = {str(row["company_id"]) for row in rows if int(row["label"]) == 1}
    negative_companies = {str(row["company_id"]) for row in rows if int(row["label"]) == 0}
    if len(labels) < 2:
        return {
            "status": "CI_NOT_ESTIMABLE", "reason": "ORIGINAL_SAMPLE_SINGLE_CLASS",
            "valid_replicates": 0, "invalid_replicates": samples,
            "cluster_count": len(companies), "superiority_established": False,
        }
    observed = metric([{**row, "prediction": row[challenger_key]} for row in rows]) - metric(
        [{**row, "prediction": row[baseline_key]} for row in rows]
    )
    rng = random.Random(seed)
    deltas = []
    invalid_replicates = 0
    for _ in range(samples):
        sample = [row for _ in companies for row in groups[rng.choice(companies)]]
        if len({int(row["label"]) for row in sample}) < 2:
            invalid_replicates += 1
            continue
        challenger = metric([{**row, "prediction": row[challenger_key]} for row in sample])
        baseline = metric([{**row, "prediction": row[baseline_key]} for row in sample])
        deltas.append(challenger - baseline)
    deltas.sort()
    power_insufficient = (
        len(companies) < 10
        or len(positive_companies) < 5
        or len(negative_companies) < 5
        or len(deltas) < max(200, int(samples * 0.8))
    )
    if not deltas or power_insufficient:
        return {
            "status": "CI_NOT_ESTIMABLE",
            "reason": "INSUFFICIENT_POWER",
            "delta": round(observed, 6),
            "ci_low": None,
            "ci_high": None,
            "valid_replicates": len(deltas),
            "invalid_replicates": invalid_replicates,
            "cluster_count": len(companies),
            "positive_cluster_count": len(positive_companies),
            "negative_cluster_count": len(negative_companies),
            "superiority_established": False,
        }
    return {
        "status": "ESTIMATED",
        "delta": round(observed, 6),
        "ci_low": round(deltas[int(len(deltas) * 0.025)], 6),
        "ci_high": round(deltas[min(len(deltas) - 1, int(len(deltas) * 0.975))], 6),
        "cluster_count": len(companies),
        "valid_replicates": len(deltas),
        "invalid_replicates": invalid_replicates,
        "superiority_established": deltas[int(len(deltas) * 0.025)] > 0,
    }


ERROR_CATEGORIES = {
    "EXTRACTION_ERROR",
    "CONTEXT_ERROR",
    "MODEL_APPLICABILITY",
    "RULE_THRESHOLD",
    "NARRATIVE_OVERWEIGHT",
    "NUMERIC_OVERWEIGHT",
    "MISSING_EVIDENCE",
    "TEMPORAL_ERROR",
    "FUSION_ERROR",
    "LABEL_AMBIGUITY",
    "AGENT_CORRELATED_ERROR",
    "CRITIC_FAILURE",
    "VERIFIER_FAILURE",
}


def structured_error_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        if row.get("prediction") == row.get("label"):
            continue
        category = row.get("error_category", "LABEL_AMBIGUITY")
        if category not in ERROR_CATEGORIES:
            category = "LABEL_AMBIGUITY"
        output.append(
            {
                "observation_id": row["observation_id"],
                "error_type": "FN" if row.get("label") == 1 else "FP",
                "category": category,
                "evidence_ids": row.get("evidence_ids", []),
                "review_status": row.get("review_status", "pending"),
            }
        )
    return output


def freeze_experiment(configuration: dict[str, Any]) -> dict[str, Any]:
    required = {
        "dataset_hash",
        "split_hash",
        "rule_version",
        "model_config",
        "fusion_config",
        "prompt_version",
        "llm_model",
        "label_schema_hash",
        "random_seed",
        "git_commit",
    }
    missing = sorted(required - set(configuration))
    if missing:
        raise ValueError(f"experiment freeze missing {missing}")
    frozen = dict(configuration)
    frozen["experiment_hash"] = canonical_hash(configuration)
    frozen["immutable"] = True
    return frozen


def verify_experiment_freeze(manifest: dict[str, Any]) -> bool:
    content = {key: value for key, value in manifest.items() if key not in {"experiment_hash", "immutable"}}
    return bool(manifest.get("immutable")) and canonical_hash(content) == manifest.get("experiment_hash")
