"""Tests for the coverage gaps named in `docs/audit_report_2026-09-13.md` (J3).

The report's central mechanical finding was that "the confirmed defects sit on the
lines the suite never executes". These tests close the specific gaps it listed -
`report.export_pdf`, `human_study.validate_study_rows`, the governance gates, the
calibration branches, the negative-severity fallbacks and the temporal labels -
so a future regression in those paths cannot hide behind the coverage number.
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

# Imported before `finrisk.tools`: `finrisk.tools` re-exports the tool registry,
# which imports the orchestrator, which imports `finrisk.tools` again. Reaching
# `finrisk.tools.ingestion` first therefore deadlocks on a half-built package.
from finrisk.agent import FinancialRiskAgent
from finrisk.benchmark import write_jsonl
from finrisk.domain import Evidence, NarrativeClaim
from finrisk.enterprise.calibration import (
    CalibrationStatus,
    brier_score,
    expected_calibration_error,
    reliability_diagram,
    risk_coverage_curve,
    selective_decision,
)
from finrisk.enterprise.domain import ModelRecord, RiskCase, RiskCaseStatus, RiskDomain
from finrisk.enterprise.evidence_graph import EvidenceNode, TemporalEvidenceGraph
from finrisk.enterprise.governance import (
    champion_challenger,
    compare_system_versions,
    drift_report,
    experiment_run,
    transition_model,
)
from finrisk.enterprise.temporal import (
    EntityRiskState,
    RiskSnapshot,
    classify_trajectory,
    compare_risk_snapshots,
)
from finrisk.enterprise.workflow import (
    add_mitigation_action,
    record_override,
    record_resolution_evidence,
    transition_case,
)
from finrisk.human_study import summarize_study, validate_study_rows
from finrisk.metrics import _safe_div, calculate_metrics
from finrisk.models import _logistic
from finrisk.pipeline import FinRiskPipeline
from finrisk.report import export_pdf, render_text_report
from finrisk.tools.ingestion import ingest_pdf, ingest_xbrl

ROOT = Path(__file__).resolve().parents[1]

VALID_ROW = {
    "participant_id": "p1",
    "condition": "human_only",
    "case_id": "c1",
    "analysis_seconds": 100,
    "missed_risks": 1,
    "unsupported_claims": 0,
    "citation_errors": 0,
    "overrides": 0,
    "decision": "FLAG",
    "gold_decision": "FLAG",
}


# --------------------------------------------------------------------------- #
# report.export_pdf - the lowest-covered function in the repository, and the
# producer of a committed artifact
# --------------------------------------------------------------------------- #
def test_export_pdf_writes_a_readable_pdf(tmp_path):
    assessment = FinRiskPipeline(ROOT).assess(
        "PDF Co",
        2025,
        {
            "revenue": 1000.0,
            "net_income": -50.0,
            "total_assets": 2000.0,
            "current_assets": 400.0,
            "current_liabilities": 500.0,
            "total_liabilities": 1500.0,
            "shareholder_equity": 500.0,
            "operating_income": -20.0,
            "operating_cash_flow": -10.0,
            "cash": 50.0,
        },
        None,
    )
    target = tmp_path / "nested" / "report.pdf"
    written = export_pdf(assessment, target)
    assert written == target
    payload = target.read_bytes()
    assert payload.startswith(b"%PDF-")
    assert payload.rstrip().endswith(b"%%EOF")
    # The text renderer is the source of the PDF, so both must exist.
    assert "FINRISK ASSESSMENT" in render_text_report(assessment)


def test_export_pdf_paginates_a_long_report(tmp_path):
    """A long report must spill onto a second page rather than run off the edge."""
    assessment = FinRiskPipeline(ROOT).assess(
        "Long Co",
        2025,
        {
            "revenue": 1000.0,
            "net_income": -50.0,
            "total_assets": 2000.0,
            "current_assets": 400.0,
            "current_liabilities": 500.0,
            "total_liabilities": 1500.0,
            "shareholder_equity": 500.0,
            "operating_income": -20.0,
            "operating_cash_flow": -10.0,
            "cash": 50.0,
            "inventory": 300.0,
            "accounts_receivable": 200.0,
            "accounts_payable": 150.0,
            "depreciation": 30.0,
            "sga": 40.0,
            "ppe": 900.0,
            "shares_outstanding": 100.0,
            "market_value_equity": 700.0,
        },
        {
            "revenue": 1100.0,
            "net_income": 10.0,
            "total_assets": 1900.0,
            "operating_cash_flow": 20.0,
            "capital_expenditure": 25.0,
        },
    )
    target = export_pdf(assessment, tmp_path / "long.pdf")
    document = fitz.open(target)
    try:
        assert document.page_count >= 1
        text = "".join(page.get_text() for page in document)
        assert "FINRISK ASSESSMENT" in text
        assert "RULE COVERAGE" in text
    finally:
        document.close()


# --------------------------------------------------------------------------- #
# human_study.validate_study_rows - the illegal-row branches were never executed
# --------------------------------------------------------------------------- #
def test_study_rows_are_validated_before_summarising():
    assert validate_study_rows([VALID_ROW])["valid"] is True
    assert validate_study_rows([VALID_ROW])["participant_count"] == 1

    missing = validate_study_rows([{"participant_id": "p1"}])
    assert missing["valid"] is False
    assert any("missing" in error for error in missing["errors"])

    bad_condition = validate_study_rows([dict(VALID_ROW, condition="unsupervised")])
    assert bad_condition["valid"] is False
    assert any("invalid condition" in error for error in bad_condition["errors"])

    with pytest.raises(ValueError, match="invalid human-study rows"):
        summarize_study([{"participant_id": "p1"}])


def test_study_summary_reports_both_conditions():
    rows = [
        VALID_ROW,
        dict(VALID_ROW, participant_id="p2", condition="finrisk_assisted", decision="REVIEW"),
    ]
    summary = summarize_study(rows, synthetic=True)
    assert summary["status"] == "SYNTHETIC_DEMO"
    assert summary["participant_count"] == 2
    assert summary["groups"]["human_only"]["n"] == 1
    assert summary["groups"]["finrisk_assisted"]["n"] == 1
    # Decision agreement is measured against the gold decision, not itself.
    assert summary["groups"]["finrisk_assisted"]["decision_agreement"] == 0.0


def test_the_committed_synthetic_study_rows_are_valid():
    import csv

    with (ROOT / "examples/human_study_synthetic.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert validate_study_rows(rows)["valid"] is True


# --------------------------------------------------------------------------- #
# enterprise/governance.py - the gate lines
# --------------------------------------------------------------------------- #
def _gate_metrics(**overrides) -> dict[str, float]:
    base = {
        "f1": 0.7,
        "balanced_accuracy": 0.7,
        "false_negative_rate": 0.1,
        "calibration_error": 0.05,
        "coverage": 0.8,
        "abstention_rate": 0.2,
        "evidence_verification_error": 0.0,
        "latency_ms": 100.0,
        "cost_usd": 0.01,
    }
    base.update(overrides)
    return base


def test_each_promotion_blocker_is_reachable_and_reported():
    champion = _gate_metrics()
    assert compare_system_versions(champion, _gate_metrics(f1=0.9))["recommendation"] == "PROMOTE"
    assert (
        compare_system_versions(champion, _gate_metrics(false_negative_rate=0.5))["blockers"]
        == ["FALSE_NEGATIVE_REGRESSION"]
    )
    assert (
        compare_system_versions(champion, _gate_metrics(evidence_verification_error=0.5))["blockers"]
        == ["EVIDENCE_ERROR_LIMIT"]
    )
    assert (
        compare_system_versions(champion, _gate_metrics(calibration_error=0.9))["blockers"]
        == ["CALIBRATION_LIMIT"]
    )
    assert (
        compare_system_versions(champion, _gate_metrics(coverage=0.1))["blockers"]
        == ["COVERAGE_LIMIT"]
    )
    conditional = compare_system_versions(champion, _gate_metrics(f1=0.6))
    assert conditional["recommendation"] == "PROMOTE_WITH_CONDITIONS"
    assert conditional["automatic_promotion"] is False


def test_experiment_run_status_vocabulary_is_closed():
    run = experiment_run(
        dataset_version="d",
        git_commit="c",
        component="fusion",
        component_version="v1",
        prompt_hash=None,
        temperature=None,
        seed=None,
        rule_version="r",
        fusion_version="f",
        policy_version="p",
        latency_ms=1.0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        status="COMPLETED",
    )
    assert run.timestamp
    with pytest.raises(ValueError, match="invalid experiment status"):
        experiment_run(status="VALIDATED")


def test_model_validation_transitions_require_a_validation_record():
    record = ModelRecord("m", "org", "fusion", "v1", "owner", "intended", "limitations")
    promoted = transition_model(record, "validated", "validation_1")
    assert promoted.validation_status == "validated"
    assert promoted.deployment_state == "validated"
    with pytest.raises(ValueError, match="validation record is required"):
        transition_model(record, "validated")
    with pytest.raises(ValueError, match="invalid model transition"):
        transition_model(record, "approved")


def test_champion_challenger_and_drift_report_branches():
    result = champion_challenger([0.5, 0.5], [0.5, 0.5], [1, 1])
    assert result["recommendation"] == "KEEP_CHAMPION"
    assert result["automatic_promotion"] is False
    with pytest.raises(ValueError, match="aligned non-empty"):
        champion_challenger([0.5], [0.5, 0.5], [1])

    empty = drift_report([], [], 0.5, 0.9)
    assert empty["status"] == "INSUFFICIENT_DATA"
    assert empty["mean_shift"] is None
    assert drift_report([1.0, 2.0], [1.0, 2.0], 0.5, 0.5)["status"] == "STABLE"
    assert drift_report([1.0, 2.0], [5.0, 6.0], 0.5, 0.5)["status"] == "REVIEW"


# --------------------------------------------------------------------------- #
# enterprise/calibration.py
# --------------------------------------------------------------------------- #
def test_calibration_inputs_are_validated():
    with pytest.raises(ValueError, match="bins must be positive"):
        reliability_diagram([1, 0], [0.6, 0.4], bins=0)
    with pytest.raises(ValueError, match="aligned non-empty"):
        brier_score([1], [0.5, 0.5])
    with pytest.raises(ValueError, match="binary"):
        brier_score([2], [0.5])
    with pytest.raises(ValueError, match="within"):
        expected_calibration_error([1], [1.5])
    with pytest.raises(ValueError, match="aligned non-empty"):
        risk_coverage_curve([1], [0.5], [0.5, 0.6])


def test_calibration_metrics_are_computed():
    labels = [1, 1, 0, 0]
    probabilities = [0.9, 0.7, 0.2, 0.1]
    assert brier_score(labels, probabilities) == pytest.approx(0.0375, abs=1e-6)
    diagram = reliability_diagram(labels, probabilities, bins=2)
    assert sum(row["count"] for row in diagram) == 4
    # bin 0: mean p 0.15 vs observed 0 -> 0.15 * 0.5; bin 1: mean p 0.8 vs 1 -> 0.2 * 0.5
    assert expected_calibration_error(labels, probabilities, bins=2) == pytest.approx(
        0.175, abs=1e-6
    )
    curve = risk_coverage_curve(labels, probabilities, [0.9, 0.9, 0.5, 0.5])
    assert [row["reliability_threshold"] for row in curve] == [0.5, 0.9]
    assert curve[0]["coverage"] == 1.0
    assert curve[-1]["coverage"] == pytest.approx(0.5)
    assert curve[-1]["selective_error"] == 0.0


def test_selective_decision_failure_branches():
    policy = {"minimum_coverage": 0.5, "minimum_reliability": 0.6, "maximum_disagreement": 0.45}
    uncalibrated = selective_decision("PASS", 0.9, 0.9, 0.0, policy)
    assert uncalibrated["decision"] == "ABSTAIN"
    assert "UNVALIDATED_RELIABILITY" in uncalibrated["failure_reasons"]

    missing_reliability = selective_decision(
        "PASS", 0.9, None, 0.0, policy, CalibrationStatus.CALIBRATED_INTERNAL
    )
    assert missing_reliability["decision"] == "ABSTAIN"
    assert "MISSING_CALIBRATED_RELIABILITY" in missing_reliability["failure_reasons"]

    low_reliability = selective_decision(
        "PASS", 0.9, 0.2, 0.0, policy, CalibrationStatus.CALIBRATED_INTERNAL
    )
    assert low_reliability["decision"] == "REVIEW"
    assert "LOW_RELIABILITY" in low_reliability["failure_reasons"]

    disagreement = selective_decision(
        "PASS", 0.9, 0.9, 0.9, policy, CalibrationStatus.VALIDATED_EXTERNAL
    )
    assert "HIGH_MODEL_DISAGREEMENT" in disagreement["failure_reasons"]

    clean = selective_decision(
        "PASS", 0.9, 0.9, 0.0, policy, CalibrationStatus.VALIDATED_EXTERNAL
    )
    assert clean["decision"] == "PASS"
    assert clean["automation_allowed"] is True
    with pytest.raises(ValueError, match="unknown selective policy"):
        selective_decision("PASS", 0.9, 0.9, 0.0, {"min_coverage": 0.5})
    with pytest.raises(ValueError, match="within"):
        selective_decision(
            "PASS",
            0.9,
            float("nan"),
            0.0,
            policy,
            CalibrationStatus.VALIDATED_EXTERNAL,
        )
    with pytest.raises(ValueError, match="reliabilities"):
        risk_coverage_curve([0], [0.5], [float("nan")])


# --------------------------------------------------------------------------- #
# models._logistic - the upper clamp
# --------------------------------------------------------------------------- #
def test_logistic_saturates_instead_of_overflowing():
    assert _logistic(0.0) == 0.5
    assert _logistic(1000.0) == 1.0
    assert _logistic(-1000.0) == 0.0
    # The lower clamp is the one the audit found tested; both matter, because a
    # mis-scaled liability produced `math.exp(745)`.
    assert 0.0 < _logistic(20.0) < 1.0


# --------------------------------------------------------------------------- #
# metrics - the arithmetic guards
# --------------------------------------------------------------------------- #
def test_safe_div_treats_overflow_as_not_computable():
    assert _safe_div(1.0, 2.0) == 0.5
    assert _safe_div(None, 2.0) is None
    assert _safe_div(1.0, 0) is None
    assert _safe_div(1.0, 0.0) is None
    assert _safe_div(10**400, 1) is None


def test_negative_ebitda_leverage_is_withheld_with_a_reason():
    metrics = calculate_metrics({"ebitda": -5.0, "total_debt": 100.0}, 2025)
    assert metrics["debt_to_ebitda"].value is None
    assert "non-positive" in (metrics["debt_to_ebitda"].missing_reason or "")


def test_growth_across_a_sign_change_is_withheld():
    metrics = calculate_metrics(
        {"net_income": -50.0, "revenue": 100.0}, 2025, {"net_income": -100.0, "revenue": 90.0}
    )
    # Two losses closing is not "+50% growth".
    assert metrics["net_income_growth"].value is None
    assert metrics["revenue_growth"].value is not None


# --------------------------------------------------------------------------- #
# benchmark.write_jsonl
# --------------------------------------------------------------------------- #
def test_write_jsonl_round_trips_rows(tmp_path):
    target = tmp_path / "rows.jsonl"
    rows = [{"b": 2, "a": 1}, {"b": 3, "a": 2}]
    write_jsonl(rows, target)
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line) for line in lines] == rows
    # Keys are sorted so two runs produce byte-identical output.
    assert lines[0].startswith('{"a": 1')


# --------------------------------------------------------------------------- #
# enterprise/temporal.py - the trajectory labels and the entity guard
# --------------------------------------------------------------------------- #
def test_every_trajectory_label_is_reachable():
    assert classify_trajectory([]) == "insufficient_history"
    assert classify_trajectory([None, None]) == "insufficient_history"
    # `persistent_weakness` is checked first, so a sharp move between two already
    # severe readings is still reported as persistence, not deterioration.
    assert classify_trajectory([70, 90]) == "persistent_weakness"
    assert classify_trajectory([61, 62]) == "persistent_weakness"
    assert classify_trajectory([40, 70]) == "sharply_deteriorating"
    assert classify_trajectory([40, 50]) == "deteriorating"
    assert classify_trajectory([80, 50]) == "recovery"
    assert classify_trajectory([40, 30]) == "improving"
    assert classify_trajectory([40, 41]) == "stable"


def _snapshot(entity_id: str, period: str, score: float) -> RiskSnapshot:
    return RiskSnapshot(entity_id, period, "f", score, {}, {}, {}, "PASS", 1)


def test_entity_risk_state_enforces_its_own_boundaries():
    state = EntityRiskState("entity_a")
    assert state.current is None
    assert state.update(_snapshot("entity_a", "2024", 40.0)) is None
    delta = state.update(_snapshot("entity_a", "2025", 70.0))
    assert delta is not None
    assert state.current is not None and state.current.period == "2025"

    with pytest.raises(ValueError, match="different entity"):
        state.update(_snapshot("entity_b", "2026", 50.0))
    with pytest.raises(ValueError, match="already exists"):
        state.update(_snapshot("entity_a", "2025", 50.0))
    with pytest.raises(ValueError, match="reporting-period order"):
        state.update(_snapshot("entity_a", "2023", 50.0))


def test_risk_snapshots_from_different_entities_cannot_be_compared():
    with pytest.raises(ValueError, match="different entities"):
        compare_risk_snapshots(_snapshot("a", "2024", 10.0), _snapshot("b", "2025", 20.0))


# --------------------------------------------------------------------------- #
# enterprise/workflow.py - the remaining guards
# --------------------------------------------------------------------------- #
def _case(status: RiskCaseStatus) -> RiskCase:
    case = RiskCase("case_1", "org", "entity", RiskDomain.LIQUIDITY, "high", "stable", 0.8, 0.7)
    case.status = status
    return case


def test_workflow_guards_each_required_argument():
    with pytest.raises(ValueError, match="invalid transition"):
        transition_case(_case(RiskCaseStatus.CLOSED), RiskCaseStatus.OPEN)
    with pytest.raises(ValueError, match="override reason is required"):
        record_override(_case(RiskCaseStatus.OPEN), "u", "FLAG", "PASS", "  ")
    with pytest.raises(ValueError, match="description, owner and due date"):
        add_mitigation_action(_case(RiskCaseStatus.OPEN), "u", "", "owner", "2026-01-01")
    with pytest.raises(ValueError, match="resolution evidence is required"):
        record_resolution_evidence(_case(RiskCaseStatus.OPEN), "  ")

    case = _case(RiskCaseStatus.OPEN)
    action = add_mitigation_action(case, "u", "Hedge", "owner", "2026-01-01")
    assert action["status"] == "open"
    assert case.owner_id == "owner"
    record_resolution_evidence(case, "ev_1")
    record_resolution_evidence(case, "ev_1")
    assert case.resolution_evidence == ["ev_1"]


# --------------------------------------------------------------------------- #
# enterprise/evidence_graph.py - the remaining guards
# --------------------------------------------------------------------------- #
def test_evidence_graph_rejects_duplicate_ids_and_cycles():
    graph = TemporalEvidenceGraph()
    graph.add_node(EvidenceNode("a", "document", "2024", {"v": 1}))
    graph.add_node(EvidenceNode("a", "document", "2024", {"v": 1}))
    with pytest.raises(ValueError, match="collision"):
        graph.add_node(EvidenceNode("a", "document", "2024", {"v": 2}))
    with pytest.raises(KeyError):
        graph.paths_to("missing")
    with pytest.raises(KeyError, match="both evidence nodes"):
        graph.link("a", "missing", "SUPPORTS", "reason")
    with pytest.raises(ValueError, match="requires a reason"):
        graph.add_node(EvidenceNode("b", "document", "2024", {}))
        graph.link("a", "b", "SUPPORTS", "  ")
    graph.link("a", "b", "SUPPORTS", "reason")
    graph.link("b", "a", "SUPPORTS", "cycle")
    # The cycle guard terminates and yields no path rather than recursing forever
    # or inventing one.
    assert graph.paths_to("a") == []
    assert graph.paths_to("b") == []


def test_evidence_graph_serialises_its_nodes_and_edges():
    graph = TemporalEvidenceGraph()
    graph.add_node(EvidenceNode("a", "document", "2024", {}))
    graph.add_node(EvidenceNode("b", "fact", "2024", {}))
    graph.link("a", "b", "SUPPORTS", "reason")
    payload = graph.to_dict()
    assert {node["id"] for node in payload["nodes"]} == {"a", "b"}
    assert payload["edges"][0]["relation"] == "SUPPORTS"


# --------------------------------------------------------------------------- #
# tools/ingestion.py - the XBRL path and the empty-extraction guard
# --------------------------------------------------------------------------- #
def test_ingest_xbrl_returns_values_and_a_year_index():
    payload = {
        "cik": "0000320193",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 100,
                                "accn": "a",
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                            }
                        ]
                    }
                }
            }
        },
    }
    result = ingest_xbrl(payload, [2023])
    assert result["values"]
    assert 2023 in result["by_year"]


def test_ingest_pdf_refuses_a_filing_with_no_financial_line_items(tmp_path):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "This filing contains no tabular financial data.")
    path = tmp_path / "empty.pdf"
    document.save(path)
    document.close()
    with pytest.raises(ValueError, match="No reliable financial line items"):
        ingest_pdf(path, "Empty 10-K", 2025)


# --------------------------------------------------------------------------- #
# A narrative claim that is refused by the grounding gate is still recorded
# --------------------------------------------------------------------------- #
def test_an_ungrounded_claim_never_reaches_the_evidence_trail():
    class Provider:
        def extract(self, pages, document, year):
            return [
                NarrativeClaim(
                    "A covenant was breached",
                    "solvency",
                    Evidence(document, 1, "A covenant was breached", year, 0.99),
                    "negative",
                )
            ]

    state = FinancialRiskAgent(ROOT, Provider()).run(
        "Example", 2025, {"cash": 10.0}, pages={1: "No covenant disclosure exists."}
    )
    assert state.assessment is not None
    assert state.assessment["contradictions"] == []
