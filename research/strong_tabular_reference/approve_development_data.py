"""Approve the existing E4-S historical development inputs without model execution."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .contract import artifact_sha256, canonical_json_bytes, load_schema
from .development_data import validate_development_data_manifest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPLICATION = ROOT / "research/e4_statistical_audit/replication"
ARTIFACTS = HERE / "artifacts"
APPROVED_MANIFEST = HERE / "development_data_manifest.json"
LABELED_COMPANIES = ARTIFACTS / "development_companies_675.json"
E5_EXCLUSIONS = ARTIFACTS / "e5_exclusion_companies_2000.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))


def _head_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def build() -> dict[str, Any]:
    source_manifest = _load(REPLICATION / "manifest.json")
    expected = {Path(row["path"]).name: row["sha256"] for row in source_manifest["files"]}
    source_names = [
        "cohort.json",
        "features.json.gz",
        "outcomes.json",
        "input_inventory.json",
        "feature_report.json",
        "outcome_report.json",
    ]
    observed = {name: sha256_file(REPLICATION / name) for name in source_names}
    for name, digest in observed.items():
        if expected.get(name) != digest:
            raise RuntimeError(f"frozen E4-S source hash mismatch: {name}")

    cohort = _load(REPLICATION / "cohort.json")
    outcomes = _load(REPLICATION / "outcomes.json")
    verified = {
        row["observation_id"]: row
        for row in outcomes
        if row.get("label_status") == "VERIFIED"
        and row.get("financial_deterioration_12m") in {0, 1}
    }
    cohort_by_id = {row["observation_id"]: row for row in cohort}
    if len(cohort) != 2000 or len(verified) != 675 or sum(
        int(row["financial_deterioration_12m"]) for row in verified.values()
    ) != 235:
        raise RuntimeError("E4-S cohort/label counts drifted")
    if len({row["cik"] for row in cohort}) != 2000:
        raise RuntimeError("source cohort company identities are not unique")

    development_rows = []
    for observation_id in sorted(verified):
        source = cohort_by_id[observation_id]
        label = verified[observation_id]
        development_rows.append(
            {
                "observation_id": observation_id,
                "cik": source["cik"],
                "masked_company_id": source["masked_company_id"],
                "accession": source["accession"],
                "accepted": source["accepted"],
                "feature_period_end": source["period"],
                "outcome_status": label["label_status"],
                "outcome": int(label["financial_deterioration_12m"]),
            }
        )
    exclusion_rows = [
        {
            "cik": row["cik"],
            "masked_company_id": row["masked_company_id"],
            "source_observation_id": row["observation_id"],
        }
        for row in sorted(cohort, key=lambda item: item["cik"])
    ]
    labeled_payload = {
        "schema_version": "1",
        "status": "APPROVED_DEVELOPMENT_COMPANY_SET",
        "dataset_id": "e4s-replication-verified-development-v1",
        "company_count": 675,
        "observation_count": 675,
        "events": 235,
        "non_events": 440,
        "rows": development_rows,
    }
    exclusions_payload = {
        "schema_version": "1",
        "status": "MANDATORY_FUTURE_E5_EXCLUSION",
        "source_dataset": "E4-S_PUBLIC_REPLICATION_COHORT",
        "company_count": 2000,
        "scope": "ALL_SOURCE_COHORT_COMPANIES_NOT_ONLY_VERIFIED_ROWS",
        "rows": exclusion_rows,
    }
    _write(LABELED_COMPANIES, labeled_payload)
    _write(E5_EXCLUSIONS, exclusions_payload)

    schema = load_schema()
    source_hashes = {name: observed[name] for name in source_names}
    source_hashes[LABELED_COMPANIES.name] = sha256_file(LABELED_COMPANIES)
    source_hashes[E5_EXCLUSIONS.name] = sha256_file(E5_EXCLUSIONS)
    source_hashes["label_schema.json"] = sha256_file(ROOT / "research/label_schema.json")
    source_hashes["development_run_config.json"] = sha256_file(
        HERE / "development_run_config.json"
    )
    source_hashes["experiment_config.json"] = sha256_file(HERE / "experiment_config.json")
    source_hashes["feature_schema.json"] = sha256_file(HERE / "feature_schema.json")
    source_hashes["approve_development_data.py"] = sha256_file(Path(__file__))
    source_hashes["run_development.py"] = sha256_file(HERE / "run_development.py")
    manifest: dict[str, Any] = {
        "schema_version": "1",
        "dataset_id": "e4s-replication-verified-development-v1",
        "status": "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT",
        "purpose": "STRONG_TABULAR_REFERENCE_DEVELOPMENT",
        "creation_source": "EXISTING_FROZEN_PUBLIC_E4S_REPLICATION_ARTIFACTS",
        "population": {
            "company_count": 675,
            "observation_count": 675,
            "source_population_company_count": 2000,
            "company_year_structure": "ONE_FY2024_10K_OBSERVATION_PER_COMPANY",
            "sector_scope": "PUBLIC_SEC_FILERS_IN_REPLICATION_COHORT",
            "inclusion_criteria": ["E4-S replication row", "outcome status VERIFIED"],
            "exclusion_criteria": ["outcome status REVIEW", "outcome status INSUFFICIENT"],
            "primary_empirical_source": True,
            "synthetic_only": False,
            "verified_label_selection_is_selective": True,
        },
        "temporal_contract": {
            "feature_start": "2024-07-01",
            "feature_end": "2025-06-30",
            "feature_cutoff_rule": "Selected FY2024 10-K facts available by SEC accepted timestamp only.",
            "outcome_start": "2025-07-01",
            "outcome_end": "2026-06-30",
            "outcome_horizon": "12_MONTH_FORWARD_WINDOW",
            "filing_availability_rule": "SELECTED_10K_ACCEPTED_WITHIN_FEATURE_WINDOW",
            "accepted_or_filing_timestamp_policy": "SEC_ACCEPTED_TIMESTAMP_IS_INFORMATION_CUTOFF",
        },
        "endpoint": {
            "name": "financial_deterioration_12m",
            "version": "deterministic_forward_outcome_rule_v1",
            "development_status": "HISTORICAL_DEVELOPMENT_ENDPOINT_V1",
            "compatibility_status": "ENDPOINT_COMPATIBLE_FOR_DEVELOPMENT",
            "e5_status": "E5_ENDPOINT_COMPATIBILITY_TO_BE_CONFIRMED_AT_PROTOCOL_FREEZE",
            "material_change_rule": "If the frozen E5 endpoint materially changes, StrongTabularReference-v1 must be re-developed or re-qualified before E5 prediction.",
            "implementation_identity": "research/e4_statistical_audit/replication/outcome_report.json",
            "implementation_sha256": observed["outcome_report.json"],
            "label_schema": "research/label_schema.json",
            "label_schema_sha256": source_hashes["label_schema.json"],
            "horizon": "12_MONTHS",
            "label_states": ["VERIFIED", "REVIEW", "INSUFFICIENT"],
        },
        "feature_contract": {
            "feature_schema_version": schema["schema_version"],
            "feature_schema_sha256": artifact_sha256(schema),
            "permitted_feature_blocks": ["V", "VO"],
            "feature_reconstruction_entry_point": "research/e4_statistical_audit/replicate_e4.py",
            "feature_source_identity": "research/e4_statistical_audit/replication/features.json.gz",
        },
        "provenance": {
            "source_files": [f"research/e4_statistical_audit/replication/{name}" for name in source_names],
            "source_artifact_hashes": source_hashes,
            "source_archive_identities": [
                "SEC_FSDS_2024Q3_TO_2025Q2_FEATURE_ARCHIVES",
                "SEC_FSDS_2025Q3_TO_2026Q2_OUTCOME_ARCHIVES",
            ],
            "accession_cik_identity_policy": "CIK_AND_ACCESSION_FROM_REPLICATION_COHORT_MANIFEST",
            "acquisition_method": "E4S_PUBLIC_SEC_FSDS_REPLICATION_PIPELINE",
            "code_commit": _head_commit(),
            "working_tree_state": "UNCOMMITTED_V0.4.1_RESEARCH_DEVELOPMENT",
            "hash_verification_status": "VERIFIED",
        },
        "isolation": {
            "historical_study_relationships": {
                "E1": "ZERO_CIK_OVERLAP_WITH_REPLICATION_VIA_E3_LINEAGE",
                "E2": "ZERO_CIK_OVERLAP_WITH_REPLICATION_VIA_E3_LINEAGE",
                "E3": "ZERO_CIK_OVERLAP_WITH_REPLICATION_COHORT",
                "E4": "HIGH_OVERLAP_NOT_IDENTICAL",
                "E4_S": "SOURCE_COHORT",
                "E4_R": "SAME_675_VERIFIED_ROWS_HEAVILY_ANALYZED",
            },
            "historical_research_exposure": "DESIGN_EXPOSED_HISTORICAL_DEVELOPMENT",
            "e5_overlap_status": "E5_NOT_ENUMERATED",
            "e5_artifacts_referenced": False,
            "e5_future_exclusion_obligation": True,
            "e5_exclusion_scope": "ALL_2000_SOURCE_COHORT_COMPANIES",
            "development_company_manifest": "research/strong_tabular_reference/artifacts/development_companies_675.json",
            "development_company_manifest_sha256": source_hashes[LABELED_COMPANIES.name],
            "e5_exclusion_manifest": "research/strong_tabular_reference/artifacts/e5_exclusion_companies_2000.json",
            "e5_exclusion_manifest_sha256": source_hashes[E5_EXCLUSIONS.name],
            "same_company_rows_must_remain_grouped": True,
            "company_group_key": "cik",
        },
        "label_access": {
            "historical_development_labels_may_be_used": True,
            "e5_outcomes_forbidden": True,
            "e5_outcome_proxies_forbidden": True,
            "post_prediction_e5_information_forbidden": True,
            "definition": "Outcome-blind means blind to E5 outcomes, not legitimate historical development labels.",
        },
        "eligibility_gates": {
            "provenance": "PASS",
            "temporal": "PASS",
            "endpoint": "PASS",
            "company_identity": "PASS",
            "grouping": "PASS",
            "feature_contract": "PASS",
            "integrity": "PASS",
            "e5_isolation": "PASS",
            "exposure_recording": "PASS",
        },
        "integrity": {
            "canonicalization": "UTF-8 JSON, object keys sorted, indent=1, ensure_ascii=false, one trailing newline",
            "canonical_manifest_sha256": "PENDING_SELF_HASH",
            "source_manifest_hashes": "RECORDED_IN_PROVENANCE",
            "validation_status": "APPROVED_AND_MECHANICALLY_VALIDATED",
        },
    }
    from .development_data import canonical_manifest_sha256

    manifest["integrity"]["canonical_manifest_sha256"] = canonical_manifest_sha256(manifest)
    validate_development_data_manifest(manifest, schema=schema)
    _write(APPROVED_MANIFEST, manifest)
    return manifest


def main() -> int:
    manifest = build()
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "manifest_sha256": manifest["integrity"]["canonical_manifest_sha256"],
                "development_companies": 675,
                "future_e5_exclusions": 2000,
                "models_trained": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
