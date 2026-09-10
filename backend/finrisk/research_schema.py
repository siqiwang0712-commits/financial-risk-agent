from __future__ import annotations

from typing import Any

V1_TO_V2_REVIEW_FIELDS = {
    "reviewer_1_label": "reviewer_a_label",
    "reviewer_1_reason": "reviewer_a_reason",
    "reviewer_1_source": "reviewer_a_source",
    "reviewer_2_label": "reviewer_b_label",
    "reviewer_2_reason": "reviewer_b_reason",
    "reviewer_2_source": "reviewer_b_source",
}


def migrate_review_record_v1_to_v2(record: dict[str, Any]) -> dict[str, Any]:
    """Return a v2 compatibility view; never mutate a frozen v1 record."""
    migrated = dict(record)
    for old, new in V1_TO_V2_REVIEW_FIELDS.items():
        if new not in migrated and old in record:
            migrated[new] = record[old]
    migrated["schema_version"] = "finrisk-forward-label-v2.0.0"
    migrated.setdefault("dataset_status", "PARTIAL_LABELS")
    migrated.setdefault("human_adjudication_status", "NOT_COMPLETED")
    return migrated
