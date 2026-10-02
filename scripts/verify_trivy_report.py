"""Assert that a machine-readable Trivy report really describes the candidate digest.

The `scan` job uploads `.runtime/trivy-*.json` as an audit artifact, and until now
nothing checked that those files existed or what they contained. The step that
produced them ended in `|| true`, so a scanner that never started (a bad image
reference, a registry hiccup, a missing Docker socket) was indistinguishable from a
scan that ran and recorded its findings: the step reported success, the artifact
upload reported "no files found", and the job moved on.

This script is the missing assertion. It fails the run when a report is absent,
unparseable, or was produced against something other than the digest the build job
published — which is the only way to keep "we scanned the artifact we are about to
release" a checked claim rather than a comment.

    python scripts/verify_trivy_report.py --report .runtime/trivy-api.json \
        --digest sha256:0000...

Importing this module must not touch the filesystem.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# `Metadata.OS` is only populated once Trivy has actually resolved the image under
# scan, so its presence is what distinguishes a real report from a stub file.
REQUIRED_METADATA_KEYS = ("OS",)


def load_report(report: Path) -> dict:
    """Read and parse a Trivy JSON report, failing loudly on anything unexpected."""
    if not report.is_file():
        raise SystemExit(
            f"{report} was not produced: the scanner did not run. Check the Trivy "
            "step above for an execution error before treating this run as scanned."
        )
    if report.stat().st_size == 0:
        raise SystemExit(f"{report} is empty: the scanner produced no report body.")
    try:
        return json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{report} is not valid JSON: {exc}") from exc


def assert_scanned_digest(document: dict, digest: str) -> str:
    """Return the scanned artifact reference, asserting it is the candidate digest."""
    artifact = document.get("ArtifactName")
    if not isinstance(artifact, str) or not artifact:
        raise SystemExit("the report carries no ArtifactName, so it records nothing.")
    # A tag reference would mean the scan could have resolved to a different artifact
    # than the one the build job published and the verify job exercised.
    if digest not in artifact:
        raise SystemExit(
            f"the report scanned {artifact!r}, which does not reference the candidate "
            f"digest {digest!r}. A tag or a rebuilt image must never satisfy this gate."
        )
    return artifact


def assert_report_shape(document: dict) -> None:
    if not document.get("SchemaVersion"):
        raise SystemExit("the report has no SchemaVersion, so it is not a Trivy report.")
    metadata = document.get("Metadata") or {}
    missing = [key for key in REQUIRED_METADATA_KEYS if not metadata.get(key)]
    if missing:
        raise SystemExit(
            "the report is missing " + ", ".join(missing) + " in Metadata, which means "
            "the scanner never resolved the image it claims to have scanned."
        )
    results = document.get("Results")
    if results is not None and not isinstance(results, list):
        raise SystemExit("the report's Results field is not a list.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path, help="Trivy JSON report to check")
    parser.add_argument("--digest", required=True, help="candidate image digest, sha256:...")
    args = parser.parse_args()

    document = load_report(args.report)
    artifact = assert_scanned_digest(document, args.digest)
    assert_report_shape(document)

    findings = sum(
        len(result.get("Vulnerabilities") or [])
        for result in (document.get("Results") or [])
    )
    print(
        f"{args.report}: {artifact} "
        f"(schema {document['SchemaVersion']}, {findings} recorded finding(s))"
    )


if __name__ == "__main__":
    main()
