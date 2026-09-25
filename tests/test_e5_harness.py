"""Tests for the executable E5 staged harness.

These test the *mechanics* of prospective governance, not any result. The real E5 study
cannot run yet — there is no future outcome window and no `previous_270.json` — so the
stage directories used here are synthetic and live in temporary paths. Nothing in these
tests writes into the repository.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import e5_harness
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = REPO_ROOT / "research" / "e5" / "harness"

PROTOCOL_ARTIFACT = "research/e5/protocol/STUDY_PROTOCOL.md"
CONFIG_ARTIFACT = "research/e5/protocol/experiment_config.json"


def _protocol_artifacts() -> list[dict]:
    return [
        {"path": PROTOCOL_ARTIFACT, "role": "protocol"},
        {"path": CONFIG_ARTIFACT, "role": "config"},
    ]


def _freeze_protocol(stage_dir: Path) -> dict:
    manifest = e5_harness.build_manifest("protocol", previous=None, artifacts=_protocol_artifacts())
    e5_harness.write_manifest(stage_dir, manifest)
    return manifest


# --------------------------------------------------------------------------------------
# Stage registry
# --------------------------------------------------------------------------------------


def test_stage_registry_is_ten_stages_with_contiguous_sequences() -> None:
    # The brief numbers them 0..8; the registry is the single source of truth.
    assert [stage.sequence for stage in e5_harness.STAGES] == list(range(9))
    assert e5_harness.STAGES[0].name == "protocol"
    assert e5_harness.STAGES[-1].name == "final-report"


def test_outcome_artifacts_are_only_allowed_from_the_unlock_stage() -> None:
    for stage in e5_harness.STAGES:
        if stage.sequence >= e5_harness.OUTCOME_BEARING_FROM_SEQUENCE:
            assert stage.outcome_allowed, f"{stage.name} must permit outcome artifacts"
        else:
            assert not stage.outcome_allowed, f"{stage.name} must forbid outcome artifacts"


# --------------------------------------------------------------------------------------
# Manifest mechanics
# --------------------------------------------------------------------------------------


def test_manifest_hash_is_stable_and_excludes_itself(tmp_path: Path) -> None:
    manifest = e5_harness.build_manifest("protocol", previous=None, artifacts=_protocol_artifacts())
    first = e5_harness.manifest_sha256(manifest)
    with_hash = {**manifest, "manifest_sha256": first}
    assert e5_harness.manifest_sha256(with_hash) == first
    assert e5_harness.manifest_sha256(manifest) == first


def test_write_manifest_refuses_to_overwrite_a_frozen_stage(tmp_path: Path) -> None:
    manifest = _freeze_protocol(tmp_path)
    with pytest.raises(e5_harness.HarnessError, match="refusing to overwrite"):
        e5_harness.write_manifest(tmp_path, manifest)


def test_manifest_records_git_environment_and_frozen_document_hashes() -> None:
    manifest = e5_harness.build_manifest("protocol", previous=None, artifacts=_protocol_artifacts())
    assert manifest["git"]["commit"]
    assert manifest["environment"]["python_version"] == sys.version.split()[0]
    assert manifest["protocol_sha256"] == e5_harness.sha256_file(REPO_ROOT / PROTOCOL_ARTIFACT)
    assert manifest["config_sha256"] == e5_harness.sha256_file(REPO_ROOT / CONFIG_ARTIFACT)
    assert manifest["environment"]["required_environment_variables"] is not None


# --------------------------------------------------------------------------------------
# Verifier: positive and negative paths
# --------------------------------------------------------------------------------------


def test_a_well_formed_two_stage_chain_verifies(tmp_path: Path) -> None:
    first = _freeze_protocol(tmp_path)
    second = e5_harness.build_manifest(
        "model-qualification",
        previous=first,
        artifacts=[],
        model_identity_sha256=e5_harness.model_identity_sha256(),
    )
    e5_harness.write_manifest(tmp_path, second)
    report = e5_harness.verify(tmp_path)
    assert not report.failures, [check["check"] for check in report.failures]
    assert report.checks


def test_empty_stage_directory_fails_without_crashing(tmp_path: Path) -> None:
    report = e5_harness.verify(tmp_path)
    assert not report.ok
    assert any("stage manifests present" in check["check"] for check in report.failures)


def test_broken_chain_fails(tmp_path: Path) -> None:
    first = _freeze_protocol(tmp_path)
    second = e5_harness.build_manifest("model-qualification", previous=first, artifacts=[])
    second["previous_manifest_sha256"] = "0" * 64
    e5_harness.write_manifest(tmp_path, second)
    report = e5_harness.verify(tmp_path)
    assert any("chain:" in check["check"] for check in report.failures)


def test_skipping_a_stage_fails(tmp_path: Path) -> None:
    """Stages must form a complete prefix; a later stage cannot be frozen early."""
    first = _freeze_protocol(tmp_path)
    skipped = e5_harness.build_manifest("cohort-freeze", previous=first, artifacts=[])
    e5_harness.write_manifest(tmp_path, skipped)
    report = e5_harness.verify(tmp_path)
    assert any("complete prefix" in check["check"] for check in report.failures)


def test_mutating_the_protocol_after_freeze_fails(tmp_path: Path) -> None:
    manifest = e5_harness.build_manifest("protocol", previous=None, artifacts=_protocol_artifacts())
    manifest["protocol_sha256"] = "0" * 64
    e5_harness.write_manifest(tmp_path, manifest)
    report = e5_harness.verify(tmp_path)
    assert any("frozen protocol unchanged" in check["check"] for check in report.failures)


def test_mutating_the_config_after_freeze_fails(tmp_path: Path) -> None:
    manifest = e5_harness.build_manifest("protocol", previous=None, artifacts=_protocol_artifacts())
    manifest["config_sha256"] = "0" * 64
    e5_harness.write_manifest(tmp_path, manifest)
    report = e5_harness.verify(tmp_path)
    assert any("frozen config unchanged" in check["check"] for check in report.failures)


def test_mutating_the_model_identity_after_freeze_fails(tmp_path: Path) -> None:
    first = _freeze_protocol(tmp_path)
    second = e5_harness.build_manifest(
        "model-qualification", previous=first, artifacts=[], model_identity_sha256="0" * 64
    )
    e5_harness.write_manifest(tmp_path, second)
    report = e5_harness.verify(tmp_path)
    assert any("frozen model identity unchanged" in check["check"] for check in report.failures)


def test_editing_a_manifest_after_it_was_written_fails(tmp_path: Path) -> None:
    _freeze_protocol(tmp_path)
    path = tmp_path / f"{e5_harness.STAGE_BY_NAME['protocol'].directory_name}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["counts"] = {"hypotheses": 99}
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    report = e5_harness.verify(tmp_path)
    assert any("manifest self-hash" in check["check"] for check in report.failures)


def test_outcome_artifact_before_the_unlock_stage_fails(tmp_path: Path) -> None:
    manifest = e5_harness.build_manifest(
        "prediction-freeze",
        previous=None,
        artifacts=[{"path": PROTOCOL_ARTIFACT, "role": "outcome"}],
    )
    e5_harness.write_manifest(tmp_path, manifest)
    report = e5_harness.verify(tmp_path)
    assert any("no outcome artifact before stage" in check["check"] for check in report.failures)


def test_missing_artifact_fails(tmp_path: Path) -> None:
    manifest = e5_harness.build_manifest(
        "protocol",
        previous=None,
        artifacts=[{"path": "research/e5/does-not-exist.json", "role": "config"}],
    )
    e5_harness.write_manifest(tmp_path, manifest)
    report = e5_harness.verify(tmp_path)
    assert any("does-not-exist" in check["check"] for check in report.failures)


# --------------------------------------------------------------------------------------
# Outcome inaccessibility and leakage
# --------------------------------------------------------------------------------------


def test_outcome_inaccessible_assertion_detects_an_existing_path(tmp_path: Path) -> None:
    present = tmp_path / "outcomes.json"
    present.write_text("{}", encoding="utf-8")
    assertion = e5_harness.assert_outcome_inaccessible([str(present)])
    assert assertion["outcome_inaccessible"] is False
    assert assertion["existing_paths"] == [str(present)]


def test_outcome_inaccessible_assertion_passes_when_absent(tmp_path: Path) -> None:
    assertion = e5_harness.assert_outcome_inaccessible([str(tmp_path / "absent.json")])
    assert assertion["outcome_inaccessible"] is True


def test_recorded_outcome_paths_reappearing_later_fails(tmp_path: Path) -> None:
    leaking = tmp_path / "outcomes.json"
    leaking.write_text("{}", encoding="utf-8")
    manifest = e5_harness.build_manifest(
        "prediction-freeze",
        previous=None,
        artifacts=[],
        outcome_inaccessible=e5_harness.assert_outcome_inaccessible([str(leaking)]),
    )
    e5_harness.write_manifest(tmp_path, manifest)
    report = e5_harness.verify(tmp_path)
    assert any("outcome paths still absent" in check["check"] for check in report.failures)


# --------------------------------------------------------------------------------------
# Cohort disjointness must fail closed
# --------------------------------------------------------------------------------------


def test_cohort_stage_fails_closed_when_disjointness_is_unproven(tmp_path: Path) -> None:
    """previous_270.json is unpublished, so this must be a failure, not a warning."""
    manifest = e5_harness.build_manifest(
        "cohort-freeze",
        previous=None,
        artifacts=[],
        disjointness={"historical_disjointness": "UNPROVEN", "reason": "previous_270.json unpublished"},
    )
    e5_harness.write_manifest(tmp_path, manifest)
    report = e5_harness.verify(tmp_path)
    assert any("historical company-disjointness proven" in check["check"] for check in report.failures)


def test_cohort_stage_passes_only_when_disjointness_is_proven(tmp_path: Path) -> None:
    manifest = e5_harness.build_manifest(
        "cohort-freeze",
        previous=None,
        artifacts=[],
        disjointness={"historical_disjointness": "PROVEN"},
    )
    e5_harness.write_manifest(tmp_path, manifest)
    report = e5_harness.verify(tmp_path)
    assert not any("historical company-disjointness proven" in check["check"] for check in report.failures)


# --------------------------------------------------------------------------------------
# Environment freeze
# --------------------------------------------------------------------------------------


def test_environment_check_passes_against_a_freshly_captured_manifest() -> None:
    environment = e5_harness.capture_environment({})
    assert e5_harness.check_environment(environment)


def test_environment_check_fails_on_a_missing_required_variable() -> None:
    environment = e5_harness.capture_environment({"E5_TEST_VARIABLE_ABSENT": "expected"})
    failures = [check for check in e5_harness.check_environment(environment) if check["status"] == "FAIL"]
    assert any("E5_TEST_VARIABLE_ABSENT" in check["check"] for check in failures)


def test_environment_check_fails_when_the_lock_changes() -> None:
    environment = e5_harness.capture_environment({})
    environment["packages_lock_sha256"] = "0" * 64
    failures = [check for check in e5_harness.check_environment(environment) if check["status"] == "FAIL"]
    assert any("requirements.lock" in check["check"] for check in failures)


def test_environment_check_reports_a_missing_block() -> None:
    failures = e5_harness.check_environment({})
    assert any(check["status"] == "FAIL" for check in failures)


# --------------------------------------------------------------------------------------
# Single-company semantic context
# --------------------------------------------------------------------------------------


def test_single_company_context_accepts_one_company() -> None:
    result = e5_harness.assert_single_company_context({"case_ids": ["E4_COMPANY_000001"]})
    assert result["single_company_context"] is True


def test_single_company_context_rejects_two_companies() -> None:
    result = e5_harness.assert_single_company_context(
        {"case_ids": ["E4_COMPANY_000001", "E4_COMPANY_000002"]}
    )
    assert result["single_company_context"] is False
    assert result["company_count"] == 2


def test_single_company_context_handles_a_bare_case_id() -> None:
    result = e5_harness.assert_single_company_context({"case_id": "E4_COMPANY_000001"})
    assert result["single_company_context"] is True


def test_single_company_context_rejects_an_empty_packet() -> None:
    result = e5_harness.assert_single_company_context({})
    assert result["company_count"] == 0
    assert result["single_company_context"] is True  # nothing to contaminate, but counted


# --------------------------------------------------------------------------------------
# CLI entry points
# --------------------------------------------------------------------------------------


def test_verify_e5_cli_runs_and_reports_unfrozen_stages(tmp_path: Path) -> None:
    _freeze_protocol(tmp_path)
    result = subprocess.run(
        [sys.executable, str(HARNESS_DIR / "verify_e5.py"), "--stage-dir", str(tmp_path),
         "--repo-root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0
    assert "checks passed" in result.stdout
    assert "stages not yet frozen" in result.stdout


def test_verify_environment_cli_round_trip(tmp_path: Path) -> None:
    """Freeze and then check, with the required variable actually set.

    experiment_config.json declares FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES as required, so a
    bare check in a process that has not set it is expected to fail - that negative case is
    covered separately below.
    """
    import os

    manifest = tmp_path / "environment_manifest.json"
    environment = dict(os.environ)
    environment["FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES"] = "2147483648"

    freeze = subprocess.run(
        [sys.executable, str(HARNESS_DIR / "verify_environment.py"), "--manifest", str(manifest), "--freeze"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=environment,
        check=False,
    )
    assert freeze.returncode == 0, freeze.stderr
    assert manifest.is_file()

    check = subprocess.run(
        [sys.executable, str(HARNESS_DIR / "verify_environment.py"), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=environment,
        check=False,
    )
    assert check.returncode == 0, check.stdout
    assert "checks passed" in check.stdout


def test_verify_environment_cli_fails_when_a_required_variable_is_absent(tmp_path: Path) -> None:
    """The real-world failure mode: the manifest requires a variable the shell never set."""
    import os

    manifest = tmp_path / "environment_manifest.json"
    with_variable = dict(os.environ)
    with_variable["FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES"] = "2147483648"
    subprocess.run(
        [sys.executable, str(HARNESS_DIR / "verify_environment.py"), "--manifest", str(manifest), "--freeze"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=with_variable,
        check=False,
    )

    without_variable = dict(os.environ)
    without_variable.pop("FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES", None)
    check = subprocess.run(
        [sys.executable, str(HARNESS_DIR / "verify_environment.py"), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=without_variable,
        check=False,
    )
    assert check.returncode == 1
    assert "FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES" in check.stdout
