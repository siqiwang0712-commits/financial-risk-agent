"""Run deterministic post-E4 audit analyses without mutating frozen E4."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import locale
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from finrisk.e4_agent import MODEL, build_manifest, packet, run_agent
from finrisk.e4_core import canonical_hash, read_json, write_json
from finrisk.e4_evaluation import source_concordance
from finrisk.e4_posthoc import (
    agent_power_funnel,
    batch_sensitivity,
    calibration_diagnostics,
    fusion_sensitivity,
    integrity,
    schema_failure_diagnostics,
    verification_bias,
    zenodo_forensics,
)

ARTIFACTS = ROOT / "research/e4/_artifacts"
OUTPUT = Path(os.environ.get("E4_POSTHOC_OUTPUT", ROOT / "research/e4_posthoc"))
ZENODO = ROOT / "research/e4/_cache/inputs/zenodo"


def _environment() -> dict[str, object]:
    packages = {distribution.metadata["Name"]: distribution.version for distribution in importlib.metadata.distributions() if distribution.metadata.get("Name")}
    manifest = read_json(ARTIFACTS / "agent_batch_manifest.json")
    return {
        "captured_without_secrets": True,
        "python": sys.version,
        "python_executable_kind": Path(sys.executable).name,
        "platform": platform.platform(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "locale": locale.getlocale(),
        "timezone": os.environ.get("TZ", "system-default"),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        "packages": dict(sorted(packages.items())),
        "agent_runtime": {key: manifest[key] for key in ("runtime", "runtime_digest", "model", "model_digest", "model_blob_digest", "tokenizer", "quantization", "context_limit", "options")},
        "docker": {
            "client": "29.7.2/windows-amd64",
            "server": "Docker Desktop 4.90.0 / Engine 29.7.2 / linux-amd64",
            "kernel": "6.18.33.2-microsoft-standard-WSL2",
            "agent_api_image": "sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9",
            "ollama_image": "sha256:8ab809d178ea5c67bfffdfece64f9d68faf2a810addfe107de864b1c76106ba5",
            "network": "finrisk-e4-internal",
            "root_filesystems_read_only": True,
        },
        "determinism": {"seed": 20260925, "json": "UTF-8, sorted keys, compact separators", "ordering": "explicitly sorted"},
    }


def run() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    features = read_json(ARTIFACTS / "features.json")
    outcomes = read_json(ARTIFACTS / "outcomes.json")
    predictions = read_json(ARTIFACTS / "predictions.json")
    evaluation = read_json(ARTIFACTS / "evaluation.json")
    size_two_path = OUTPUT / "batch_sensitivity/batch_size_2_predictions.json"
    size_two = read_json(size_two_path) if size_two_path.exists() else None
    jobs = {
        OUTPUT / "integrity_verification.json": integrity(ROOT, ARTIFACTS),
        OUTPUT / "verification_bias/verification_bias_diagnostics.json": verification_bias(features, outcomes, predictions),
        OUTPUT / "agent_power/agent_coverage_funnel.json": agent_power_funnel(read_json(ARTIFACTS / "feature_report.json"), outcomes, read_json(ARTIFACTS / "agent_predictions.json")),
        OUTPUT / "batch_sensitivity/batch_context_diagnostics.json": batch_sensitivity(read_json(ARTIFACTS / "batch_sensitivity_summary.json"), outcomes, features, size_two),
        OUTPUT / "schema_failures/schema_failure_diagnostics.json": schema_failure_diagnostics(read_json(ARTIFACTS / "agent_raw_responses.json"), read_json(ARTIFACTS / "agent_batch_manifest.json")),
        OUTPUT / "fusion_sensitivity/fusion_weight_grid.json": fusion_sensitivity(evaluation),
        OUTPUT / "calibration_diagnostics/calibration_diagnostics.json": calibration_diagnostics(evaluation),
        OUTPUT / "zenodo_forensics/concordance_error_taxonomy.json": zenodo_forensics(ZENODO, features),
        OUTPUT / "zenodo_forensics/post_e4_period_matched_concordance.json": source_concordance(ZENODO, features),
        OUTPUT / "environment_manifest.json": _environment(),
    }
    for path, value in jobs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, value)
    print(json.dumps({"outputs": [str(path.relative_to(ROOT)) for path in jobs], "integrity_valid": jobs[OUTPUT / "integrity_verification.json"]["valid"]}, indent=2))


def run_batch_size_two() -> None:
    selected = set(read_json(ARTIFACTS / "feature_report.json")["batch_sensitivity_ids"])
    rows = [row for row in read_json(ARTIFACTS / "features.json") if row["observation_id"] in selected]
    base = build_manifest(rows)
    batches = []
    for representation in ("A0", "A1"):
        packets = [packet(row, representation) for row in rows]
        for index in range(0, len(packets), 2):
            items = packets[index:index + 2]
            batches.append({
                "batch_id": f"POSTHOC-{representation}-{index // 2 + 1:04d}",
                "representation": representation,
                "case_ids": [item["case_id"] for item in items],
                "packet_hashes": [canonical_hash(item) for item in items],
                "packets": items,
            })
    manifest = {**base, "version": "e4-posthoc-batch-size-2-v1", "model": MODEL, "batches": batches}
    predictions, raw = run_agent(rows, manifest, "POST_HOC_BATCH_SIZE_2", os.environ.get("E4_AGENT_URL", "http://finrisk-e4-agent-api:8080"))
    target = OUTPUT / "batch_sensitivity"
    target.mkdir(parents=True, exist_ok=True)
    write_json(target / "batch_size_2_manifest.json", manifest)
    write_json(target / "batch_size_2_predictions.json", predictions)
    write_json(target / "batch_size_2_raw_responses.json", raw)
    print(json.dumps({"predictions": len(predictions), "failures": len(raw["failures"])}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("all", "run-batch-size-two"))
    args = parser.parse_args()
    if args.command == "all":
        run()
    else:
        run_batch_size_two()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
