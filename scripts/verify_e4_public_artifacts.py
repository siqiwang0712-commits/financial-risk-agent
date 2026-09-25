"""Verify the checked-in v0.3.4/E4 public research surface."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "research/e4/public"
SOL = ROOT / "research/e4_posthoc/model_capacity/sol_codex_agent"
SOURCE_COMMIT = "4273b070678240fe7cbdf01a17527afcc71c500e"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify() -> dict[str, Any]:
    required = {
        "VALIDATION_REPORT.md",
        "CONCLUSION.md",
        "readme_summary.json",
        "reproducibility_summary.json",
        "render_replay_verification.json",
        "auroc_ci.svg",
        "paired_delta_auroc.svg",
    }
    missing = sorted(name for name in required if not (PUBLIC / name).is_file())
    if missing:
        raise RuntimeError(f"missing E4 public artifacts: {missing}")

    summary = _read(PUBLIC / "readme_summary.json")
    if summary["source_commit"] != SOURCE_COMMIT:
        raise RuntimeError("E4 public summary source commit mismatch")
    if summary["outcomes"] != {
        "cohort_n": 2000,
        "event_prevalence": 235 / 674,
        "events": 235,
        "status_counts": {
            "INSUFFICIENT_DATA": 755,
            "REQUIRES_HUMAN_REVIEW": 571,
            "VERIFIED": 674,
        },
        "verified_coverage": 0.337,
        "verified_n": 674,
    }:
        raise RuntimeError("E4 public outcome summary mismatch")
    if summary["claim_gate"] != {
        "P1": "POSITIVE_PAIRED_AUROC_IMPROVEMENT",
        "P2": "NOT_ESTABLISHED",
        "P3": "NOT_ESTABLISHED",
    }:
        raise RuntimeError("E4 public claim gate mismatch")
    if not _read(PUBLIC / "reproducibility_summary.json")["canonical_byte_identical"]:
        raise RuntimeError("E4 deterministic reproduction is not byte-identical")
    if not _read(PUBLIC / "render_replay_verification.json")["byte_identical"]:
        raise RuntimeError("E4 public render replay mismatch")

    sol_manifest = _read(SOL / "manifest.json")
    sol_predictions = _read(SOL / "predictions.json")
    prediction_hash = hashlib.sha256(
        (SOL / "predictions.json").read_bytes()
    ).hexdigest()
    if prediction_hash != sol_manifest["prediction_file_sha256"]:
        raise RuntimeError("post-hoc comparator prediction hash mismatch")
    if (
        len(sol_predictions) != 150
        or len({(row["masked_company_id"], row["model_id"]) for row in sol_predictions})
        != 150
    ):
        raise RuntimeError("post-hoc comparator coverage mismatch")
    if (
        sol_manifest["evidence_status"] != "POST_HOC"
        or sol_manifest["exact_underlying_model_id"] != "NOT_EXPOSED_BY_PLATFORM"
    ):
        raise RuntimeError("post-hoc comparator identity/evidence boundary mismatch")

    patterns = (
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"Authorization\s*:", re.IGNORECASE),
        re.compile(r"[A-Za-z]:\\Users\\"),
    )
    scanned = [
        path
        for directory in (PUBLIC, SOL)
        for path in directory.rglob("*")
        if path.is_file()
    ]
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in patterns):
            raise RuntimeError(
                f"private value or local path found in {path.relative_to(ROOT)}"
            )

    return {
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "e4_verified": summary["outcomes"]["verified_n"],
        "e4_events": summary["outcomes"]["events"],
        "posthoc_predictions": len(sol_predictions),
        "scanned_files": len(scanned),
    }


def main() -> int:
    print(json.dumps(verify(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
