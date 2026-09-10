from __future__ import annotations

import argparse
import json
from pathlib import Path

from finrisk.reproducibility import verify_frozen_experiment

ROOT = Path(__file__).resolve().parents[1]
FORENSICS = ROOT / "research/results/v0.3.1/benchmark_forensics"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only verification of a frozen experiment")
    parser.add_argument("experiment_id", choices=("v0.3.1-E1-diagnostic", "v0.3.1-E2", "v0.3.1-E3"))
    args = parser.parse_args()
    report = verify_frozen_experiment(FORENSICS / args.experiment_id, ROOT)
    print(json.dumps(report, indent=2))
    return 0 if report["artifact_integrity"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
