#!/usr/bin/env python
"""Check that the current environment matches a frozen E5 environment manifest.

E4 needed an undocumented environment override: the frozen
``FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES`` default is 256 MB while the real SEC FSDS
``num.txt`` members are 500-600 MB, so the outcome stage could not run without raising it,
and nothing in E4 recorded that. E5 freezes required environment variables explicitly, and
this script is the mechanical check.

    python research/e5/harness/verify_environment.py --freeze   # write a manifest
    python research/e5/harness/verify_environment.py            # check against it
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS_DIR))

from e5_harness import (
    E5_DIR,
    REPO_ROOT,
    canonical_bytes,
    capture_environment,
    check_environment,
    sha256_bytes,
)

DEFAULT_MANIFEST = E5_DIR / "harness" / "environment_manifest.json"
DEFAULT_REQUIRED_VARIABLES = {"FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES": "2147483648"}


def _read_required_variables() -> dict[str, str]:
    config = E5_DIR / "protocol" / "experiment_config.json"
    if not config.is_file():
        return dict(DEFAULT_REQUIRED_VARIABLES)
    payload = json.loads(config.read_text(encoding="utf-8"))
    declared = payload.get("environment_variables") or {}
    return {
        name: str(value)
        for name, value in declared.items()
        if not name.startswith("_")
    } or dict(DEFAULT_REQUIRED_VARIABLES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--freeze", action="store_true", help="write a fresh environment manifest")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)

    if args.freeze:
        environment = capture_environment(_read_required_variables())
        environment["environment_manifest_sha256"] = None
        environment["environment_manifest_sha256"] = sha256_bytes(
            canonical_bytes({k: v for k, v in environment.items() if k != "environment_manifest_sha256"})
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(environment, indent=1, sort_keys=True) + "\n")
        print(f"froze environment manifest at {manifest_path}")
        return 0

    if not manifest_path.is_file():
        print(f"no frozen environment manifest at {manifest_path}; run with --freeze first")
        return 2

    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    findings = check_environment(recorded)
    failed = [item for item in findings if item["status"] == "FAIL"]
    print(f"environment: {len(findings) - len(failed)}/{len(findings)} checks passed")
    for item in failed:
        print(f"  FAIL {item['check']}: {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
