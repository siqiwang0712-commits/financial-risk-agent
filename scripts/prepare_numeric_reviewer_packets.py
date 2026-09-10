from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/empirical_v1"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    observations = json.loads((DATA / "numeric_corpus.json").read_text(encoding="utf-8"))
    annual_outcomes = json.loads((DATA / "annual_outcome_corpus.json").read_text(encoding="utf-8"))
    periods = json.loads((DATA / "reported_fcf_periods.json").read_text(encoding="utf-8"))
    definition = json.loads((ROOT / "research/label_schema.json").read_text(encoding="utf-8"))["outcome_level"]["secondary_endpoint"]
    packets = []
    for current in observations:
        future_annual = [row for row in annual_outcomes if row["ticker"] == current["ticker"]]
        future_periods = [row for row in periods if row["ticker"] == current["ticker"]]
        packet = {
            "observation_id": current["observation_id"], "frozen_definition": definition,
            "current_evidence": current, "complete_annual_evidence_pool": future_annual,
            "complete_filing_period_evidence_pool": future_periods,
            "evidence_selection_policy": "ALL_SAME_COMPANY_RAW_NUMERIC_EVIDENCE_NO_DIRECTION_FILTER",
            "prohibited_fields": ["candidate_label", "model_prediction", "candidate_selected_directional_evidence", "other_reviewer_output"],
        }
        packet["packet_hash"] = digest(packet)
        packets.append(packet)
    output = {
        "status": "REVIEWER_PACKETS_READY", "candidate_labels_included": False,
        "model_predictions_included": False, "other_reviewer_outputs_included": False,
        "candidate_selected_directional_evidence_included": False,
        "packet_count": len(packets), "packets": packets,
    }
    output["output_hash"] = digest(output)
    path = DATA / "reviewer_packets/numeric_outcomes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "packets"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
