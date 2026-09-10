from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research/empirical_v1"
RESULTS = ROOT / "research/results/v0.3.1/empirical_numeric"
FORENSICS = ROOT / "research/results/v0.3.1/benchmark_forensics"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a non-overwriting forensic experiment snapshot")
    parser.add_argument("experiment_id", choices=("v0.3.1-E1-diagnostic", "v0.3.1-E2", "v0.3.1-E3"))
    args = parser.parse_args()
    destination = FORENSICS / args.experiment_id
    if destination.exists():
        raise RuntimeError(f"immutable experiment already exists: {destination}")
    destination.mkdir(parents=True)
    manifests = {
        "v0.3.1-E1-diagnostic": DATA / "experiment_manifest.numeric_v031.corrected-v3.json",
        "v0.3.1-E2": DATA / "experiment_manifest.numeric_v031.E2.json",
        "v0.3.1-E3": DATA / "experiment_manifest.numeric_v031.E3.json",
    }
    experiment_manifest = manifests[args.experiment_id]
    inputs = {
        "corpus_manifest.json": DATA / "corpus_manifest.json",
        "deterioration_labels.json": DATA / "deterioration_labels.json",
        "integrity_report.json": DATA / "integrity_report.json",
        "experiment_manifest.json": experiment_manifest,
        "results.json": RESULTS / "results.json",
        "b0_predictions.json": RESULTS / "b0_predictions.json",
        "b1_predictions.json": RESULTS / "b1_predictions.json",
        "b2_predictions.json": RESULTS / "b2_predictions.json",
        "b6_predictions.json": RESULTS / "b6_predictions.json",
        "temporal_trajectories.json": RESULTS / "temporal_trajectories.json",
        "annual_outcome_corpus.json": DATA / "annual_outcome_corpus.json",
        "reported_fcf_periods.json": DATA / "reported_fcf_periods.json",
    }
    missing = [name for name, path in inputs.items() if not path.exists()]
    if missing:
        raise RuntimeError(f"cannot freeze incomplete experiment: {missing}")
    hashes = {}
    for name, source in inputs.items():
        shutil.copy2(source, destination / name)
        hashes[name] = sha256(destination / name)
    manifest = {
        "experiment_id": args.experiment_id,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "immutable": True,
        "artifact_hashes": hashes,
        "configuration_hashes": {
            "rules": sha256(ROOT / "rules/rules.json"),
            "label_schema": sha256(ROOT / "research/label_schema.json"),
            "numeric_model_code": sha256(ROOT / "backend/finrisk/numeric_benchmark.py"),
            "runner_code": sha256(ROOT / "scripts/run_numeric_benchmarks.py"),
        },
        "overwrite_policy": "FAIL_IF_EXISTS",
    }
    manifest["manifest_hash"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (destination / "forensic_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
