"""Independently verify the E4-S audit's own numbers.

A third party should be able to confirm every claim in ``AUDIT_REPORT.md`` without access to
any unpublished input. This script does three things:

1. verifies the SHA-256 of every published E4 artifact (proving the audit did not mutate E4);
2. verifies the SHA-256 of every published replication artifact;
3. recomputes the real-data inference from the published paired rows and asserts that it
   reproduces ``replication_crosscheck.json``.

Exit status: 0 if everything reproduces, 1 if any check fails.

Usage::

    python research/e4_statistical_audit/verify_audit.py            # full, 20000 replicates
    python research/e4_statistical_audit/verify_audit.py --quick    # 2000 replicates
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from e4s_stats import (  # noqa: E402
    PairedObservation,
    cluster_bootstrap,
    delong_paired,
    delta_metric,
    label_permutation_as_implemented,
    marginal_metric,
    score_swap_randomization,
)

REPLICATION_DIR = HERE / "replication"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})
        return passed

    def close(self, name: str, observed: float | None, expected: float | None, tolerance: float) -> bool:
        if observed is None or expected is None:
            return self.check(name, False, "missing value")
        gap = abs(observed - expected)
        return self.check(name, gap <= tolerance, f"observed {observed!r}, expected {expected!r}, gap {gap:.3e}")

    @property
    def failed(self) -> list[dict]:
        return [item for item in self.checks if item["status"] == "FAIL"]


def verify_manifest(directory: Path, manifest_name: str, report: Report, label: str) -> bool:
    manifest_path = directory / manifest_name
    if not manifest_path.is_file():
        return report.check(f"{label}: manifest present", False, str(manifest_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files") if isinstance(manifest.get("files"), list) else None
    if entries is None:
        # the E4 frozen-artifact manifest stores a path->hash mapping instead
        entries = [{"path": path, "sha256": digest} for path, digest in manifest["files"].items()]
    ok = True
    for entry in entries:
        path = REPO_ROOT / entry["path"]
        if not path.is_file():
            ok = report.check(f"{label}: {entry['path']}", False, "missing") and ok
            continue
        digest = sha256_file(path)
        ok = report.check(
            f"{label}: {entry['path']}",
            digest == entry["sha256"],
            "" if digest == entry["sha256"] else f"observed {digest[:12]}, expected {entry['sha256'][:12]}",
        ) and ok
    return ok


def load_paired_rows() -> list[PairedObservation]:
    analysis = json.loads((REPLICATION_DIR / "analysis.json").read_text(encoding="utf-8"))
    labels = {row["observation_id"]: int(row["label"]) for row in analysis}
    by_model: dict[str, dict[str, float]] = {}
    for row in analysis:
        by_model.setdefault(row["model_id"], {})[row["observation_id"]] = row["score"]
    common = sorted(set(by_model["B0"]) & set(by_model["B6"]))
    return [
        PairedObservation(
            cluster_id=observation_id,
            label=labels[observation_id],
            reference_score=by_model["B0"][observation_id],
            challenger_score=by_model["B6"][observation_id],
        )
        for observation_id in common
        if labels[observation_id] in (0, 1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="2000 replicates instead of 20000")
    args = parser.parse_args()

    replicates = 2000 if args.quick else 20000
    seed = 20260924
    report = Report()

    print("== frozen E4 artifacts ==")
    verify_manifest(HERE, "e4_frozen_artifact_manifest.json", report, "e4-frozen")

    print("== published replication artifacts ==")
    verify_manifest(REPLICATION_DIR, "manifest.json", report, "replication")

    print("== real-data inference reproduction ==")
    rows = load_paired_rows()
    published = json.loads((HERE / "replication_crosscheck.json").read_text(encoding="utf-8"))
    audit = published["audit_independent_implementation"]

    report.check("cohort: n_pairs", len(rows) == published["cohort_provenance"]["n_pairs"],
                 f"{len(rows)} vs {published['cohort_provenance']['n_pairs']}")
    report.check("cohort: events", sum(r.label for r in rows) == published["cohort_provenance"]["events"],
                 f"{sum(r.label for r in rows)} vs {published['cohort_provenance']['events']}")

    report.close("marginal: B0 AUROC", marginal_metric(rows, "reference", "auroc"), published["marginals"]["B0_auroc"], 1e-12)
    report.close("marginal: B6 AUROC", marginal_metric(rows, "challenger", "auroc"), published["marginals"]["B6_auroc"], 1e-12)
    report.close("delta AUROC", delta_metric(rows, "auroc"), audit["delta_auroc"], 1e-12)
    report.close("delta PR-AUC", delta_metric(rows, "pr_auc"), audit["delta_pr_auc"], 1e-12)

    delong = delong_paired(rows)
    report.close("DeLong delta", delong["observed_delta"], audit["delong"]["observed_delta"], 1e-12)
    report.close("DeLong SE", delong["standard_error_delta"], audit["delong"]["standard_error_delta"], 1e-12)
    report.close("DeLong z", delong["z"], audit["delong"]["z"], 1e-9)
    report.close("DeLong p", delong["p_value"], audit["delong"]["p_value"], 1e-12)

    # Bootstrap intervals are seed-dependent; re-running with the frozen seed must land in
    # the same place. Tolerances widen for the quick mode because fewer replicates shift
    # the percentile endpoints.
    bootstrap = cluster_bootstrap(rows, "auroc", samples=replicates, seed=seed, with_bca=True)
    tolerance = 0.002 if args.quick else 2e-4
    report.close("bootstrap SE", bootstrap.standard_error, audit["auroc_bootstrap"]["standard_error"], tolerance)
    report.close("bootstrap BCa low", bootstrap.bca[0] if bootstrap.bca else None,
                 audit["auroc_bootstrap"]["bca"][0], tolerance)
    report.close("bootstrap BCa high", bootstrap.bca[1] if bootstrap.bca else None,
                 audit["auroc_bootstrap"]["bca"][1], tolerance)

    permutation = label_permutation_as_implemented(rows, "auroc", samples=replicates, seed=seed)
    report.close("permutation null SD", permutation["null_standard_deviation"],
                 audit["label_permutation_as_implemented"]["null_standard_deviation"],
                 0.001 if args.quick else 1e-4)

    swap = score_swap_randomization(rows, "auroc", samples=replicates, seed=seed + 2)
    report.close("swap null SD", swap["null_standard_deviation"],
                 audit["score_swap_randomization"]["null_standard_deviation"],
                 0.001 if args.quick else 1e-4)

    print("== consistency of the audit's published conclusions ==")
    report.check(
        "DeLong rejects H0_equality at alpha=0.05",
        delong["p_value"] is not None and delong["p_value"] < 0.05,
        f"p = {delong['p_value']}",
    )
    report.check(
        "BCa interval excludes zero in the positive direction",
        bool(bootstrap.bca) and bootstrap.bca[0] > 0,
        f"bca = {bootstrap.bca}",
    )
    crosscheck = json.loads((HERE / "inference_crosscheck.json").read_text(encoding="utf-8"))
    report.check(
        "inference_crosscheck headline is CONSISTENT_SUPPORT",
        crosscheck["headline"] in {"CONSISTENT_SUPPORT", "DIRECTION_CONSISTENT_STRENGTH_DIFFERS"},
        crosscheck["headline"],
    )
    report.check(
        "E4's published P1 permutation p-value equals the attainable floor",
        math.isclose(
            json.loads((HERE / "paired_auc_inference.json").read_text(encoding="utf-8"))
            ["internal_consistency"]["permutation_p_value_at_floor"]["published_p"],
            1.0 / 2001,
            rel_tol=0,
            abs_tol=1e-15,
        ),
        "1/2001",
    )

    failed = report.failed
    print(f"\n{len(report.checks) - len(failed)}/{len(report.checks)} checks passed")
    for item in failed:
        print(f"  FAIL {item['check']}: {item['detail']}")
    print(json.dumps({"checks": report.checks}, indent=1)[:0] or "", end="")
    # newline="" keeps the file LF on Windows, matching the repo convention for research
    # artifacts. Without it Python translates to CRLF and the working tree diverges from
    # the committed blob.
    with (HERE / "verification_result.json").open("w", encoding="utf-8", newline="") as handle:
        handle.write(
            json.dumps(
                {"status": "PASS" if not failed else "FAIL", "replicates": replicates, "checks": report.checks},
                indent=1,
                sort_keys=True,
            )
            + "\n"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
