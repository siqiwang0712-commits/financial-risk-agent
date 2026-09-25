"""Verify a candidate ``previous_270.json`` and, if it is genuine, reconstruct E4's exact cohort.

Why this exists
---------------
E4's cohort cannot be rebuilt by an outside party because
``research/e4/_cache/previous_270.json`` — the 270-CIK exclusion set — is unpublished. Only
its SHA-256 is pinned, in ``finrisk.e4_core.PREVIOUS_270_SHA256``. That single missing file
is what makes E4's P1 `NOT_INDEPENDENTLY_REPRODUCIBLE` and what blocks E5 from proving
company-disjointness against the prior cohort.

This script turns "publish the file" from a request into a one-command check:

1. ``--candidate PATH`` verifies the file against the pinned SHA-256 and shape. No SEC data
   needed.
2. ``--rebuild`` additionally runs the **frozen** ``build_cohort`` with that exclusion set,
   reproducing E4's exact 2,000-company cohort, and compares it against the published
   replication cohort to give the true overlap and the exact index mapping.

The point is that the verification does not depend on trusting this audit: the hash is the
frozen constant, and the cohort reconstruction is the frozen function.

Usage::

    python research/e4_statistical_audit/verify_previous_270.py --candidate path/to/previous_270.json
    python research/e4_statistical_audit/verify_previous_270.py --candidate ... --rebuild \\
        --feature-dir path/to/feature/archives --cache-dir /tmp/e4cache
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "backend"))

# The pinned hash is read from the frozen module when the full FinRisk dependency stack is
# importable, and otherwise from a literal. A test asserts the literal against the frozen
# source *text*, so the fallback cannot silently drift from ``finrisk.e4_core``.
_FALLBACK_PREVIOUS_270_SHA256 = "d73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603"
try:  # pragma: no cover - depends on the ambient dependency set
    from finrisk.e4_core import PREVIOUS_270_SHA256 as _FROZEN_PREVIOUS_270_SHA256

    PREVIOUS_270_SHA256 = _FROZEN_PREVIOUS_270_SHA256
    PINNED_HASH_SOURCE = "finrisk.e4_core"
except ImportError:  # pragma: no cover - the minimal audit venv takes this path
    PREVIOUS_270_SHA256 = _FALLBACK_PREVIOUS_270_SHA256
    PINNED_HASH_SOURCE = "literal_fallback"

REPLICATION_COHORT = HERE / "replication" / "cohort.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_candidate(path: Path) -> dict:
    """Check a candidate file against the pinned hash and the frozen shape contract."""
    result: dict = {
        "candidate": str(path),
        "pinned_sha256": PREVIOUS_270_SHA256,
        "exists": path.is_file(),
    }
    if not path.is_file():
        result["status"] = "MISSING"
        return result

    digest = sha256_file(path)
    result["observed_sha256"] = digest
    result["hash_matches"] = digest == PREVIOUS_270_SHA256
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        result["status"] = "NOT_JSON"
        result["error"] = str(exc)
        return result

    result["is_list"] = isinstance(rows, list)
    result["count"] = len(rows) if isinstance(rows, list) else None
    if isinstance(rows, list):
        ciks = [str(row.get("cik", "")).zfill(10) for row in rows if isinstance(row, dict)]
        result["cik_count"] = len(ciks)
        result["unique_ciks"] = len(set(ciks))
        result["all_ten_digits"] = all(len(cik) == 10 and cik.isdigit() for cik in ciks)

    if not result["hash_matches"]:
        result["status"] = "REJECTED_HASH_MISMATCH"
        result["note"] = (
            "The pinned SHA-256 is the frozen constant from finrisk.e4_core, so a mismatch "
            "means this is not the file E4 used. Do not use it to claim E4 reproduction."
        )
    elif not result.get("is_list") or result.get("count") != 270:
        result["status"] = "REJECTED_SHAPE"
    else:
        result["status"] = "GENUINE"
        result["note"] = "This is E4's exact exclusion set; the cohort can now be rebuilt."
    return result


def compare_cohorts(e4_plan: list[dict], replication_cohort: list[dict]) -> dict:
    """Pure comparison of two masked cohorts keyed by CIK."""
    e4_by_cik = {str(row["cik"]).zfill(10): row for row in e4_plan}
    replication_by_cik = {str(row["cik"]).zfill(10): row for row in replication_cohort}
    e4_ciks, replication_ciks = set(e4_by_cik), set(replication_by_cik)
    shared = e4_ciks & replication_ciks

    def observation_id(cik: str) -> str | None:
        row = e4_by_cik.get(cik)
        return row.get("observation_id") if row else None

    return {
        "e4_cohort_size": len(e4_ciks),
        "replication_cohort_size": len(replication_ciks),
        "shared": len(shared),
        "shared_fraction_of_e4": len(shared) / len(e4_ciks) if e4_ciks else None,
        "in_e4_only": len(e4_ciks - replication_ciks),
        "in_replication_only": len(replication_ciks - e4_ciks),
        "symmetric_difference": len(e4_ciks ^ replication_ciks),
        "index_mapping_examples": [
            {
                "cik": cik,
                "e4_observation_id": observation_id(cik),
                "replication_observation_id": replication_by_cik[cik]["observation_id"],
                "same_index": observation_id(cik) == replication_by_cik[cik]["observation_id"],
            }
            for cik in sorted(shared)[:10]
        ],
    }


def rebuild_e4_cohort(candidate: Path, feature_dir: Path, cache_dir: Path) -> dict:
    """Run the frozen cohort builder with the genuine exclusion set."""
    from finrisk.e4_core import build_cohort

    plan, report = build_cohort(REPO_ROOT, feature_dir, candidate, cache_dir)
    return {"plan": plan, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", required=True, help="path to a candidate previous_270.json")
    parser.add_argument("--rebuild", action="store_true", help="rebuild E4's cohort (requires the SEC feature archives)")
    parser.add_argument("--feature-dir", default=None, help="directory holding 2024q3..2025q2.zip")
    parser.add_argument("--cache-dir", default=None, help="scratch directory for the frozen cohort builder")
    parser.add_argument("--out", default=str(HERE / "previous_270_verification.json"))
    args = parser.parse_args()

    candidate = Path(args.candidate)
    payload: dict = {"verification": verify_candidate(candidate)}
    print(json.dumps(payload["verification"], indent=1))

    if payload["verification"]["status"] != "GENUINE":
        print(f"\nstatus: {payload['verification']['status']} — stopping.")
        Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return 1

    if not args.rebuild:
        print(
            "\nThe candidate is genuine. Re-run with --rebuild (and --feature-dir) to reconstruct "
            "E4's exact cohort and measure the true overlap with the published replication cohort."
        )
        Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return 0

    if not args.feature_dir:
        print("\n--rebuild needs --feature-dir pointing at 2024q3.zip .. 2025q2.zip")
        return 2

    cache_dir = Path(args.cache_dir) if args.cache_dir else Path(tempfile.mkdtemp(prefix="e4-cohort-"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    rebuilt = rebuild_e4_cohort(candidate, Path(args.feature_dir), cache_dir)
    payload["e4_cohort_report"] = rebuilt["report"]

    if REPLICATION_COHORT.is_file():
        replication = json.loads(REPLICATION_COHORT.read_text(encoding="utf-8"))
        payload["overlap_with_replication"] = compare_cohorts(rebuilt["plan"], replication)
    else:
        payload["overlap_with_replication"] = None

    payload["next_steps"] = [
        "Re-run the numeric pipeline on E4's rebuilt cohort to obtain a true reproduction of E4-A.",
        "Set FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES above the largest num.txt before building outcomes.",
        "Compare the rebuilt cohort's B0/B6 scores and labels against E4's published summary.",
    ]
    Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["overlap_with_replication"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
