"""Future-only E4 outcome construction using the frozen v0.3.4 endpoint."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from finrisk import sec_bulk

from .e4_core import OUTCOME_ARCHIVES, canonical_hash


def build_outcomes(features: list[dict[str, Any]], outcome_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = [outcome_dir / name for name in OUTCOME_ARCHIVES]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise RuntimeError(f"future outcome archives are unavailable: {missing}")
    mapping = {row["masked_company_id"]: str(row["cik"]).zfill(10) for row in features}
    original_mapping = sec_bulk.FROZEN_CIKS
    try:
        sec_bulk.FROZEN_CIKS = mapping
        submissions, numbers, sources = sec_bulk.load_statement_archives(paths, set(mapping.values()))
        annual = sec_bulk.build_annual_outcome_corpus(submissions, numbers, sources)
        reported = sec_bulk.build_reported_fcf_periods(submissions, numbers)
        endpoint_features = [
            {
                "observation_id": row["observation_id"],
                "ticker": row["masked_company_id"],
                "fiscal_year": row["fiscal_year"],
                "information_cutoff": row["information_cutoff"],
                "outcome_window_end": row["outcome_window_end"],
                "facts": row["current"],
            }
            for row in features
        ]
        labels = sec_bulk.build_deterioration_labels(
            endpoint_features,
            reported_periods=reported,
            annual_outcomes=annual,
            outcome_data_available_through="2026-06-30T23:59:59Z",
        )
    finally:
        sec_bulk.FROZEN_CIKS = original_mapping
    feature_by_id = {row["observation_id"]: row for row in features}
    for label in labels:
        feature = feature_by_id[label["observation_id"]]
        available = label.get("outcome_available_at")
        if available:
            cutoff = datetime.fromisoformat(feature["information_cutoff"])
            end = datetime.fromisoformat(feature["outcome_window_end"])
            observed = datetime.fromisoformat(str(available))
            if not cutoff < observed <= end:
                raise RuntimeError("outcome is outside the locked forward window")
        if label.get("label_status") != "VERIFIED" and label.get("financial_deterioration_12m") is not None:
            raise RuntimeError("REVIEW/INSUFFICIENT outcome was converted into a binary label")
    labels.sort(key=lambda row: row["observation_id"])
    status_counts: dict[str, int] = {}
    for row in labels:
        status_counts[row["label_status"]] = status_counts.get(row["label_status"], 0) + 1
    report = {
        "endpoint": "deterministic_forward_outcome_rule_v1",
        "status_counts": dict(sorted(status_counts.items())),
        "verified_events": sum(row.get("financial_deterioration_12m") == 1 for row in labels),
        "sources": sources,
        "annual_outcome_count": len(annual),
        "reported_period_count": len(reported),
        "label_hash": canonical_hash(labels),
    }
    return labels, report
