"""Unified state-machine entry point for the E4 research study."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from finrisk.e4_agent import (
    OPTIONS,
    REPRESENTATIONS,
    RUNTIME,
    RUNTIME_DIGEST,
    build_manifest,
    execute_batch,
    hybrid_predictions,
    manifest_hash,
    replay_frozen_agent,
    run_agent,
)
from finrisk.e4_core import (
    BATCH_SENSITIVITY_LIMIT,
    FEATURE_ARCHIVES,
    OUTCOME_ARCHIVES,
    SOURCE_COMMIT,
    SOURCE_TAG,
    STABILITY_LIMIT,
    Stage,
    StudyState,
    build_cohort,
    build_features,
    canonical_hash,
    read_json,
    run_numeric,
    sha256_file,
    verify_inputs,
    verify_source,
    write_json,
)
from finrisk.e4_evaluation import (
    evaluate,
    label_attrition,
    missingness,
    sector_heterogeneity,
    source_concordance,
    stability_summary,
    threshold_sensitivity,
)
from finrisk.e4_outcomes import build_outcomes

ARTIFACTS = Path(os.environ.get("E4_ARTIFACT_DIR", ROOT / "research/e4/_artifacts"))
CACHE = Path(os.environ.get("E4_CACHE_DIR", ROOT / "research/e4/_cache/runtime"))
FEATURE_INPUTS = Path(os.environ.get("E4_FEATURE_INPUT_DIR", ROOT / "research/e4/_cache/inputs/feature"))
OUTCOME_INPUTS = Path(os.environ.get("E4_OUTCOME_INPUT_DIR", ROOT / "research/e4/_cache/inputs/outcome"))
ZENODO_INPUTS = Path(os.environ.get("E4_ZENODO_INPUT_DIR", ROOT / "research/e4/_cache/inputs/zenodo"))
PREVIOUS_270 = Path(os.environ.get("E4_PREVIOUS_270", ROOT / "research/e4/_cache/previous_270.json"))
AGENT_URL = os.environ.get("E4_AGENT_URL", "http://finrisk-e4-agent-api:8080")


def state() -> StudyState:
    return StudyState(ARTIFACTS)


def _frozen_write(path: Path, value: Any) -> None:
    write_json(path, value, frozen=True)


def _require_prediction_isolation() -> None:
    if os.environ.get("E4_OUTCOME_INPUT_DIR") or Path("/inputs/outcome").exists():
        raise RuntimeError("future outcome storage is visible before predictions freeze")
    if any((OUTCOME_INPUTS / name).exists() for name in OUTCOME_ARCHIVES):
        raise RuntimeError("future outcome archives are visible before predictions freeze")
    for name in OUTCOME_ARCHIVES:
        if (FEATURE_INPUTS / name).exists():
            raise RuntimeError("future outcome archive leaked into feature mount")


def command_verify_inputs() -> None:
    current = state()
    current.require(Stage.INIT)
    source = verify_source(ROOT)
    inventory = verify_inputs(FEATURE_INPUTS, OUTCOME_INPUTS, ZENODO_INPUTS, PREVIOUS_270)
    _frozen_write(ARTIFACTS / "input_inventory.json", {"source": source, **inventory})
    current.advance(Stage.INIT, Stage.INPUTS_VERIFIED, {"inventory_hash": inventory["inventory_hash"]})


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def command_verify_local_agent() -> None:
    current = state()
    current.require(Stage.INPUTS_VERIFIED)
    health = _get_json(AGENT_URL.rstrip("/") + "/health")
    models = _get_json(AGENT_URL.rstrip("/") + "/v1/models")
    probe = {
        "batch_id": "VERIFY-0001",
        "representation": "A0",
        "case_ids": ["E4_COMPANY_VERIFY"],
        "packet_hashes": [canonical_hash({"case_id": "E4_COMPANY_VERIFY"})],
        "packets": [{"case_id": "E4_COMPANY_VERIFY", "raw_fy2024": {"revenue": 100.0}, "raw_same_filing_fy2023": {"revenue": 120.0}}],
    }
    result = execute_batch(probe, AGENT_URL)
    if result.failures or len(result.cases) != 1:
        raise RuntimeError("genuine Local Agent structured inference verification failed")
    evidence = {
        "health": health,
        "models": models,
        "probe": result.cases,
        "runtime": RUNTIME,
        "runtime_digest": RUNTIME_DIGEST,
        "network": "Docker internal network finrisk-e4-internal",
        "agent_rootfs_read_only": True,
        "model_rootfs_read_only": True,
        "agent_mounts": ["/app/e4_local_agent_api.py:ro"],
        "model_mounts": ["/root/.ollama:ro"],
        "internet": "UNAVAILABLE_BY_INTERNAL_NETWORK",
    }
    _frozen_write(ARTIFACTS / "local_agent_verification.json", evidence)
    current.advance(Stage.INPUTS_VERIFIED, Stage.LOCAL_AGENT_VERIFIED, {"model": health["model"], "probe_hash": canonical_hash(result.cases)})


def _experiment_config() -> dict[str, Any]:
    inventory = read_json(ARTIFACTS / "input_inventory.json")
    local = read_json(ARTIFACTS / "local_agent_verification.json")
    return {
        "study": "E4",
        "source_commit": SOURCE_COMMIT,
        "source_tag": SOURCE_TAG,
        "data_inventory_hash": inventory["inventory_hash"],
        "data_hashes": {row["name"]: row["sha256"] for row in inventory["archives"]},
        "feature_archives": list(FEATURE_ARCHIVES),
        "outcome_archives": list(OUTCOME_ARCHIVES),
        "feature_fiscal_year": 2024,
        "filing_window": ["2024-07-01", "2025-06-30"],
        "outcome_window_months": 12,
        "eligibility": "original FY2024 10-K; non-financial SIC; computable B0 and same-filing temporal component",
        "previous_270_hash": inventory["previous_270"]["sha256"],
        "cohort_algorithm": "proportional SIC strata, largest remainder, ascending SHA-256 within stratum",
        "sampling_salts": {
            "cohort": "finrisk-e4-cohort-v1:",
            "agent": "finrisk-e4-agent-v1:",
            "stability": "finrisk-e4-stability-v1:",
            "batch_sensitivity": "finrisk-e4-batch-sensitivity-v1:",
        },
        "agent_cohort_limit": 50,
        "stability_limit": STABILITY_LIMIT,
        "batch_sensitivity_limit": BATCH_SENSITIVITY_LIMIT,
        "baselines": ["B0", "B1", "B2", "B3", "B6", "A0", "A1", "A2", "H0"],
        "local_agent": local,
        "agent_options": OPTIONS,
        "agent_representations": list(REPRESENTATIONS),
        "batching": {"target": 25, "context_budget_fraction": 0.7, "retry": 1, "recovery": "deterministic_bisect"},
        "hybrid": "H0 = 0.5 * B6 + 0.5 * A2",
        "threshold": 0.5,
        "primary_hypotheses": ["P1:B6-B0", "P2:H0-B0", "P3:H0-A2"],
        "bootstrap_samples": 5000,
        "label_permutations": 2000,
        "multiplicity": "Holm across P1/P2/P3",
        "seed": 20260924,
        "readme_claim_gate": "positive improvement only if paired AUROC CI lower > 0 and adjusted inference supports",
        "reliability": "UNCALIBRATED",
    }


def command_freeze_protocol() -> None:
    current = state()
    current.require(Stage.LOCAL_AGENT_VERIFIED)
    config = _experiment_config()
    config["config_hash"] = canonical_hash(config)
    protocol = ROOT / "research/e4/protocol/STUDY_PROTOCOL.md"
    if not protocol.exists():
        raise RuntimeError("STUDY_PROTOCOL.md is missing")
    _frozen_write(ROOT / "research/e4/protocol/experiment_config.json", config)
    freeze = {
        "immutable": True,
        "source_commit": SOURCE_COMMIT,
        "protocol_sha256": sha256_file(protocol),
        "config_hash": config["config_hash"],
        "input_inventory_hash": read_json(ARTIFACTS / "input_inventory.json")["inventory_hash"],
    }
    freeze["freeze_hash"] = canonical_hash(freeze)
    _frozen_write(ROOT / "research/e4/protocol/protocol_freeze.json", freeze)
    current.advance(Stage.LOCAL_AGENT_VERIFIED, Stage.PROTOCOL_FROZEN, {"freeze_hash": freeze["freeze_hash"]})


def command_build_cohort() -> None:
    current = state()
    current.require(Stage.PROTOCOL_FROZEN)
    _require_prediction_isolation()
    plan, report = build_cohort(ROOT, FEATURE_INPUTS, PREVIOUS_270, CACHE)
    if not report["company_disjoint"]:
        raise RuntimeError("E4 cohort is not company-disjoint")
    _frozen_write(ARTIFACTS / "cohort.json", plan)
    _frozen_write(ARTIFACTS / "cohort_report.json", report)
    current.advance(Stage.PROTOCOL_FROZEN, Stage.COHORT_FROZEN, {"count": len(plan), "cohort_hash": canonical_hash(plan)})


def command_build_features() -> None:
    current = state()
    current.require(Stage.COHORT_FROZEN)
    _require_prediction_isolation()
    plan = read_json(ARTIFACTS / "cohort.json")
    material = read_json(CACHE / "selected_feature_material.json")
    features, report = build_features(plan, material)
    _frozen_write(ARTIFACTS / "features.json", features)
    _frozen_write(ARTIFACTS / "feature_report.json", report)
    current.advance(Stage.COHORT_FROZEN, Stage.FEATURES_FROZEN, {"count": len(features), "feature_hash": report["feature_hash"]})


def _config_hash() -> str:
    return read_json(ROOT / "research/e4/protocol/experiment_config.json")["config_hash"]


def command_run_numeric() -> None:
    state().require(Stage.FEATURES_FROZEN)
    _require_prediction_isolation()
    path = ARTIFACTS / "numeric_predictions.json"
    if path.exists():
        raise RuntimeError("numeric predictions already exist")
    predictions, report = run_numeric(ROOT, read_json(ARTIFACTS / "features.json"), _config_hash())
    _frozen_write(path, predictions)
    _frozen_write(ARTIFACTS / "numeric_report.json", report)


def _selected_features(key: str) -> list[dict[str, Any]]:
    report = read_json(ARTIFACTS / "feature_report.json")
    ids = set(report[key])
    return [row for row in read_json(ARTIFACTS / "features.json") if row["observation_id"] in ids]


def command_run_agent() -> None:
    state().require(Stage.FEATURES_FROZEN)
    _require_prediction_isolation()
    output_path = ARTIFACTS / "agent_predictions.json"
    if output_path.exists():
        raise RuntimeError("Agent predictions already exist")
    rows = _selected_features("e4b_ids")
    manifest = build_manifest(rows)
    _frozen_write(ARTIFACTS / "agent_batch_manifest.json", manifest)
    predictions, raw = run_agent(rows, manifest, _config_hash(), AGENT_URL)
    _frozen_write(output_path, predictions)
    _frozen_write(ARTIFACTS / "agent_raw_responses.json", raw)

    stability_rows = _selected_features("stability_ids")
    stability_runs = []
    stability_raw = []
    for repeat in range(3):
        repeated, raw_repeat = run_agent(stability_rows, build_manifest(stability_rows), _config_hash(), AGENT_URL)
        stability_runs.extend({**row, "repeat": repeat} for row in repeated)
        stability_raw.append({"repeat": repeat, "raw": raw_repeat})
    _frozen_write(ARTIFACTS / "agent_stability_runs.json", stability_runs)
    _frozen_write(ARTIFACTS / "agent_stability_raw.json", stability_raw)

    sensitivity_rows = _selected_features("batch_sensitivity_ids")
    single_runs = []
    single_raw = []
    for row in sensitivity_rows:
        one_manifest = build_manifest([row])
        values, raw_one = run_agent([row], one_manifest, _config_hash(), AGENT_URL)
        single_runs.extend(values)
        single_raw.append({"observation_id": row["observation_id"], "raw": raw_one})
    _frozen_write(ARTIFACTS / "agent_single_case_predictions.json", single_runs)
    _frozen_write(ARTIFACTS / "agent_single_case_raw.json", single_raw)


def command_run_hybrid() -> None:
    state().require(Stage.FEATURES_FROZEN)
    _require_prediction_isolation()
    output = ARTIFACTS / "hybrid_predictions.json"
    if output.exists():
        raise RuntimeError("hybrid predictions already exist")
    values = hybrid_predictions(read_json(ARTIFACTS / "numeric_predictions.json"), read_json(ARTIFACTS / "agent_predictions.json"), _config_hash())
    _frozen_write(output, values)


def command_freeze_predictions() -> None:
    current = state()
    current.require(Stage.FEATURES_FROZEN)
    _require_prediction_isolation()
    required = [ARTIFACTS / name for name in ("numeric_predictions.json", "agent_predictions.json", "hybrid_predictions.json", "agent_batch_manifest.json", "agent_raw_responses.json")]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"cannot freeze incomplete predictions: {missing}")
    values = [row for name in ("numeric_predictions.json", "agent_predictions.json", "hybrid_predictions.json") for row in read_json(ARTIFACTS / name)]
    values.sort(key=lambda row: (row["observation_id"], row["model_id"]))
    freeze = {
        "immutable": True,
        "prediction_hash": canonical_hash(values),
        "count": len(values),
        "agent_manifest_hash": manifest_hash(read_json(ARTIFACTS / "agent_batch_manifest.json")),
        "config_hash": _config_hash(),
    }
    _frozen_write(ARTIFACTS / "predictions.json", values)
    _frozen_write(ARTIFACTS / "prediction_freeze.json", freeze)
    current.advance(Stage.FEATURES_FROZEN, Stage.PREDICTIONS_FROZEN, freeze)


def command_build_outcomes() -> None:
    current = state()
    current.require(Stage.PREDICTIONS_FROZEN)
    if not os.environ.get("E4_OUTCOME_INPUT_DIR"):
        raise RuntimeError("outcome stage requires an explicit future-only mount")
    labels, report = build_outcomes(read_json(ARTIFACTS / "features.json"), OUTCOME_INPUTS)
    _frozen_write(ARTIFACTS / "outcomes.json", labels)
    _frozen_write(ARTIFACTS / "outcome_report.json", report)
    current.advance(Stage.PREDICTIONS_FROZEN, Stage.OUTCOMES_FROZEN, {"label_hash": report["label_hash"], "status_counts": report["status_counts"]})


def _batch_sensitivity() -> dict[str, Any]:
    batched = {(row["observation_id"], row["model_id"]): row for row in read_json(ARTIFACTS / "agent_predictions.json")}
    single = read_json(ARTIFACTS / "agent_single_case_predictions.json")
    pairs = []
    for row in single:
        other = batched.get((row["observation_id"], row["model_id"]))
        if other and row.get("score") is not None and other.get("score") is not None:
            pairs.append({
                "observation_id": row["observation_id"],
                "model_id": row["model_id"],
                "single_score": row["score"],
                "batched_score": other["score"],
                "absolute_difference": abs(float(row["score"]) - float(other["score"])),
                "decision_agreement": row["prediction"] == other["prediction"],
            })
    return {
        "n_pairs": len(pairs),
        "mean_absolute_difference": sum(row["absolute_difference"] for row in pairs) / len(pairs) if pairs else None,
        "decision_agreement": sum(row["decision_agreement"] for row in pairs) / len(pairs) if pairs else None,
        "pairs": pairs,
    }


def command_evaluate() -> None:
    current = state()
    current.require(Stage.OUTCOMES_FROZEN)
    features = read_json(ARTIFACTS / "features.json")
    predictions = read_json(ARTIFACTS / "predictions.json")
    labels = read_json(ARTIFACTS / "outcomes.json")
    results = evaluate(features, predictions, labels)
    _frozen_write(ARTIFACTS / "evaluation.json", results)
    _frozen_write(ARTIFACTS / "threshold_sensitivity.json", threshold_sensitivity(results["analysis_rows"]))
    _frozen_write(ARTIFACTS / "sector_heterogeneity.json", sector_heterogeneity(results["analysis_rows"]))
    _frozen_write(ARTIFACTS / "missingness.json", missingness(features, labels))
    _frozen_write(ARTIFACTS / "attrition.json", label_attrition(features, labels))
    _frozen_write(ARTIFACTS / "source_concordance.json", source_concordance(ZENODO_INPUTS, features))
    _frozen_write(ARTIFACTS / "agent_stability_summary.json", stability_summary(read_json(ARTIFACTS / "agent_stability_runs.json")))
    _frozen_write(ARTIFACTS / "batch_sensitivity_summary.json", _batch_sensitivity())
    current.advance(Stage.OUTCOMES_FROZEN, Stage.EVALUATED, {"analysis_hash": results["analysis_hash"], "verified": results["verified_observations"], "events": results["verified_events"]})


def command_reproduce() -> None:
    current = state()
    current.require(Stage.EVALUATED)
    features = read_json(ARTIFACTS / "features.json")
    numeric_replay, _ = run_numeric(ROOT, features, _config_hash())
    numeric_equal = canonical_hash(numeric_replay) == canonical_hash(read_json(ARTIFACTS / "numeric_predictions.json"))
    hybrid_replay = hybrid_predictions(numeric_replay, read_json(ARTIFACTS / "agent_predictions.json"), _config_hash())
    hybrid_equal = canonical_hash(hybrid_replay) == canonical_hash(read_json(ARTIFACTS / "hybrid_predictions.json"))
    evaluation_replay = evaluate(features, read_json(ARTIFACTS / "predictions.json"), read_json(ARTIFACTS / "outcomes.json"))
    evaluation_equal = canonical_hash(evaluation_replay) == canonical_hash(read_json(ARTIFACTS / "evaluation.json"))
    summary = {
        "canonical_byte_identical": numeric_equal and hybrid_equal and evaluation_equal,
        "numeric_replay": numeric_equal,
        "hybrid_replay": hybrid_equal,
        "evaluation_replay": evaluation_equal,
        "agent_response_replay": "FROZEN_RESPONSE_PARSE_VERIFIED_BY_TEST_SUITE",
        "agent_stochasticity": "REPORTED_SEPARATELY",
    }
    if not summary["canonical_byte_identical"]:
        raise RuntimeError("E4 deterministic reproduction mismatch")
    _frozen_write(ARTIFACTS / "reproducibility_summary.json", summary)
    current.advance(Stage.EVALUATED, Stage.REPRODUCED, summary)


def command_status() -> None:
    print(json.dumps(state().snapshot(), indent=2, sort_keys=True))


def command_verify_agent_replay() -> None:
    state().require(Stage.REPRODUCED)
    replay = replay_frozen_agent(
        _selected_features("e4b_ids"),
        read_json(ARTIFACTS / "agent_batch_manifest.json"),
        read_json(ARTIFACTS / "agent_raw_responses.json"),
        _config_hash(),
    )
    expected = read_json(ARTIFACTS / "agent_predictions.json")
    evidence = {
        "canonical_byte_identical": canonical_hash(replay) == canonical_hash(expected),
        "prediction_count": len(replay),
        "replay_hash": canonical_hash(replay),
        "source": "frozen_http_responses_and_failure_records",
    }
    if not evidence["canonical_byte_identical"]:
        raise RuntimeError("frozen Agent response replay mismatch")
    _frozen_write(ARTIFACTS / "agent_replay_verification.json", evidence)


def command_verify_render_replay() -> None:
    from render_e4_readme import verify_render

    evidence = verify_render(ROOT, ARTIFACTS, state())
    _frozen_write(ARTIFACTS / "render_replay_verification.json", evidence)
    _frozen_write(ROOT / "research/e4/public/render_replay_verification.json", evidence)


def command_all() -> None:
    """Resume through the stages available in the current isolated phase."""
    while True:
        current = state().stage
        if current is Stage.INIT:
            command_verify_inputs()
        elif current is Stage.INPUTS_VERIFIED:
            command_verify_local_agent()
        elif current is Stage.LOCAL_AGENT_VERIFIED:
            command_freeze_protocol()
        elif current in {Stage.PROTOCOL_FROZEN, Stage.COHORT_FROZEN, Stage.FEATURES_FROZEN}:
            outcome_visible = os.environ.get("E4_OUTCOME_INPUT_DIR") or Path("/inputs/outcome").exists()
            outcome_visible = outcome_visible or any((OUTCOME_INPUTS / name).exists() for name in OUTCOME_ARCHIVES)
            if outcome_visible:
                print("E4 phase boundary: resume `all` in a feature-only container with no future outcome mount.")
                return
            if current is Stage.PROTOCOL_FROZEN:
                command_build_cohort()
            elif current is Stage.COHORT_FROZEN:
                command_build_features()
            else:
                if not (ARTIFACTS / "numeric_predictions.json").exists():
                    command_run_numeric()
                if not (ARTIFACTS / "agent_predictions.json").exists():
                    command_run_agent()
                if not (ARTIFACTS / "hybrid_predictions.json").exists():
                    command_run_hybrid()
                command_freeze_predictions()
        elif current is Stage.PREDICTIONS_FROZEN:
            if not os.environ.get("E4_OUTCOME_INPUT_DIR"):
                print("E4 phase boundary: resume `all` in a future-outcome-only container.")
                return
            command_build_outcomes()
        elif current is Stage.OUTCOMES_FROZEN:
            command_evaluate()
        elif current is Stage.EVALUATED:
            command_reproduce()
        elif current is Stage.REPRODUCED:
            from render_e4_readme import render

            render(ROOT, ARTIFACTS, state())
        else:
            command_status()
            return


COMMANDS = {
    "status": command_status,
    "verify-inputs": command_verify_inputs,
    "verify-local-agent": command_verify_local_agent,
    "freeze-protocol": command_freeze_protocol,
    "build-cohort": command_build_cohort,
    "build-features": command_build_features,
    "run-numeric": command_run_numeric,
    "run-agent": command_run_agent,
    "run-hybrid": command_run_hybrid,
    "freeze-predictions": command_freeze_predictions,
    "build-outcomes": command_build_outcomes,
    "evaluate": command_evaluate,
    "reproduce": command_reproduce,
    "verify-agent-replay": command_verify_agent_replay,
    "verify-render-replay": command_verify_render_replay,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=[*COMMANDS, "render-readme", "all"])
    args = parser.parse_args()
    if args.command == "all":
        command_all()
        return 0
    if args.command == "render-readme":
        from render_e4_readme import render

        render(ROOT, ARTIFACTS, state())
        return 0
    COMMANDS[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
