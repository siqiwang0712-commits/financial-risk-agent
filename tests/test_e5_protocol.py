"""Tests for the E5 prospective protocol package.

These tests check that the protocol package is internally consistent and that its
mechanical parts (the freeze-chain verifier and the power analysis) behave as documented.
They deliberately do not check for study results, because no E5 result exists.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import power_analysis
import pytest
import verify_freeze_chain
from e4s_stats import delong_paired
from method_calibration import generate_paired

REPO_ROOT = Path(__file__).resolve().parents[1]
E5_DIR = REPO_ROOT / "research" / "e5"
PROTOCOL_DIR = E5_DIR / "protocol"


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
    selected, delta, correlation = 1200, 0.03, 0.90
    n_evaluable = round(selected * 0.60 * 0.99)
    analytic = power_analysis.analytic_power(n_evaluable, delta, correlation)
    assert analytic is not None
    n_events = round(n_evaluable * power_analysis.PLANNING["e4_event_prevalence"])
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


# ----------------------------------------------------------------------------------
# E5-Narrative: a separate study, with its own frozen requirements
# ----------------------------------------------------------------------------------

NARRATIVE_DIR = E5_DIR / "narrative"


def test_narrative_study_is_present_and_separate() -> None:
    assert (NARRATIVE_DIR / "NARRATIVE_PROTOCOL.md").is_file()
    assert (NARRATIVE_DIR / "experiment_config.json").is_file()
    config = json.loads((NARRATIVE_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    assert config["merge_with_structured_e5"] is False
    assert config["separate_from"].startswith("structured E5")
    assert config["status"] == "PROSPECTIVE_NOT_FROZEN"


def test_narrative_config_forbids_cross_study_claim_transfer() -> None:
    """Structured E5 and E5-Narrative measure different capabilities."""
    config = json.loads((NARRATIVE_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    transfer = config["cross_study_claim_transfer"].lower()
    assert "forbidden" in transfer


def test_narrative_study_uses_the_same_inference_rules() -> None:
    """The E4-S findings must carry over: cluster resampling and no permutation equality test."""
    config = json.loads((NARRATIVE_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    inference = config["inference"]
    assert inference["resampling_unit"] == "company"
    assert inference["interval"] == "company_cluster_bca_bootstrap"
    assert inference["bootstrap_replicates"] == 20000
    assert inference["multiplicity"] == "holm_over_N1_N2_N3_N4_N5"
    assert "forbidden" in inference["label_permutation_as_equality_test"]


def test_narrative_study_covers_all_five_research_questions() -> None:
    config = json.loads((NARRATIVE_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    metrics = config["metrics"]
    for question in ("N1_claim_extraction", "N2_evidence_grounding", "N3_contradiction",
                     "N4_temporal_change", "N5_abstention"):
        assert question in metrics, f"missing metric family {question}"
    assert metrics["abstention_reported_in_both_directions"] is True


def test_narrative_study_validates_its_instrument_before_running_models() -> None:
    """A metric that cannot detect a planted defect cannot be trusted on model output."""
    config = json.loads((NARRATIVE_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    validation = config["instrument_validation"]
    assert validation["must_be_committed_before_model_run"] is True
    assert validation["defect_types"], "at least one planted defect type is required"
    assert config["governance"]["instrument_validation_precedes_model_run"] is True
    stages = config["governance"]["stage_commits"]
    assert stages.index("instrument-validation") < stages.index("model-run")


def test_narrative_ground_truth_is_double_annotated_and_blinded() -> None:
    config = json.loads((NARRATIVE_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    truth = config["ground_truth"]
    assert truth["annotators"] == {"a": True, "b": True, "adjudicator_c": True}
    assert truth["field_level_kappa_required"] is True
    assert "model output" in truth["blinding"]
    assert truth["guidelines"].startswith("frozen")


def test_narrative_annotation_schema_is_complete() -> None:
    config = json.loads((NARRATIVE_DIR / "experiment_config.json").read_text(encoding="utf-8"))
    schema = config["annotation_schema"]
    for field in ("claim_span", "claim_type", "direction", "evidence_spans",
                  "evidence_sufficiency", "contradicts_structured_financials", "temporal_change"):
        assert field in schema, f"annotation schema is missing {field}"
    assert schema["evidence_sufficiency"] == ["sufficient", "partial", "absent"]


# ----------------------------------------------------------------------------------
# Agent representations: the documented field lists must match the frozen builder,
# and the confound claim must be measurable rather than asserted
# ----------------------------------------------------------------------------------

REPRESENTATIONS_DOC = PROTOCOL_DIR / "AGENT_REPRESENTATIONS.md"
REPRESENTATIONS_JSON = PROTOCOL_DIR / "representations.json"
REPLICATION_FEATURES = REPO_ROOT / "research" / "e4_statistical_audit" / "replication" / "features.json.gz"
REPLICATION_PREDICTIONS = (
    REPO_ROOT / "research" / "e4_statistical_audit" / "replication" / "numeric_predictions.json"
)


def _representations() -> dict:
    return json.loads(REPRESENTATIONS_JSON.read_text(encoding="utf-8"))


def _replication_observations() -> list[dict]:
    import gzip

    return json.loads(gzip.decompress(REPLICATION_FEATURES.read_bytes()))


def test_representation_document_and_schema_are_present() -> None:
    assert REPRESENTATIONS_DOC.is_file()
    assert REPRESENTATIONS_JSON.is_file()
    assert _representations()["status"] == "PROSPECTIVE_NOT_FROZEN"


def test_documented_representation_fields_match_the_frozen_packet_builder() -> None:
    """The documentation must describe what ``packet()`` actually emits, not what it should.

    This is checked against the frozen builder on real observations, so a future edit to
    either the code or the document fails here.
    """
    packet = pytest.importorskip("finrisk.e4_agent").packet
    documented = _representations()["representations"]
    observation = _replication_observations()[0]
    for representation in ("A0", "A1", "A2"):
        emitted = set(packet(observation, representation))
        assert emitted == set(documented[representation]["fields"]), (
            f"{representation}: documented {sorted(documented[representation]['fields'])} "
            f"but packet() emits {sorted(emitted)}"
        )


def test_b0_and_b6_are_recoverable_from_the_a2_packet() -> None:
    """The confound claim in AGENT_REPRESENTATIONS.md section 2, measured.

    If the baselines can be recomputed from the Agent's own packet, then A2 vs B6 is a
    comparison of aggregation rather than of information access. Any drift here would
    invalidate that section, so the claim is pinned by a test.
    """
    agent = pytest.importorskip("finrisk.e4_agent")
    benchmark = pytest.importorskip("finrisk.numeric_benchmark")
    packet = agent.packet
    temporal_risk_score = benchmark.temporal_risk_score
    ratio_risk_score = benchmark.ratio_risk_score

    published = {
        (row["observation_id"], row["model_id"]): row["score"]
        for row in json.loads(REPLICATION_PREDICTIONS.read_text(encoding="utf-8"))
    }
    checked = 0
    worst = {"B0": 0.0, "B6": 0.0}
    for observation in _replication_observations():
        engineered = packet(observation, "A2")["engineered_features"]
        recomputed = {
            "B0": ratio_risk_score(engineered),
            "B6": temporal_risk_score(engineered),
        }
        for model_id, value in recomputed.items():
            expected = published.get((observation["observation_id"], model_id))
            if value is None or expected is None:
                continue
            checked += 1
            worst[model_id] = max(worst[model_id], abs(value - expected))

    assert checked > 0, "no comparable baseline scores found"
    # Published scores are rounded to 10 decimals by _record, so the residual is float noise.
    assert worst["B0"] < 1e-9, f"B0 is not recoverable from the A2 packet: {worst['B0']}"
    assert worst["B6"] < 1e-9, f"B6 is not recoverable from the A2 packet: {worst['B6']}"


def test_forbidden_key_list_covers_the_frozen_guard() -> None:
    frozen_guard = {"cik", "accession", "ticker", "company_name", "outcome", "label",
                    "B0", "B2", "B6", "score"}
    declared = set(_representations()["forbidden_packet_keys"])
    assert frozen_guard <= declared, f"the E5 list drops frozen guard keys: {frozen_guard - declared}"
    for extra in ("ratio_risk_score", "temporal_risk_score", "hybrid_score", "prediction", "threshold"):
        assert extra in declared


def test_a3_is_ineligible_until_the_extraction_exists() -> None:
    """A3 must not enter the confirmatory family without the multi-period extraction."""
    a3 = _representations()["representations"]["A3"]
    assert a3["eligible"] is False
    assert "temporal_evidence" in a3["fields"]
    assert "build_features" in a3["eligibility_blocker"]
    assert "temporal_evidence" in a3["fields"]
    assert a3["note"].startswith("adds horizon")


def test_exactly_one_representation_is_primary() -> None:
    rule = _representations()["primary_rule"]
    assert rule["exactly_one_of"] == ["A2", "A3"]
    assert rule["excluded_from_primary_family_if_ablation"] is True


def test_aggregation_equivalence_diagnostic_stays_out_of_the_primary_family() -> None:
    diagnostic = _representations()["aggregation_equivalence_diagnostic"]
    assert diagnostic["enters_holm_family"] is False
    assert diagnostic["role"] == "diagnostic_not_primary"
    assert "paired_delta_auroc_against_agent_regressed_on_B0_and_B6" in diagnostic["measures"]


def test_monotone_rederivation_ceiling_is_an_open_freeze_decision() -> None:
    check = _representations()["monotone_rederivation_check"]
    assert check["ceiling"] is None, "the ceiling must be declared in the protocol commit, not now"
    assert check["ceiling_frozen_in"] == "protocol commit"


def test_a3_temporal_evidence_schema_is_complete() -> None:
    schema = _representations()["temporal_evidence_schema"]
    for field in ("fiscal_years", "years_available", "series", "comparability", "trajectory_class"):
        assert field in schema, f"temporal_evidence schema is missing {field}"
    assert "same accession" in " ".join(schema["rules"])
