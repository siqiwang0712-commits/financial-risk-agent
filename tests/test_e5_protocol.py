"""Tests for the E5 prospective protocol package.

These tests check that the protocol package is internally consistent and that its
mechanical parts (the freeze-chain verifier and the power analysis) behave as documented.
They deliberately do not check for study results, because no E5 result exists.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
E5_DIR = REPO_ROOT / "research" / "e5"
PROTOCOL_DIR = E5_DIR / "protocol"
AUDIT_DIR = REPO_ROOT / "research" / "e4_statistical_audit"

sys.path.insert(0, str(AUDIT_DIR))
sys.path.insert(0, str(PROTOCOL_DIR))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


verify_freeze_chain = _load("verify_freeze_chain", PROTOCOL_DIR / "verify_freeze_chain.py")
power_analysis = _load("e5_power_analysis", PROTOCOL_DIR / "power_analysis.py")


# ----------------------------------------------------------------------------------
# Package presence and config consistency
# ----------------------------------------------------------------------------------

REQUIRED_DOCUMENTS = (
    "STUDY_PROTOCOL.md",
    "INFERENCE_POLICY.md",
    "AGENT_QUALIFICATION_PROTOCOL.md",
    "OUTCOME_ADJUDICATION_PROTOCOL.md",
    "GOVERNANCE_WORKFLOW.md",
    "experiment_config.json",
    "power_analysis.py",
    "verify_freeze_chain.py",
)


@pytest.mark.parametrize("name", REQUIRED_DOCUMENTS)
def test_protocol_package_is_present(name: str) -> None:
    assert (PROTOCOL_DIR / name).is_file(), f"missing protocol document: {name}"


def test_experiment_config_declares_the_prespecified_design() -> None:
    config = json.loads((PROTOCOL_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    hypotheses = config["hypotheses"]
    assert [item["id"] for item in hypotheses["primary_family"]] == ["H1", "H2", "H3"]
    assert hypotheses["primary_test"] == "paired_delong_1988"
    assert hypotheses["multiplicity"] == "holm_step_down_over_H1_H2_H3"
    assert "label_permutation_as_test_of_auc_equality" in hypotheses["forbidden_primary"]
    assert config["agent_inference_policy"]["one_company_per_semantic_request"] is True
    assert config["agent_inference_policy"]["cross_company_context_sharing"] is False
    assert config["agent_qualification"]["selection_may_use_e5_outcomes"] is False
    assert config["outcome"]["adjudication"]["coercion_of_insufficient_data"] is False
    assert config["isolation"]["unused_e4_companies_eligible"] is False


def test_experiment_config_records_the_environment_variable_e4_omitted() -> None:
    config = json.loads((PROTOCOL_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    variables = config["environment_variables"]
    assert "FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES" in variables
    assert int(variables["FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES"]) > 256 * 1024 * 1024


def test_experiment_config_leaves_design_choices_open_until_freeze() -> None:
    config = json.loads((PROTOCOL_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    assert config["status"] == "PROSPECTIVE_NOT_FROZEN"
    assert config["power"]["minimum_meaningful_delta_auroc"] is None
    assert config["agent_qualification"]["selected_model"] is None
    assert config["source_commit_at_freeze"] is None


def test_governance_declares_nine_stage_commits_in_order() -> None:
    config = json.loads((PROTOCOL_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    assert config["governance"]["stage_commits"] == list(verify_freeze_chain.REQUIRED_STAGES)
    assert config["governance"]["amend_pushed_commits"] is False


# ----------------------------------------------------------------------------------
# Freeze-chain verifier
# ----------------------------------------------------------------------------------


def test_freeze_chain_reports_not_frozen_when_empty(tmp_path: Path) -> None:
    result = verify_freeze_chain.verify({}, tmp_path)
    assert result["status"] == "NOT_FROZEN"
    assert result["stages_missing"] == list(verify_freeze_chain.REQUIRED_STAGES)


def test_freeze_chain_detects_a_broken_chain(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = verify_freeze_chain.sha256_file(artifact)

    def manifest(stage: str, sequence: int, previous: str | None, timestamp: str) -> dict:
        return {
            "stage": stage,
            "sequence": sequence,
            "previous_manifest_hash": previous,
            "created_at_utc": timestamp,
            "artifacts": [{"path": "artifact.json", "sha256": digest, "bytes": 2}],
        }

    first = manifest("protocol", 1, None, "2026-01-01T00:00:00Z")
    second = manifest("agent-qualification", 2, "not-the-right-hash", "2026-01-02T00:00:00Z")
    result = verify_freeze_chain.verify({"protocol": first, "agent-qualification": second}, tmp_path)
    assert result["status"] == "BROKEN"
    assert any(f["check"] == "chain" and f["status"] == "FAIL" for f in result["findings"])


def test_freeze_chain_detects_an_out_of_order_timestamp(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = verify_freeze_chain.sha256_file(artifact)
    first = {
        "stage": "protocol",
        "created_at_utc": "2026-02-01T00:00:00Z",
        "artifacts": [{"path": "artifact.json", "sha256": digest}],
    }
    second = {
        "stage": "agent-qualification",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "previous_manifest_hash": verify_freeze_chain.canonical_manifest_hash(first),
        "artifacts": [{"path": "artifact.json", "sha256": digest}],
    }
    result = verify_freeze_chain.verify({"protocol": first, "agent-qualification": second}, tmp_path)
    assert any(f["check"] == "timestamp_monotonic" and f["status"] == "FAIL" for f in result["findings"])


def test_freeze_chain_detects_a_modified_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    manifest = {
        "stage": "protocol",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "artifacts": [{"path": "artifact.json", "sha256": "0" * 64}],
    }
    result = verify_freeze_chain.verify({"protocol": manifest}, tmp_path)
    assert any(f["check"] == "artifact_hash" and f["status"] == "FAIL" for f in result["findings"])


def test_freeze_chain_rejects_an_outcome_artifact_before_unlock(tmp_path: Path) -> None:
    artifact = tmp_path / "outcomes.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = verify_freeze_chain.sha256_file(artifact)
    manifest = {
        "stage": "prediction-freeze",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "artifacts": [{"path": "outcomes.json", "sha256": digest}],
    }
    result = verify_freeze_chain.verify({"prediction-freeze": manifest}, tmp_path)
    assert any(f["check"] == "outcome_isolation" and f["status"] == "FAIL" for f in result["findings"])


# ----------------------------------------------------------------------------------
# Power analysis
# ----------------------------------------------------------------------------------


def test_analytic_power_increases_with_effect_and_sample() -> None:
    small = power_analysis.analytic_power(600, 0.02, 0.90)
    larger = power_analysis.analytic_power(2400, 0.02, 0.90)
    stronger = power_analysis.analytic_power(600, 0.06, 0.90)
    assert small is not None and larger is not None and stronger is not None
    assert small["power"] < larger["power"]
    assert small["power"] < stronger["power"]
    assert 0.0 <= small["power"] <= 1.0


def test_analytic_power_increases_with_score_correlation() -> None:
    low = power_analysis.analytic_power(1200, 0.03, 0.85)
    high = power_analysis.analytic_power(1200, 0.03, 0.95)
    assert low is not None and high is not None
    assert low["power"] < high["power"], "a more correlated pair must be easier to distinguish"


def test_analytic_power_agrees_with_monte_carlo() -> None:
    """The analytic approximation must track the simulation, or one of them is wrong."""
    from e4s_stats import delong_paired
    from method_calibration import generate_paired
    import random

    selected, delta, correlation = 1200, 0.03, 0.90
    analytic = power_analysis.analytic_power(
        int(round(selected * 0.60 * 0.99)), delta, correlation
    )
    assert analytic is not None
    n_evaluable = int(round(selected * 0.60 * 0.99))
    n_events = int(round(n_evaluable * power_analysis.PLANNING["e4_event_prevalence"]))
    n_non_events = n_evaluable - n_events
    rejections = 0
    replicates = 150
    for replicate in range(replicates):
        rows = generate_paired(
            n_events,
            n_non_events,
            power_analysis.PLANNING["e4_observed_b6_auroc"],
            power_analysis.PLANNING["e4_observed_b6_auroc"] + delta,
            correlation,
            random.Random(9000 + replicate),
        )
        result = delong_paired(rows)
        if result.get("p_value") is not None and result["p_value"] < 0.05:
            rejections += 1
    monte_carlo = rejections / replicates
    assert abs(monte_carlo - analytic["power"]) < 0.15, (
        f"Monte Carlo power {monte_carlo:.3f} is far from analytic {analytic['power']:.3f}"
    )


def test_power_analysis_artifact_is_internally_consistent() -> None:
    path = PROTOCOL_DIR / "power_analysis.json"
    if not path.is_file():
        pytest.skip("power_analysis.json has not been generated yet")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "DRAFT_NOT_FROZEN"
    assert "power_curve" in payload and payload["power_curve"]["points"]
    for point in payload["power_curve"]["points"]:
        assert point["power"] is None or 0.0 <= point["power"] <= 1.0
    assert payload["recommendation"]["target_power"] in (0.80, 0.90)
