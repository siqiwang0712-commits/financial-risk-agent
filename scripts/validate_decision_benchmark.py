import argparse
import json
from pathlib import Path

from finrisk.benchmark_protocol import validate_company_year_manifest

parser = argparse.ArgumentParser(
    description="Validate a point-in-time FinRisk company-year manifest"
)
parser.add_argument("manifest", type=Path)
args = parser.parse_args()
result = validate_company_year_manifest(
    json.loads(args.manifest.read_text(encoding="utf-8"))
)
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["valid"] else 1)
