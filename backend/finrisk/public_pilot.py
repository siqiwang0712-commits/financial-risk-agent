"""Cached projection of the immutable public-pilot research artifact."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import __version__


class PublicPilotUnavailable(RuntimeError):
    """The frozen public snapshot cannot satisfy the published API contract."""


@lru_cache(maxsize=4)
def public_pilot_payload(root: Path) -> dict:
    try:
        payload = json.loads(
            (root / "research/results/public_v1/summary.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError) as exc:
        raise PublicPilotUnavailable("public pilot snapshot is unavailable") from exc

    full_hybrid = next(
        (
            item
            for item in payload.get("summaries", [])
            if item.get("baseline") == "full_hybrid"
        ),
        None,
    )
    if full_hybrid is None:
        raise PublicPilotUnavailable(
            "public pilot snapshot is missing the full_hybrid baseline"
        )
    return {
        "snapshot": "v0.3.0 frozen public pilot",
        "runtime": f"v{__version__}",
        "annotation_status": payload.get("annotation_status"),
        "benchmark_evidence_coverage": full_hybrid["evidence_coverage"],
        "rows": [
            {
                "entity": item.get("company"),
                "decision": "FLAG" if item.get("prediction") else "PASS",
                "score": item.get("overall_score"),
                "reliability": "UNCALIBRATED",
                "filing": item.get("example_id"),
            }
            for item in payload.get("decompositions", [])
        ],
    }
