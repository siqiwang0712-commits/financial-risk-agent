from __future__ import annotations

from statistics import mean

REQUIRED_FIELDS = {
    "participant_id", "condition", "case_id", "analysis_seconds", "missed_risks",
    "unsupported_claims", "citation_errors", "overrides", "decision", "gold_decision",
}


def validate_study_rows(rows: list[dict]) -> dict:
    errors = []
    for index, row in enumerate(rows):
        missing = REQUIRED_FIELDS - row.keys()
        if missing:
            errors.append(f"row {index}: missing {sorted(missing)}")
        if row.get("condition") not in {"human_only", "finrisk_assisted"}:
            errors.append(f"row {index}: invalid condition")
    return {"valid": not errors, "errors": errors, "participant_count": len({row.get("participant_id") for row in rows if row.get("participant_id")})}


def summarize_study(rows: list[dict], synthetic: bool = False) -> dict:
    validation = validate_study_rows(rows)
    if not validation["valid"]:
        raise ValueError("invalid human-study rows")
    groups = {}
    for condition in ("human_only", "finrisk_assisted"):
        selected = [row for row in rows if row["condition"] == condition]
        groups[condition] = {
            "n": len(selected),
            "mean_analysis_seconds": round(mean(row["analysis_seconds"] for row in selected), 3) if selected else None,
            "mean_missed_risks": round(mean(row["missed_risks"] for row in selected), 3) if selected else None,
            "unsupported_claim_rate": round(sum(row["unsupported_claims"] for row in selected) / len(selected), 3) if selected else None,
            "citation_error_rate": round(sum(row["citation_errors"] for row in selected) / len(selected), 3) if selected else None,
            "decision_agreement": round(sum(row["decision"] == row["gold_decision"] for row in selected) / len(selected), 3) if selected else None,
        }
    return {"status": "SYNTHETIC_DEMO" if synthetic else "OBSERVED", "groups": groups, "participant_count": validation["participant_count"]}
