from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/empirical_v1"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalized_status(value: str) -> str:
    return "REQUIRES_HUMAN_REVIEW" if value == "REVIEW_REQUIRED" else value


def main() -> int:
    independent = json.loads((DATA / "machine_reviews/reviewer_b_neutral_evidence.json").read_text(encoding="utf-8"))
    reviewer_a = json.loads((DATA / "machine_reviews/reviewer_a_neutral_evidence.json").read_text(encoding="utf-8"))
    labels = {row["observation_id"]: row for row in json.loads((DATA / "deterioration_labels.json").read_text(encoding="utf-8"))}
    comparisons = []
    for record in independent["records"]:
        candidate = labels[record["observation_id"]]
        result = record["result"]
        comparisons.append({
            "observation_id": record["observation_id"],
            "reviewer_label": result["label"], "reviewer_status": result["status"],
            "candidate_label": candidate.get("financial_deterioration_12m"),
            "candidate_status": candidate["label_status"],
            "agreement": result["label"] == candidate.get("financial_deterioration_12m") and result["status"] == candidate["label_status"],
        })
    old_exposed = DATA / "machine_reviews/reviewer_b.json"
    a_by_id = {record["observation_id"]: record for record in reviewer_a["records"]}
    reviewer_pairs = []
    for record in independent["records"]:
        a_result = a_by_id[record["observation_id"]]
        b_result = record["result"]
        reviewer_pairs.append({
            "observation_id": record["observation_id"],
            "reviewer_a_label": a_result["label"], "reviewer_a_status": a_result["status"],
            "reviewer_b_label": b_result["label"], "reviewer_b_status": b_result["status"],
            "agreement": a_result["label"] == b_result["label"] and normalized_status(a_result["status"]) == normalized_status(b_result["status"]),
        })
    disagreements = [row for row in reviewer_pairs if not row["agreement"]]
    report = {
        "reviewer_b_independent_run": "MACHINE_REVIEWED",
        "candidate_labels_visible_during_review": independent["candidate_labels_seen"],
        "other_reviewer_outputs_visible_during_review": independent["other_reviewer_outputs_seen"],
        "candidate_selected_directional_evidence_visible_during_review": False,
        "posthoc_comparison_count": len(comparisons),
        "posthoc_label_status_agreement_count": sum(row["agreement"] for row in comparisons),
        "reviewer_a_status": "MACHINE_REVIEWED",
        "dual_review_status": "COMPLETE_MACHINE_ONLY",
        "reviewer_pair_count": len(reviewer_pairs),
        "reviewer_pair_agreement_count": sum(row["agreement"] for row in reviewer_pairs),
        "reviewer_pair_percent_agreement": sum(row["agreement"] for row in reviewer_pairs) / len(reviewer_pairs),
        "disagreement_count": len(disagreements),
        "adjudication_status": "NOT_REQUIRED_NO_DISAGREEMENTS" if not disagreements else "REQUIRED_NOT_RUN",
        "human_gold_status": "NOT_ADJUDICATED",
        "prior_reviewer_b_artifact": "CONFIRMATION_EXPOSED_INVALID" if old_exposed.exists() else "NOT_PRESENT",
        "superseded_candidate_blind_artifact": "EVIDENCE_SELECTION_NOT_STRICT_ENOUGH_INVALID",
        "independence_conclusion": "Earlier Reviewer B artifacts are invalid: the original read candidate labels and the first replacement used preselected next-year evidence. Neutral Reviewer A and B each received the complete same-company evidence pool, no candidate label or prediction, and no other reviewer output. Their agreement is machine-only and is not human-adjudicated gold.",
        "comparisons": comparisons,
        "reviewer_pairs": reviewer_pairs,
    }
    report["report_hash"] = digest(report)
    (DATA / "machine_reviews/independence_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "comparisons"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
