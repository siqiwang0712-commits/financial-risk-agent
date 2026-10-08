"""Verify v0.4.2 release metadata and all preserved historical research gates."""

import argparse
import re
import sys
from pathlib import Path

from scripts.verify_v041 import run, verify_artifacts

ROOT = Path(__file__).resolve().parents[1]


def verify_release_metadata(root: Path = ROOT) -> None:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = re.findall(r"^## \[([^\]]+)\]", changelog, re.MULTILINE)
    if not versions or versions[0] != "0.4.2":
        raise SystemExit("newest changelog release must be 0.4.2")
    for relative in ("RELEASE_NOTES_v0.4.2.md", "PROJECT_STATUS.md", "README.md", "README.zh-CN.md"):
        if "v0.4.2" not in (root / relative).read_text(encoding="utf-8")[:1500]:
            raise SystemExit(f"current release documentation drift: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true")
    parser.parse_args()
    verify_release_metadata()
    run("historical synthetic source byte identity", [sys.executable, "scripts/generate_v040_development_reference.py", "--check"])
    verify_artifacts("scripts/generate_v042_runtime_identities.py", expected_version="0.4.2")
    print("v0.4.2 release metadata and historical artifacts: PASS (not a release publication)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
