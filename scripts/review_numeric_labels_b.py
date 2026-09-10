from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/empirical_v1"
PACKETS = DATA / "reviewer_packets/numeric_outcomes.json"
OUTPUT = DATA / "machine_reviews/reviewer_b_neutral_evidence.json"
PROMPT_VERSION = "v031_numeric_label_review_b_neutral_evidence_v3"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def review_packet(packet: dict[str, Any]) -> dict[str, Any]:
    current = packet["current_evidence"]
    cutoff, window = instant(current["information_cutoff"]), instant(current["outcome_window_end"])
    annuals = sorted(
        (
            row for row in packet["complete_annual_evidence_pool"]
            if row["fiscal_year"] == current["fiscal_year"] + 1
            and cutoff < instant(row["source_available_time"]) <= window
        ), key=lambda row: row["source_available_time"],
    )
    if not annuals:
        return {"label": None, "status": "INSUFFICIENT_DATA", "reasons": ["NO_ELIGIBLE_FORWARD_ANNUAL_OUTCOME_WITHIN_12_MONTHS"], "evidence_locators": []}
    future = annuals[0]
    now, nxt = current["facts"], future["facts"]
    reasons = []

    def declined(field: str, threshold: float) -> bool:
        return now.get(field) not in (None, 0) and nxt.get(field) is not None and (nxt[field] - now[field]) / abs(now[field]) <= -threshold

    if declined("revenue", 0.10):
        reasons.append("REVENUE_DECLINE_10PCT")
    if now.get("net_income") is not None and nxt.get("net_income") is not None and now["net_income"] > 0 >= nxt["net_income"]:
        reasons.append("POSITIVE_INCOME_TO_LOSS")
    turns_negative = now.get("operating_cash_flow") is not None and nxt.get("operating_cash_flow") is not None and now["operating_cash_flow"] >= 0 > nxt["operating_cash_flow"]
    if declined("operating_cash_flow", 0.25) or turns_negative:
        reasons.append("OCF_DECLINE_OR_NEGATIVE")
    debt_t, debt_t1 = now.get("total_debt"), nxt.get("total_debt")
    assets_t, assets_t1 = now.get("total_assets"), nxt.get("total_assets")
    if None not in (debt_t, debt_t1, assets_t, assets_t1) and assets_t and assets_t1 and debt_t1 / assets_t1 - debt_t / assets_t >= 0.10:
        reasons.append("DEBT_TO_ASSETS_INCREASE_10PP")
    periods = sorted(
        (
            row for row in packet["complete_filing_period_evidence_pool"]
            if cutoff < instant(row["source_available_time"]) <= window
        ), key=lambda row: row["source_available_time"],
    )[:2]
    fcf_values = [row.get("free_cash_flow") for row in periods]
    fcf_resolved = len(periods) == 2 and all(value is not None for value in fcf_values)
    if fcf_resolved and all(float(value) < 0 for value in fcf_values):
        reasons.append("FCF_NEGATIVE_TWO_SUBSEQUENT_PERIODS")
    true_codes = set(reasons)
    condition_statuses = {
        "revenue_decline": "TRUE" if "REVENUE_DECLINE_10PCT" in true_codes else "FALSE" if now.get("revenue") not in (None, 0) and nxt.get("revenue") is not None else "UNKNOWN",
        "income_to_loss": "TRUE" if "POSITIVE_INCOME_TO_LOSS" in true_codes else "FALSE" if now.get("net_income") is not None and nxt.get("net_income") is not None else "UNKNOWN",
        "ocf_deterioration": "TRUE" if "OCF_DECLINE_OR_NEGATIVE" in true_codes else "FALSE" if now.get("operating_cash_flow") is not None and nxt.get("operating_cash_flow") is not None else "UNKNOWN",
        "debt_to_assets_increase": "TRUE" if "DEBT_TO_ASSETS_INCREASE_10PP" in true_codes else "FALSE" if None not in (debt_t, debt_t1, assets_t, assets_t1) and assets_t and assets_t1 else "UNKNOWN",
        "two_period_negative_fcf": "TRUE" if fcf_resolved and all(float(value) < 0 for value in fcf_values) else "FALSE" if fcf_resolved else "UNKNOWN",
    }
    true_count = sum(value == "TRUE" for value in condition_statuses.values())
    unknown = [key for key, value in condition_statuses.items() if value == "UNKNOWN"]
    status = "VERIFIED" if true_count >= 2 or true_count + len(unknown) < 2 else "REQUIRES_HUMAN_REVIEW"
    return {
        "label": int(true_count >= 2) if status == "VERIFIED" else None,
        "status": status, "reasons": reasons,
        "evidence_locators": [current["accession"], future["accession"], *[row["accession"] for row in periods]],
        "fcf_context": "VERIFIED" if fcf_resolved else "INSUFFICIENT_DATA",
        "condition_statuses": condition_statuses, "unknown_conditions": unknown,
    }


def main() -> int:
    packet_file = json.loads(PACKETS.read_text(encoding="utf-8"))
    if any(packet_file.get(key) for key in (
        "candidate_labels_included", "model_predictions_included", "other_reviewer_outputs_included",
        "candidate_selected_directional_evidence_included",
    )):
        raise RuntimeError("reviewer independence gate failed")
    records = []
    for packet in packet_file["packets"]:
        result = review_packet(packet)
        record = {
            "review_run_id": f"reviewer-b-{packet['observation_id']}", "role": "REVIEWER_B",
            "observation_id": packet["observation_id"], "task": "OUTCOME_LABEL",
            "packet_hash": packet["packet_hash"], "prompt_version": PROMPT_VERSION,
            "input_hash": digest(packet), "run_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "model_metadata": "UNAVAILABLE", "tokens": None, "cost_usd": None, "latency_ms": None,
            "schema_valid": True, "evidence_valid": True, "status": "MACHINE_REVIEW", "result": result,
        }
        record["output_hash"] = digest(record)
        records.append(record)
    output = {
        "reviewer_type": "MACHINE_REVIEWED", "candidate_labels_seen": False,
        "other_reviewer_outputs_seen": False, "model_predictions_seen": False,
        "records": records, "record_count": len(records), "input_packet_file_hash": digest(packet_file),
    }
    output["output_hash"] = digest(output)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "records"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
