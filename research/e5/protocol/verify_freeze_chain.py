"""Verify the E5 staged freeze chain.

Reads ``research/e5/freeze/<stage>.json`` manifests and mechanically checks:

1. the nine stage manifests appear in the required order with non-decreasing timestamps;
2. every artifact hash in every manifest matches the file on disk;
3. ``previous_manifest_hash`` chains correctly from the second stage onward;
4. the protocol document hash matches the hash recorded in the manifests;
5. the stage that introduces outcome data is the only one that may reference outcomes.

Run with ``--report-only`` to print the state without failing on an incomplete chain.
Exit status is 0 when the chain is complete and valid, 1 when it is broken, and 2 when the
study is simply not frozen yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

PROTOCOL_DIR = Path(__file__).resolve().parent
E5_DIR = PROTOCOL_DIR.parent
FREEZE_DIR = E5_DIR / "freeze"
PROTOCOL_DOC = PROTOCOL_DIR / "STUDY_PROTOCOL.md"

REQUIRED_STAGES = (
    "protocol",
    "agent-qualification",
    "cohort-freeze",
    "feature-freeze",
    "prediction-freeze",
    "outcome-unlock",
    "adjudication",
    "evaluation",
    "results",
)

OUTCOME_BEARING_STAGES = frozenset({"outcome-unlock", "adjudication", "evaluation", "results"})
OUTCOME_TOKENS = ("outcome", "label")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_manifest_hash(manifest: dict) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_manifests() -> dict[str, dict]:
    if not FREEZE_DIR.is_dir():
        return {}
    manifests: dict[str, dict] = {}
    for path in sorted(FREEZE_DIR.glob("*.json")):
        try:
            manifests[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            manifests[path.stem] = {"_unreadable": str(exc)}
    return manifests


def verify(manifests: dict[str, dict], repo_root: Path) -> dict:
    findings: list[dict] = []

    def fail(check: str, detail: str) -> None:
        findings.append({"check": check, "status": "FAIL", "detail": detail})

    def ok(check: str, detail: str) -> None:
        findings.append({"check": check, "status": "PASS", "detail": detail})

    present = [stage for stage in REQUIRED_STAGES if stage in manifests]
    missing = [stage for stage in REQUIRED_STAGES if stage not in manifests]
    if not present:
        return {
            "status": "NOT_FROZEN",
            "stages_present": [],
            "stages_missing": list(REQUIRED_STAGES),
            "findings": [],
        }

    # order
    indices = [REQUIRED_STAGES.index(stage) for stage in present]
    if indices != sorted(indices):
        fail("stage_order", f"stages are not in the required order: {present}")
    else:
        ok("stage_order", f"stages in order: {present}")

    # timestamps
    stamps = []
    for stage in present:
        value = manifests[stage].get("created_at_utc")
        if value is None:
            fail("timestamp", f"{stage} has no created_at_utc")
            continue
        try:
            stamps.append((stage, datetime.fromisoformat(value.replace("Z", "+00:00"))))
        except ValueError:
            fail("timestamp", f"{stage} has an unparsable created_at_utc: {value}")
    for (earlier, first), (later, second) in zip(stamps, stamps[1:]):
        if second < first:
            fail("timestamp_monotonic", f"{later} ({second}) precedes {earlier} ({first})")
    if stamps and not any(f["check"] == "timestamp_monotonic" for f in findings):
        ok("timestamp_monotonic", f"{len(stamps)} stage timestamps are non-decreasing")

    # artifact hashes
    for stage in present:
        manifest = manifests[stage]
        artifacts = manifest.get("artifacts", [])
        if not artifacts:
            fail("artifacts", f"{stage} lists no artifacts")
            continue
        for artifact in artifacts:
            path = repo_root / artifact["path"]
            if not path.is_file():
                fail("artifact_present", f"{stage}: missing {artifact['path']}")
                continue
            if sha256_file(path) != artifact["sha256"]:
                fail("artifact_hash", f"{stage}: hash mismatch for {artifact['path']}")
        if not any(f["check"] == "artifact_hash" and f["status"] == "FAIL" for f in findings):
            ok("artifact_hash", f"{stage}: {len(artifacts)} artifact hashes verified")

    # chain
    for previous, current in zip(present, present[1:]):
        recorded = manifests[current].get("previous_manifest_hash")
        if recorded is None:
            fail("chain", f"{current} has no previous_manifest_hash")
            continue
        expected = canonical_manifest_hash(manifests[previous])
        if recorded != expected:
            fail("chain", f"{current}.previous_manifest_hash does not match the canonical hash of {previous}")
        else:
            ok("chain", f"{current} chains to {previous}")

    # protocol hash
    protocol_hash = sha256_file(PROTOCOL_DOC)
    for stage in present:
        recorded = manifests[stage].get("protocol_sha256")
        if recorded and recorded != protocol_hash:
            fail("protocol_hash", f"{stage} records protocol_sha256 {recorded[:12]} but the file hashes to {protocol_hash[:12]}")
    if not any(f["check"] == "protocol_hash" and f["status"] == "FAIL" for f in findings):
        ok("protocol_hash", f"protocol document hash consistent: {protocol_hash[:12]}")

    # outcome isolation
    for stage in present:
        if stage in OUTCOME_BEARING_STAGES:
            continue
        for artifact in manifests[stage].get("artifacts", []):
            lowered = artifact["path"].lower()
            if any(token in lowered for token in OUTCOME_TOKENS):
                fail("outcome_isolation", f"{stage} references a possible outcome artifact before the unlock stage: {artifact['path']}")
    if not any(f["check"] == "outcome_isolation" and f["status"] == "FAIL" for f in findings):
        ok("outcome_isolation", "no pre-unlock stage references an outcome artifact")

    status = "BROKEN" if any(f["status"] == "FAIL" for f in findings) else (
        "COMPLETE" if not missing else "PARTIAL"
    )
    return {
        "status": status,
        "stages_present": present,
        "stages_missing": missing,
        "protocol_sha256": protocol_hash,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="do not fail on an incomplete chain")
    parser.add_argument("--repo-root", default=None, help="repository root (default: three levels up)")
    args = parser.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else PROTOCOL_DIR.parents[2]
    result = verify(load_manifests(), repo_root)
    print(json.dumps(result, indent=1))

    if result["status"] == "BROKEN":
        return 1
    if result["status"] in {"NOT_FROZEN", "PARTIAL"}:
        return 0 if args.report_only else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
