"""Separate current v0.4.2 candidate identities from immutable historical evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from scripts import generate_v041_runtime_identities as previous

ROOT = previous.ROOT
BASE = "e60abba2976e389ddf80a147227a56cc4cad8e06"
OUTPUT = ROOT / "research/v042_development/runtime_identities.json"


def historical_bytes(path: Path) -> bytes:
    relative = path.relative_to(ROOT).as_posix()
    return subprocess.check_output(["git", "show", f"{BASE}:{relative}"], cwd=ROOT)


def verify_historical() -> None:
    path = ROOT / "research/v041_development/runtime_identities.json"
    if path.read_bytes() != historical_bytes(path):
        raise ValueError("v0.4.1 release identity bytes changed")
    if json.loads(path.read_bytes()) != previous.build(historical_bytes):
        raise ValueError("v0.4.1 identities do not match their historical source")


def build() -> dict:
    value = previous.build()
    value.pop("identity_sha256")
    value.update(release_identity="v0.4.2", scope="RELEASE_CANDIDATE_NOT_PUBLISHED_NOT_E5_FREEZE",
                 historical_release_source=BASE)
    for name in ("assurance_policy", "decision_certificate"):
        value[name]["status"] = "RELEASE_CANDIDATE_NOT_PUBLISHED"
    # The current implementation, including the changed verifier, stays bound.
    value["security_boundary_sources"] = {
        name: previous._sha(ROOT / name)
        for name in (
            "backend/finrisk/assurance/engine.py", "backend/finrisk/assurance/semantics.py",
            "backend/finrisk/assurance/certificate.py",
            "backend/finrisk/enterprise/postgres.py", "backend/finrisk/enterprise/repository.py",
            "backend/finrisk/llm.py", "backend/finrisk/process_isolation.py",
            "backend/finrisk/request_boundary.py", "backend/finrisk/upload_boundary.py",
            "backend/finrisk/runtime.py", "backend/finrisk/api.py",
            "backend/finrisk/__init__.py", "pyproject.toml",
            "frontend/package.json", "frontend/package-lock.json",
            "backend/Dockerfile", "frontend/Dockerfile",
            "scripts/verify_candidate_image.py", "scripts/verify_release_ci.py",
            "scripts/verify_trivy_report.py", "scripts/verify_v041_release.py",
            "scripts/verify_v042_release.py",
            ".github/workflows/container-release.yml",
        )
    }
    value["identity_sha256"] = hashlib.sha256(previous._canonical(value)).hexdigest()
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    verify_historical()
    expected = previous._canonical(build())
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
            raise SystemExit("v0.4.2 development runtime identity drift")
        print("v0.4.1 historical / v0.4.2 current development identities: PASS")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(expected)
        print(OUTPUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
