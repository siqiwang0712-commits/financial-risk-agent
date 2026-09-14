"""Validate a point-in-time FinRisk company-year manifest.

Run explicitly. Importing this module used to parse `sys.argv` and exit the
interpreter with status 2 when the required positional argument was absent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finrisk.benchmark_protocol import validate_company_year_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a point-in-time FinRisk company-year manifest"
    )
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    result = validate_company_year_manifest(
        json.loads(args.manifest.read_text(encoding="utf-8"))
    )
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
