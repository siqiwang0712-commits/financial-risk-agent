from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean

from finrisk.enterprise.fusion import hierarchical_escalation
from finrisk.llm import MockNarrativeProvider
from finrisk.pipeline import FinRiskPipeline
from finrisk.research_eval import (
    run_public_benchmark,
    run_robustness_checks,
    write_results,
    write_robustness,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "research/benchmark/public_company_observations.json"
OUTPUT = ROOT / "research/results/v0.3.1"


def legacy_v1_score(scores: dict[str, float | None]) -> float | None:
    active = {key: value for key, value in scores.items() if value is not None}
    if not active:
        return None
    severe = [value for value in active.values() if value >= 70]
    elevated = [value for value in active.values() if value >= 50]
    return max(active.values()) if severe else mean(active.values()) + min(15, 5 * len(elevated))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows, summary, ablations = run_public_benchmark(MANIFEST, ROOT)
    write_results(rows, summary, ablations, OUTPUT)
    write_robustness(run_robustness_checks(MANIFEST, ROOT), OUTPUT)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pipeline = FinRiskPipeline(ROOT, MockNarrativeProvider())
    diffs = []
    for example in manifest["examples"]:
        assessment = pipeline.assess(
            example["company"],
            example["fiscal_year"],
            example["current"],
            example["previous"],
            {int(key): value for key, value in example.get("pages", {}).items()},
            example["filing_url"],
        )
        scores = {
            key: value["score"] for key, value in assessment.dimensions.items()
        }
        old_score = legacy_v1_score(scores)
        new = hierarchical_escalation(
            scores, assessment.confidence, assessment.confidence
        )
        diffs.append(
            {
                "example_id": example["id"],
                "split": example["split"],
                "gold_label": example["high_risk_label"],
                "legacy_fusion_v1_on_v031_evidence": None if old_score is None else round(old_score, 3),
                "integrity_fusion_v2_score": new.score,
                "delta": None
                if old_score is None or new.score is None
                else round(new.score - old_score, 3),
                "v031_decision": new.decision.value,
                "reason_codes": "|".join(new.reason_codes),
            }
        )
    (OUTPUT / "decision_integrity_replay.json").write_text(
        json.dumps(diffs, indent=2), encoding="utf-8"
    )
    with (OUTPUT / "decision_integrity_replay.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(diffs[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(diffs)
    (OUTPUT / "run_manifest.json").write_text(
        json.dumps(
            {
                "version": "v0.3.1-local",
                "source_dataset": manifest["dataset_id"],
                "source_results_preserved": "research/results/public_v1",
                "replay_comparison": "legacy fusion v1 versus integrity fusion v2 on the same v0.3.1 claim-conditioned evidence; not a reconstruction of historical public_v1 scores",
                "calibration_status": "UNCALIBRATED",
                "validation_scope": "three-company single-reviewer public pilot",
                "predictive_superiority_claimed": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(diffs, indent=2))


if __name__ == "__main__":
    main()
