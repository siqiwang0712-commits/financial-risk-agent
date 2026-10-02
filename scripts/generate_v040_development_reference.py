"""Generate the synthetic v0.4 development-only distribution reference.

This artifact exists only to exercise Assurance Runtime states reproducibly. It is
not a population estimate, calibration set, prospective cohort, or external validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("FINRISK_LLM_PROVIDER", "mock")

from finrisk.enterprise.decision import canonical_hash
from finrisk.pipeline import FinRiskPipeline

SOURCE = ROOT / "examples" / "synthetic_company.json"
TARGET = ROOT / "research" / "v040_development" / "development_reference.json"
SOURCE_COMMIT = "69cafe6a8afbb35aceec27a8e27660419d401b57"


def build() -> dict:
    fixture = json.loads(SOURCE.read_text(encoding="utf-8"))
    current = fixture["current"]
    pipeline = FinRiskPipeline(ROOT)
    assessment = pipeline.assess(
        fixture["company"],
        fixture["fiscal_year"],
        current,
        fixture["previous"],
        {int(key): value for key, value in fixture["pages"].items()},
    )
    availability = assessment.reporting_observability
    availability_rate = sum(availability.values()) / len(availability)
    bounds: dict[str, list[float]] = {}
    statistics: dict[str, dict[str, float | int]] = {}
    for name, raw in sorted(current.items()):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        value = float(raw)
        width = max(abs(value) * 0.5, 1.0)
        lower, upper = max(0.0, value - width), value + width
        bounds[name] = [lower, upper]
        statistics[name] = {
            "n": 1,
            "observed_min": value,
            "observed_max": value,
            "development_lower": lower,
            "development_upper": upper,
        }
    payload = {
        "name": "FinRisk synthetic development reference",
        "version": "v0.4.0-development-reference-1",
        "scope": "DEVELOPMENT_REFERENCE_ONLY",
        "status_labels": [
            "RETROSPECTIVE",
            "POST_HOC",
            "DEVELOPMENT",
            "NOT_CONFIRMATORY",
        ],
        "source_cohort_identity": "examples/synthetic_company.json:Northstar Components (Synthetic)",
        "source_commit": SOURCE_COMMIT,
        "source_fixture_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "feature_schema": {
            "kind": "normalized raw financial values",
            "features": sorted(bounds),
            "reporting_observability_separate": True,
        },
        "reference_statistics": statistics,
        "feature_bounds": bounds,
        "allowed_sectors": ["industrial"],
        "required_features": sorted(bounds),
        "minimum_reporting_availability": round(max(0.0, availability_rate - 0.01), 6),
        "maximum_outside_fraction": 0.1,
        "generation_method": (
            "Single synthetic fixture; each observed non-negative financial value receives "
            "a deterministic ±50% envelope with a minimum width of 1. Reporting availability "
            "uses the pipeline's expected-feature schema and a 0.01 tolerance."
        ),
        "limitations": [
            "Not representative of any issuer population.",
            "Not suitable for calibration, probability claims, or automated real-world admission.",
            "Only synthetic/demo and deterministic development tests may load this artifact.",
            "Unknown or unsupported real-world inputs must continue to fail closed.",
        ],
    }
    return {**payload, "artifact_hash": canonical_hash(payload)}


def render() -> str:
    return json.dumps(build(), indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = render()
    if args.check:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != generated:
            print("development reference is stale")
            return 1
        print("development reference is current and hash-reproducible")
        return 0
    TARGET.write_text(generated, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
