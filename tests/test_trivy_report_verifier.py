"""The machine-readable Trivy reports must be checked, not merely uploaded.

The `scan` job used to end its report-generation step with `|| true`, so a scanner
that never started produced no file, no error, and a green step: "the scan could not
run" and "the scan ran and recorded its findings" were the same outcome.
`scripts/verify_trivy_report.py` is the assertion that replaced it, and these tests
pin the failures it has to catch — especially the one that matters most, a report
that describes a tag or a rebuilt image instead of the candidate digest.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "verify_trivy_report", ROOT / "scripts" / "verify_trivy_report.py"
)
assert _SPEC is not None and _SPEC.loader is not None
verify_trivy_report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_trivy_report)

DIGEST = "sha256:" + "a" * 64
REFERENCE = f"ghcr.io/siqiwang0712-commits/financial-risk-agent-api@{DIGEST}"


def write(tmp_path: Path, payload) -> Path:
    path = tmp_path / "trivy.json"
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def report(**overrides) -> dict:
    document = {
        "SchemaVersion": 2,
        "ArtifactName": REFERENCE,
        "Metadata": {"OS": {"Family": "debian", "Name": "13.7"}},
        "Results": [],
    }
    document.update(overrides)
    return document


def test_a_report_for_the_candidate_digest_is_accepted(tmp_path):
    document = verify_trivy_report.load_report(write(tmp_path, report()))
    assert verify_trivy_report.assert_scanned_digest(document, DIGEST) == REFERENCE
    verify_trivy_report.assert_report_shape(document)


def test_a_missing_report_is_a_failure_not_an_empty_artifact(tmp_path):
    with pytest.raises(SystemExit, match="did not run"):
        verify_trivy_report.load_report(tmp_path / "absent.json")


def test_an_empty_or_unparseable_report_is_a_failure(tmp_path):
    with pytest.raises(SystemExit, match="empty"):
        verify_trivy_report.load_report(write(tmp_path, b""))
    with pytest.raises(SystemExit, match="not valid JSON"):
        verify_trivy_report.load_report(write(tmp_path, b"{not json"))


def test_a_tag_or_foreign_digest_cannot_satisfy_the_assertion(tmp_path):
    for artifact in (
        "ghcr.io/siqiwang0712-commits/financial-risk-agent-api:latest",
        "ghcr.io/siqiwang0712-commits/financial-risk-agent-api@sha256:" + "b" * 64,
    ):
        document = verify_trivy_report.load_report(write(tmp_path, report(ArtifactName=artifact)))
        with pytest.raises(SystemExit, match="candidate"):
            verify_trivy_report.assert_scanned_digest(document, DIGEST)

    document = verify_trivy_report.load_report(write(tmp_path, report(ArtifactName=None)))
    with pytest.raises(SystemExit, match="ArtifactName"):
        verify_trivy_report.assert_scanned_digest(document, DIGEST)


def test_a_report_that_never_resolved_an_image_is_a_failure(tmp_path):
    cases = (
        (report(SchemaVersion=None), "SchemaVersion"),
        (report(Metadata={}), "Metadata"),
        (report(Results={}), "Results"),
    )
    for document, expected in cases:
        loaded = verify_trivy_report.load_report(write(tmp_path, document))
        with pytest.raises(SystemExit, match=expected):
            verify_trivy_report.assert_report_shape(loaded)


def test_main_reports_the_scanned_reference(tmp_path, monkeypatch, capsys):
    path = write(tmp_path, report())
    monkeypatch.setattr(
        "sys.argv",
        ["verify_trivy_report.py", "--report", str(path), "--digest", DIGEST],
    )
    verify_trivy_report.main()
    assert REFERENCE in capsys.readouterr().out


def test_release_upload_retains_hidden_scan_reports_and_fails_if_missing():
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    uploads = [
        step for step in workflow["jobs"]["scan"]["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == ".runtime/trivy-*.json"
    assert upload["with"]["include-hidden-files"] is True
    assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize('artifact', [
    f'ghcr.io/image:{DIGEST}', f'ghcr.io/image@{DIGEST}ff',
    f'ghcr.io/image@{DIGEST}:latest',
])
def test_digest_substrings_are_not_artifact_identity(artifact):
    with pytest.raises(SystemExit, match='candidate'):
        verify_trivy_report.assert_scanned_digest(report(ArtifactName=artifact), DIGEST)


@pytest.mark.parametrize('digest', ['', 'sha256:', 'sha256:' + 'a'*63, 'sha256:' + 'g'*64])
def test_invalid_expected_digest_cannot_match_a_report(digest):
    with pytest.raises(SystemExit, match='candidate'):
        verify_trivy_report.assert_scanned_digest(report(), digest)
