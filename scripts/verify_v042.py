"""Verify v0.4.2 development while preserving all historical research gates."""

import argparse

from scripts.verify_v041 import verify_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true")
    parser.parse_args()
    verify_artifacts("scripts/generate_v042_runtime_identities.py")
    print("v0.4.2 development and historical artifacts: PASS (not a release publication)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
