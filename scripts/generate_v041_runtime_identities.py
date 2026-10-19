"""Generate or verify the v0.4.1 Assurance-policy and certificate identities."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from finrisk.assurance.policy import AssurancePolicy

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research" / "v041_development" / "runtime_identities.json"


def _sha(path: Path, read_bytes=None) -> str:
    # Runtime identities describe source content, not a checkout platform's
    # newline conversion. Git stores these text files with LF, while Windows
    # may materialize CRLF (or legacy mixed endings) in the working tree.
    canonical = (read_bytes(path) if read_bytes else path.read_bytes()).replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()


def build(read_bytes=None) -> dict:
    policy_config_path = ROOT / "config" / "assurance_policy.json"
    policy_mapping = json.loads(read_bytes(policy_config_path) if read_bytes else policy_config_path.read_bytes())
    policy = AssurancePolicy.from_mapping(policy_mapping)
    bundle_path = ROOT / "backend" / "finrisk" / "enterprise" / "decision_bundle.py"
    reason_path = ROOT / "backend" / "finrisk" / "assurance" / "reason_codes.py"
    policy_path = ROOT / "backend" / "finrisk" / "assurance" / "policy.py"
    payload = {
        "schema_version": "1",
        "release_identity": "v0.4.1",
        "scope": "RELEASE_IDENTITY_NOT_E5_FREEZE",
        "assurance_policy": {
            "status": "READY_FOR_V0.4.1",
            "maturity": policy.maturity.value,
            "version": policy.version,
            "policy_hash": policy.policy_hash,
            "config": "config/assurance_policy.json",
            "config_sha256": _sha(policy_config_path, read_bytes),
            "implementation": "backend/finrisk/assurance/policy.py",
            "implementation_sha256": _sha(policy_path, read_bytes),
            "reason_codes": "backend/finrisk/assurance/reason_codes.py",
            "reason_codes_sha256": _sha(reason_path, read_bytes),
            "calibration_status": "UNCALIBRATED",
        },
        "decision_certificate": {
            "status": "READY_FOR_V0.4.1",
            "schema_version": "decision-certificate-v0.4",
            "implementation": "backend/finrisk/enterprise/decision_bundle.py",
            "implementation_sha256": _sha(bundle_path, read_bytes),
            "serialization_contract": "dataclass_to_dict_then_material_decision_payload_canonical_hash",
            "hash_behavior": "any_material_mutation_invalidates_bundle_and_certificate_hash",
            "replay_requirement": "verified AssuranceResult, policy identity, material inputs and component versions",
            "e5_freeze_identity": "TO_BE_FROZEN",
        },
    }
    payload["identity_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = _canonical(build())
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
            raise SystemExit("v0.4.1 runtime identity drift")
        print("v0.4.1 runtime identities: PASS")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(expected)
    print(OUTPUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
