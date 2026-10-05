"""Report stage-aware E5 readiness without executing or freezing E5."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research" / "e5_readiness" / "preflight_v041.json"


def _read(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    e5 = _read("research/e5/experiment_config.json")
    model = _read("research/strong_tabular_reference/artifacts/artifact_manifest.json")
    data = _read("research/strong_tabular_reference/development_data_manifest.json")
    identities = _read("research/v041_development/runtime_identities.json")
    protocol_blockers = [
        "primary authorization-quality estimands remain TO_BE_FROZEN",
        "multiplicity alpha and minimum meaningful effects remain TO_BE_FROZEN",
        "final E5 reference-distribution design remains TO_BE_FROZEN",
        "S1 threshold/policy identity remains TO_BE_FROZEN for prospective E5",
    ]
    cohort_blockers = [
        "future feature/outcome window is unavailable and cohort is not enumerated",
        "research/e4/_cache/previous_270.json is unavailable",
        "future eligibility and sampling rules remain TO_BE_FROZEN",
    ]
    prediction_blockers = [
        "protocol and cohort freezes have not completed",
        "final E5-bound S0 identity and S1-S4 implementation identities are not frozen",
        "prediction environment/container and outcome-mount isolation are not frozen",
    ]
    outcome_blockers = [
        "prediction freeze has not completed",
        "arm completeness, deviation log, adjudication and analysis policy are not frozen",
    ]
    payload = {
        "schema_version": "1",
        "study": "E5",
        "status": "BLOCKED",
        "e5_executed": False,
        "e5_frozen": False,
        "inputs": {
            "authoritative_protocol": e5["authoritative_protocol"]["path"],
            "historical_s0_status": model["status"],
            "historical_s0_artifact_hash": model["hashes"]["fitted_artifact_hash"],
            "development_data_status": data["status"],
            "development_exclusions": data["isolation"]["e5_exclusion_scope"],
            "assurance_policy_hash": identities["assurance_policy"]["policy_hash"],
            "certificate_schema": identities["decision_certificate"]["schema_version"],
            "calibration_status": "RESOLVED_AS_UNCALIBRATED_FOR_V0.4.1",
        },
        "stages": {
            "protocol_freeze": {"status": "BLOCKED", "blockers": protocol_blockers},
            "cohort_freeze": {"status": "BLOCKED", "blockers": cohort_blockers},
            "prediction_freeze": {
                "status": "NOT_YET_APPLICABLE",
                "blockers": prediction_blockers,
            },
            "outcome_unlock": {
                "status": "NOT_YET_APPLICABLE",
                "blockers": outcome_blockers,
            },
        },
    }
    payload["preflight_sha256"] = hashlib.sha256(
        (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode()
    ).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = (json.dumps(build(), indent=1, sort_keys=True) + "\n").encode()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
            raise SystemExit("E5 preflight artifact drift")
        print("E5 preflight: PASS (BLOCKED / DRAFT_NOT_FROZEN)")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(expected)
    print(OUTPUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
