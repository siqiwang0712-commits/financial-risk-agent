"""Regression tests for the defects recorded in `docs/audit_report_2026-09-13.md`.

Each test here fails against the code as audited. The report's section J3 showed
that nearly every confirmed defect sat on a line the suite never executed, so the
point of this file is to pair each fix with the test that would have caught it.
Sections are labelled with the report's own item ids.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from finrisk.api import app
from finrisk.benchmark import SMOKE_BASELINES, run_manifest
from finrisk.benchmark_protocol import (
    calibration_curve,
    fit_decision_stump,
    selective_metrics,
)
from finrisk.contradictions import (
    CHECKS,
    ClaimConsistencyReasonCode,
    evaluate_claim_consistency,
)
from finrisk.domain import Evidence, NarrativeClaim
from finrisk.enterprise.alerts import detect_alerts
from finrisk.enterprise.applicability import model_key, route_model
from finrisk.enterprise.decision import build_decision_trace, verified_paths_for_domain
from finrisk.enterprise.domain import (
    PRODUCED_RISK_DOMAINS,
    UNPRODUCED_RISK_DOMAINS,
    ModelRecord,
    PolicyVersion,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
)
from finrisk.enterprise.evidence_graph import (
    ADVERSE_RELATIONS,
    EvidenceNode,
    EvidenceRelation,
    TemporalEvidenceGraph,
)
from finrisk.enterprise.governance import GATE_METRICS, REPORTED_METRICS
from finrisk.enterprise.integrity import DecisionReasonCode
from finrisk.enterprise.jobs import Job, JobQueue
from finrisk.enterprise.observability import structured_event, traced_stage
from finrisk.enterprise.policy import (
    evaluate_kri,
    normalize_direction,
    validate_thresholds,
)
from finrisk.enterprise.repository import InMemoryEnterpriseRepository
from finrisk.enterprise.scenario import Scenario, apply_scenario
from finrisk.enterprise.storage import LocalDocumentStorage
from finrisk.enterprise.tension import (
    EVIDENCE_SUFFICIENCY_VALUES,
    classify_tension,
)
from finrisk.enterprise.workflow import reopen_case
from finrisk.evaluation import confusion_matrix, roc_auc, unsupported_claim_rate
from finrisk.extraction_reference import _line, _text
from finrisk.facts import MODEL_KEYS, MODEL_NAMES_BY_KEY
from finrisk.llm import StructuredLLMProvider
from finrisk.normalization import parse_number
from finrisk.numeric_benchmark import temporal_trajectories
from finrisk.parser import _scale_token
from finrisk.pipeline import FinRiskPipeline
from finrisk.research_eval import PILOT_BASELINES
from finrisk.rules import producible_fact_names, rule_coverage
from finrisk.sec_bulk import BULK_FIELDS, CONCEPT_ALIASES, build_reported_fcf_periods
from finrisk.severity import severity_key, severity_label
from finrisk.xbrl import CONCEPTS, parse_companyfacts

ROOT = Path(__file__).resolve().parents[1]

MINIMAL_CURRENT = {
    "revenue": 1000.0,
    "net_income": 50.0,
    "total_assets": 2000.0,
    "current_assets": 500.0,
    "current_liabilities": 300.0,
    "total_liabilities": 1200.0,
    "shareholder_equity": 800.0,
    "operating_income": 80.0,
    "operating_cash_flow": 90.0,
    "cash": 100.0,
}


def _authenticated_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(app)
    response = client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "audit-fix tenant", "actor_id": "audit-admin"},
    )
    assert response.status_code == 200
    return client, {"X-API-Key": response.json()["api_key"]}


# --------------------------------------------------------------------------- #
# A2 - the pilot's "Evidence coverage" column was the dataset mean on every row
# --------------------------------------------------------------------------- #
def test_public_pilot_publishes_per_company_coverage_not_the_dataset_mean():
    client = TestClient(app)
    body = client.get("/api/v1/public-pilot").json()
    per_company = {row["filing"]: row["coverage"] for row in body["rows"]}
    assert per_company == {"aapl-2024": 0.65, "msft-2024": 0.45, "intc-2024": 0.65}
    # The three rows must not be identical, and the dataset mean must still be
    # available under its own name.
    assert len(set(per_company.values())) == 2
    assert body["dataset_evidence_coverage"] == pytest.approx(0.5833, abs=1e-4)


# --------------------------------------------------------------------------- #
# D1 - a caller-supplied model metric raised an uncaught StopIteration
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "derived",
    [{"beneish_m_score": 0.5}, {"piotroski_f_score": 2.0}],
)
def test_caller_supplied_model_metric_is_a_value_error_not_a_stop_iteration(derived):
    pipeline = FinRiskPipeline(ROOT)
    with pytest.raises(ValueError, match="was not evaluated"):
        pipeline.assess("X", 2024, dict(MINIMAL_CURRENT, **derived), None)


def test_assess_endpoint_maps_a_caller_supplied_model_metric_to_422():
    client, headers = _authenticated_client()
    response = client.post(
        "/api/v1/assess",
        headers=headers,
        json={
            "company": "X",
            "fiscal_year": 2024,
            "current": dict(MINIMAL_CURRENT, beneish_m_score=0.5),
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# D2 - `llm_unavailable` fired when the provider worked and claims were rejected
# --------------------------------------------------------------------------- #
class UngroundedProvider:
    """Returns a claim whose quote does not appear on the page it cites."""

    def extract(self, pages, document, year):
        return [
            NarrativeClaim(
                "A covenant was breached",
                "solvency",
                Evidence(document, 1, "A covenant was breached", year, 0.99),
                "negative",
            )
        ]


def test_rejected_claims_are_not_reported_as_an_llm_outage():
    from finrisk.agent import FinancialRiskAgent

    data = json.loads(
        (ROOT / "examples/synthetic_company.json").read_text(encoding="utf-8")
    )
    state = FinancialRiskAgent(ROOT, UngroundedProvider()).run(
        "Example",
        2025,
        data["current"],
        data["previous"],
        {1: "No covenant disclosure exists."},
    )
    assert state.assessment is not None
    failures = state.assessment["failure_state"]
    # The provider answered; the claim was refused by the grounding gate. Those
    # are different findings and must not share a failure code.
    assert "llm_unavailable" not in failures["review_failures"]
    assert "llm_unavailable" not in failures["blocking_failures"]


# --------------------------------------------------------------------------- #
# I1 - XBRL parsed the prior-year comparative as the current year
# --------------------------------------------------------------------------- #
def _companyfacts(revenue_entries: list[dict], asset_entries: list[dict]) -> dict:
    return {
        "cik": "0000320193",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": revenue_entries}
                },
                "Assets": {"units": {"USD": asset_entries}},
            }
        },
    }


def _duration(start: str, end: str, value: float) -> dict:
    return {
        "start": start,
        "end": end,
        "val": value,
        "accn": "0000320193-23-000106",
        "filed": "2023-11-03",
        "form": "10-K",
        "fy": 2023,
        "fp": "FY",
    }


def _instant(end: str, value: float) -> dict:
    return {
        "end": end,
        "val": value,
        "accn": "0000320193-23-000106",
        "filed": "2023-11-03",
        "form": "10-K",
        "fy": 2023,
        "fp": "FY",
    }


def test_xbrl_selects_the_current_year_not_the_comparative():
    current = _duration("2023-01-01", "2023-12-31", 383_285_000_000)
    prior = _duration("2022-01-01", "2022-12-31", 394_328_000_000)
    for order in ([current, prior], [prior, current]):
        values = parse_companyfacts(_companyfacts(order, []), [2023])
        revenue = next(value for value in values if value.line_item == "revenue")
        assert revenue.value == 383_285_000_000
        assert (revenue.period_start, revenue.period_end) == ("2023-01-01", "2023-12-31")
        # A comparative is not a restatement.
        assert revenue.restated is False


def test_xbrl_selects_the_latest_instant_for_instant_items():
    current = _instant("2023-09-30", 352_583_000_000)
    prior = _instant("2022-09-24", 352_755_000_000)
    for order in ([current, prior], [prior, current]):
        values = parse_companyfacts(_companyfacts([], order), [2023])
        assets = next(value for value in values if value.line_item == "total_assets")
        assert assets.value == 352_583_000_000


def test_xbrl_still_detects_a_genuine_restatement():
    """The comparative-period fix must not disable restatement detection."""
    first = _duration("2023-01-01", "2023-12-31", 100.0)
    restated = dict(first, val=120.0, accn="0000320193-24-000010", filed="2024-02-01")
    values = parse_companyfacts(_companyfacts([first, restated], []), [2023])
    revenue = next(value for value in values if value.line_item == "revenue")
    assert revenue.value == 120.0
    assert revenue.restated is True


def test_xbrl_ignores_a_quarterly_duration():
    annual = _duration("2023-01-01", "2023-12-31", 100.0)
    quarter = _duration("2023-10-01", "2023-12-31", 40.0)
    values = parse_companyfacts(_companyfacts([quarter, annual], []), [2023])
    revenue = next(value for value in values if value.line_item == "revenue")
    assert revenue.value == 100.0


# --------------------------------------------------------------------------- #
# I2 - a structurally degraded response bypassed retry and the cost log
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "response",
    [
        {"choices": []},  # IndexError
        {"choices": [{"message": {"content": "{}"}}], "usage": None},  # AttributeError
    ],
)
def test_a_degraded_upstream_response_is_retried_and_logged(response):
    provider = StructuredLLMProvider(
        transport=lambda payload: response, max_retries=0, log_path=None
    )
    with pytest.raises(RuntimeError, match="after retries"):
        provider.extract({1: "text"}, "doc", 2024)
    # One attempt at `max_retries=0`, and that attempt is on the record. Both used
    # to escape the loop with no log entry and no cost row.
    assert len(provider.call_logs) == 1
    assert provider.call_logs[0].status.startswith("error:")


def test_provider_from_env_reads_the_project_prefixed_api_key(monkeypatch):
    from finrisk.llm import provider_from_env

    monkeypatch.setenv("FINRISK_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("FINRISK_LLM_API_KEY", "frk-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = provider_from_env()
    assert provider.api_key == "frk-test-key"


# --------------------------------------------------------------------------- #
# I3 / I4 - number and scale parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,234", 1234.0),
        ("1,234,567", 1234567.0),
        ("1,234.56", 1234.56),
        ("12,345.6", 12345.6),
        ("(1,234.56)", -1234.56),
        ("1234,56", 1234.56),
        ("1.234,56", 1234.56),
        ("0,5", 0.5),
    ],
)
def test_parse_number_handles_both_separator_conventions(raw, expected):
    assert parse_number(raw) == pytest.approx(expected)


def test_parse_number_still_returns_none_for_genuinely_unparseable_text():
    assert parse_number("n/a") is None
    assert parse_number("") is None


def test_scale_pattern_does_not_read_a_body_number_as_a_scale():
    # `$1,000,000` used to match the bare `000` alternative and scale the whole
    # page by 1000x -- the exact error the pattern exists to prevent.
    assert _scale_token("Revenues increased to $1,000,000 in 2023") is None
    assert _scale_token("$1,000") is None
    assert _scale_token("total 000123 units") is None
    assert _scale_token("(in thousands)") == "thousands"
    assert _scale_token("Amounts in 000's") == "000"
    assert _scale_token("(000s)") == "000s"
    assert _scale_token("US$ mm") == "mm"
    # `column` used to match the bare `mn` alternative, `immediate` the bare `mm`.
    assert _scale_token("This column is unaudited") is None
    assert _scale_token("immediate settlement") is None


@pytest.mark.parametrize(
    "header",
    [
        "(In Millions, Except Per Share Data)",
        "In millions,",
        "Dollars in Thousands, except share data",
        "thousands of dollars, unless otherwise noted",
        "($ in millions)",
        "(In billions, except per share amounts)",
    ],
)
def test_a_scale_token_followed_by_a_comma_is_still_a_scale_token(header):
    """The comma guard belongs to the `000` branch only.

    Excluding `,` from the word-token boundaries dropped the most common 10-K
    header phrasing, which left the page unscaled: a 1,000x/1,000,000x
    *under*statement, the mirror image of the error the pattern exists to fix.
    """
    assert _scale_token(header) is not None


def test_every_scale_token_the_pattern_can_return_has_a_multiplier():
    """The token is looked up in `_SCALE_TOKENS`; an unmapped token scales by 1."""
    from finrisk.parser import _SCALE_TOKENS

    for header in (
        "(in thousands)",
        "(in millions)",
        "(in billions)",
        "Amounts in 000's",
        "(000s)",
        "US$ mn",
        "US$ mm",
        "US$ bn",
    ):
        token = _scale_token(header)
        assert token is not None, header
        assert token in _SCALE_TOKENS, (header, token)
        assert _SCALE_TOKENS[token] in {"thousand", "thousands", "million", "millions", "billion", "billions"}


# --------------------------------------------------------------------------- #
# I5 - abstentions were ranked as the least risky samples
# --------------------------------------------------------------------------- #
def test_abstentions_are_reported_separately_and_never_ranked_as_safe():
    result = selective_metrics([1, 0, 1, 0], [0.9, 0.1, None, 0.05])
    assert result["abstained"] == [2]
    assert 2 not in result["risk_ranking"]
    assert set(result["risk_ranking"]) == {0, 1, 3}
    # Descending risk, decided samples only.
    assert result["risk_ranking"] == [0, 1, 3]


# --------------------------------------------------------------------------- #
# I7 / I8 - benchmark labels and baseline vocabularies
# --------------------------------------------------------------------------- #
def test_smoke_benchmark_publishes_quality_and_coverage_under_separate_names():
    rows = run_manifest(ROOT / "research/synthetic_manifest.json", ROOT)
    hybrid = next(row for row in rows if row["baseline"] == "full_hybrid")
    output = hybrid["output"]
    assert "coverage" not in output
    assert {"evidence_quality", "evidence_coverage"} <= set(output)


def test_the_two_baseline_vocabularies_are_named_for_their_datasets():
    assert set(SMOKE_BASELINES) != set(PILOT_BASELINES)
    assert "rules_only" in SMOKE_BASELINES
    assert "rule_engine" in PILOT_BASELINES
    # They must not be the same tuple under two names.
    assert SMOKE_BASELINES is not PILOT_BASELINES


def test_ablation_methods_are_declared_and_only_one_is_a_real_rerun():
    from finrisk.research_eval import ABLATION_METHODS, ABLATIONS

    assert set(ABLATION_METHODS) == set(ABLATIONS)
    # Three of the five variants are arithmetic recombinations of baselines that
    # were already computed. Publishing them as if a component had been removed
    # and the system re-measured was the audited defect; the distinction is now
    # data, so a consumer of `ablations.csv` can see it.
    assert {
        name for name, method in ABLATION_METHODS.items() if method == "rerun"
    } == {"without_trends"}
    assert sum(1 for method in ABLATION_METHODS.values() if method == "arithmetic_proxy") == 3


def test_the_pilot_summary_measures_claims_instead_of_publishing_constants():
    from finrisk.research_eval import ABLATION_METHODS, run_public_benchmark

    manifest = ROOT / "research/benchmark/public_company_observations.json"
    rows, summary, ablations = run_public_benchmark(manifest, ROOT)

    # `method` travels with every ablation row.
    assert {row["method"] for row in ablations} <= set(ABLATION_METHODS.values())

    # `evidence_precision` was a tautology (only admitted claims reach the graph,
    # so it was 1.0 by construction) and has been replaced by the measurement.
    assert all("evidence_precision" not in item for item in summary["summaries"])
    for item in summary["summaries"]:
        assert "verified_claim_coverage" in item
        # The two are complements of one another, not two independent constants.
        # `abs` covers the rounding of both terms to four decimals.
        assert item["unsupported_claim_rate"] + item["verified_claim_coverage"] == pytest.approx(
            1.0, abs=2e-4
        )

    # `without_narrative` is the `rule_engine` baseline verbatim - the tautology
    # the audit found, now declared rather than hidden.
    for example in {row["example_id"] for row in rows}:
        proxy = next(
            row
            for row in ablations
            if row["example_id"] == example and row["ablation"] == "without_narrative"
        )
        baseline = next(
            row
            for row in rows
            if row["example_id"] == example and row["baseline"] == "rule_engine"
        )
        assert proxy["risk_probability"] == baseline["risk_probability"]


# --------------------------------------------------------------------------- #
# I9 - free cash flow used `ocf - capex` with a signed capex tag
# --------------------------------------------------------------------------- #
def test_reported_free_cash_flow_uses_the_absolute_capex_convention():
    submissions = [
        {
            "adsh": "0000320193-23-000106",
            "cik": "0000320193",
            "form": "10-K",
            "period": "20230930",
            "fy": "2023",
            "filed": "20231103",
            "accepted": "2023-11-03T18:01:00.000Z",
        }
    ]

    def number(tag: str, value: str) -> dict:
        return {
            "adsh": "0000320193-23-000106",
            "tag": tag,
            "ddate": "20230930",
            "uom": "USD",
            "qtrs": "4",
            "coreg": "",
            "segments": "",
            "value": value,
        }

    records = build_reported_fcf_periods(
        submissions,
        [
            number("NetCashProvidedByUsedInOperatingActivities", "110000000000"),
            number("PaymentsToAcquirePropertyPlantAndEquipment", "-11000000000"),
        ],
    )
    assert records[0]["operating_cash_flow"] == 110_000_000_000
    assert records[0]["capital_expenditure"] == -11_000_000_000
    # 110 - 11, not 110 + 11: `ocf - capex` overstated FCF by 2x|capex|.
    assert records[0]["free_cash_flow"] == 99_000_000_000


# --------------------------------------------------------------------------- #
# I10 - short CSV rows produced None, which `int()` and sorting rejected
# --------------------------------------------------------------------------- #
def test_csv_helpers_tolerate_a_missing_trailing_field():
    assert _line({"line": "12"}) == 12
    assert _line({}) == 2**31 - 1
    assert _line({"line": None}) == 2**31 - 1
    assert _line({"line": "abc"}) == 2**31 - 1
    assert _text(None) == ""
    assert _text("10") == "10"


# --------------------------------------------------------------------------- #
# I11 - one incomplete period killed the whole trajectory report
# --------------------------------------------------------------------------- #
def test_a_trajectory_with_no_computable_delta_reports_none():
    rows = [
        {"ticker": "T", "fiscal_year": 2023, "metrics": {}},
        {"ticker": "T", "fiscal_year": 2024, "metrics": {}},
    ]
    result = temporal_trajectories(rows)
    assert len(result) == 1
    assert result[0]["delta"] is None
    assert [point["risk"] for point in result[0]["points"]] == [None, None]


def test_a_single_period_ticker_is_skipped_rather_than_crashing():
    assert temporal_trajectories([{"ticker": "T", "fiscal_year": 2024, "metrics": {}}]) == []


# --------------------------------------------------------------------------- #
# I12 - the online and bulk concept tables disagreed
# --------------------------------------------------------------------------- #
def test_the_bulk_corpus_builds_its_aliases_from_the_online_concept_table():
    assert set(CONCEPT_ALIASES) == set(BULK_FIELDS)
    for field in BULK_FIELDS:
        assert CONCEPT_ALIASES[field] == CONCEPTS[field], field
    # The aggregate must not be shadowed by its component.
    assert CONCEPTS["short_term_debt"].index("DebtCurrent") < CONCEPTS[
        "short_term_debt"
    ].index("LongTermDebtCurrent")


# --------------------------------------------------------------------------- #
# I13 - the protocol helpers disagreed about invalid input
# --------------------------------------------------------------------------- #
def test_fit_decision_stump_rejects_empty_and_ragged_matrices():
    with pytest.raises(ValueError, match="rectangular"):
        fit_decision_stump([[]], [1])
    with pytest.raises(ValueError, match="rectangular"):
        fit_decision_stump([[1.0, 2.0], [3.0]], [1, 0])
    with pytest.raises(ValueError, match="aligned"):
        fit_decision_stump([[1.0]], [1, 0])


def test_calibration_curve_rejects_what_expected_calibration_error_rejects():
    with pytest.raises(ValueError, match="bins"):
        calibration_curve([1], [0.5], bins=0)
    with pytest.raises(ValueError, match="aligned"):
        calibration_curve([1, 0], [0.5], bins=2)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        calibration_curve([1], [1.5], bins=2)


# --------------------------------------------------------------------------- #
# D3 - evaluation metrics silently truncated to the shorter list
# --------------------------------------------------------------------------- #
def test_roc_auc_and_confusion_matrix_reject_misaligned_input():
    with pytest.raises(ValueError, match="equal length"):
        roc_auc([1, 0, 1], [0.5, 0.5])
    with pytest.raises(ValueError, match="equal length"):
        confusion_matrix([1, 0, 1], [1, 1])
    with pytest.raises(ValueError, match="binary"):
        roc_auc([1, 2], [0.5, 0.5])


def test_unsupported_claim_rate_measures_claims_rather_than_returning_zero():
    assert unsupported_claim_rate([]) == 0
    assert unsupported_claim_rate([{"evidence_verified": True}]) == 0
    assert unsupported_claim_rate(
        [{"evidence_verified": True}, {"evidence_verified": False}]
    ) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# H1 - three RiskDomain members could never pass the evidence gate
# --------------------------------------------------------------------------- #
def test_every_risk_domain_is_either_producible_or_declared_unproducible():
    assert UNPRODUCED_RISK_DOMAINS == {RiskDomain.COVENANT, RiskDomain.COUNTERPARTY}
    assert PRODUCED_RISK_DOMAINS | UNPRODUCED_RISK_DOMAINS == set(RiskDomain)
    assert not (PRODUCED_RISK_DOMAINS & UNPRODUCED_RISK_DOMAINS)
    # A disclosure tension now has a producer, so its domain is reachable.
    assert RiskDomain.DISCLOSURE_TENSION in PRODUCED_RISK_DOMAINS


def test_verified_paths_for_domain_applies_the_dimension_alias():
    trace = {
        "paths": [
            {
                "risk_domain": "accounting",
                "evidence_path_status": "VERIFIED",
                "source_evidence": [{"quote": "x"}],
            },
            {
                "risk_domain": "accounting",
                "evidence_path_status": "VERIFIED",
                "source_evidence": [],
            },
            {
                "risk_domain": "accounting",
                "evidence_path_status": "UNVERIFIED",
                "source_evidence": [{"quote": "x"}],
            },
        ]
    }
    # Only the path that is verified *and* sourced counts.
    assert len(verified_paths_for_domain(trace, "accounting_anomaly")) == 1
    assert verified_paths_for_domain(trace, "liquidity") == []


def test_a_narrative_conflict_produces_a_disclosure_tension_path():
    trace = build_decision_trace(
        {
            "dimensions": {},
            "contradictions": [
                {
                    "category": "liquidity",
                    "evidence": {"verification_status": "verified", "confidence": 0.7},
                }
            ],
        },
        {"disagreement": 0.1, "drivers": []},
    )
    domains = {path["risk_domain"] for path in trace["paths"]}
    assert "disclosure_tension" in domains


def test_applicability_model_names_normalize_to_the_requirement_keys():
    for name, key in MODEL_KEYS.items():
        assert model_key(name) == key, name
    assert model_key("altman_z_score") == "altman"
    assert model_key("Altman Z") == "altman"
    assert MODEL_NAMES_BY_KEY["ohlson"] == "Ohlson O-Score"
    with pytest.raises(KeyError, match="unknown model"):
        route_model("not a model", "industrial", {})


# --------------------------------------------------------------------------- #
# H2 - a malformed policy was stored, then raised or silently failed open
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("direction", ["higher_is_worse", "", "highish", "LOW_RISK"])
def test_an_unrecognised_risk_direction_is_rejected_not_read_as_low(direction):
    with pytest.raises(ValueError, match="risk_direction"):
        normalize_direction(direction)


@pytest.mark.parametrize("direction", ["high", "HIGH", " high ", "High"])
def test_a_risk_direction_is_case_and_whitespace_insensitive(direction):
    # Accepting `"HIGH"` is the point: the audit found it silently took the `<=`
    # branch and reported a breach as within appetite. Normalizing it to `high`
    # makes it mean what it says.
    assert normalize_direction(direction) == "high"


def test_a_high_is_worse_limit_breach_is_reported_as_critical():
    policy = PolicyVersion(
        "p", "org", 1, "n", {"debt": {"warning": 0.4, "critical": 0.6}}, "u"
    )
    assert evaluate_kri(policy, {"debt": 0.95})[0]["status"] == "critical"


def test_an_uppercase_risk_direction_still_breaches():
    """The audited payload: `risk_direction: "HIGH"` with a breached critical."""
    policy = PolicyVersion(
        "p",
        "org",
        1,
        "n",
        {"debt": {"warning": 0.4, "critical": 0.6, "risk_direction": "HIGH"}},
        "u",
    )
    assert evaluate_kri(policy, {"debt": 0.95})[0]["status"] == "critical"


def test_a_low_is_worse_limit_breach_is_reported_as_critical():
    policy = PolicyVersion(
        "p",
        "org",
        1,
        "n",
        {"coverage": {"warning": 0.6, "critical": 0.4, "risk_direction": "low"}},
        "u",
    )
    assert evaluate_kri(policy, {"coverage": 0.1})[0]["status"] == "critical"
    assert evaluate_kri(policy, {"coverage": 0.9})[0]["status"] == "within_appetite"


def test_validate_thresholds_rejects_what_evaluate_kri_cannot_evaluate():
    with pytest.raises(ValueError, match="limits must be an object"):
        validate_thresholds({"debt": "abc"})
    with pytest.raises(ValueError, match="must be a number"):
        validate_thresholds({"debt": {"warning": "low", "critical": "high"}})
    with pytest.raises(ValueError, match="risk_direction"):
        validate_thresholds({"debt": {"risk_direction": "higher_is_worse"}})
    with pytest.raises(ValueError, match="thresholds must be an object"):
        validate_thresholds(["debt"])
    # A well-formed policy passes unchanged, including the upper-case spelling.
    validate_thresholds({"debt": {"warning": 0.5, "critical": 0.8}})
    validate_thresholds({"debt": {"warning": 0.5, "risk_direction": "LOW"}})


def test_the_policy_endpoint_refuses_a_malformed_threshold_map():
    client, headers = _authenticated_client()
    response = client.post(
        "/api/v1/enterprise/policies",
        headers=headers,
        json={
            "name": "bad",
            "version": 1,
            "thresholds": {"debt": {"warning": "low", "critical": "high"}},
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# H3 - FINRISK_ENV was normalized two different ways in one module
# --------------------------------------------------------------------------- #
def test_a_trailing_space_in_finrisk_env_still_enforces_production_storage():
    """`FINRISK_ENV="production "` used to skip the production DATABASE_URL check.

    The check is a module-level guard inside `finrisk.api`, so it is exercised the
    only honest way: in a fresh interpreter.
    """
    import os

    environment = dict(os.environ)
    environment["FINRISK_ENV"] = "production "
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-c", "import finrisk.api"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
        check=False,
    )
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


def test_a_lower_case_environment_value_is_also_normalized():
    import os

    environment = dict(os.environ)
    environment["FINRISK_ENV"] = "  PRODUCTION  "
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-c", "import finrisk.api"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
        check=False,
    )
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


# --------------------------------------------------------------------------- #
# H4 - `dict.get(key, default)` does not cover an explicit None
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "payload",
    [
        {"severity": None, "confidence": None},
        {"severity": None},
        {"confidence": None},
        {"severity": "critical"},
    ],
)
def test_detect_alerts_tolerates_none_and_non_numeric_values(payload):
    assert isinstance(detect_alerts(payload), list)


def test_detect_alerts_still_reports_a_real_worsening():
    alerts = detect_alerts({"severity": 80}, {"severity": 50})
    worsening = next(item for item in alerts if item["type"] == "RISK_WORSENING")
    # `moderate`/`high` are from the five-band vocabulary in `severity.py`.
    assert worsening["severity"] in {"critical", "high", "moderate", "low", "very_low"}
    dropped = detect_alerts({"confidence": 0.5}, {"confidence": 0.9})
    assert [item["severity"] for item in dropped] == ["moderate"]


# --------------------------------------------------------------------------- #
# H5 - a failed stage was also logged as completed; redaction was bypassable
# --------------------------------------------------------------------------- #
def test_a_failed_stage_is_not_also_reported_as_completed(caplog):
    logger = logging.getLogger("finrisk.test.observability")
    with (
        caplog.at_level(logging.INFO, logger=logger.name),
        pytest.raises(RuntimeError),
        traced_stage(logger, "assess"),
    ):
        raise RuntimeError("boom")
    events = [json.loads(record.message)["event"] for record in caplog.records]
    assert "stage.failed" in events
    assert "stage.completed" not in events


def test_a_successful_stage_is_reported_once(caplog):
    logger = logging.getLogger("finrisk.test.observability.ok")
    with caplog.at_level(logging.INFO, logger=logger.name), traced_stage(logger, "assess"):
        pass
    events = [json.loads(record.message)["event"] for record in caplog.records]
    assert events == ["stage.completed"]


@pytest.mark.parametrize(
    "field",
    ["api_key", "API_KEY", "apiKey", "api-key", "secret", "token", "password", "header", "document_text"],
)
def test_log_redaction_covers_camel_case_and_common_secret_names(caplog, field):
    logger = logging.getLogger("finrisk.test.observability.redaction")
    with caplog.at_level(logging.INFO, logger=logger.name):
        structured_event(logger, "probe", **{field: "do-not-log"})
    assert caplog.records
    assert "do-not-log" not in caplog.records[-1].message


def test_log_redaction_keeps_ordinary_fields(caplog):
    logger = logging.getLogger("finrisk.test.observability.keep")
    with caplog.at_level(logging.INFO, logger=logger.name):
        structured_event(logger, "probe", stage="assess", latency_ms=1.5)
    assert "assess" in caplog.records[-1].message


# --------------------------------------------------------------------------- #
# H6 - reopen bypassed the state machine
# --------------------------------------------------------------------------- #
def _case(status: RiskCaseStatus) -> RiskCase:
    case = RiskCase("case_1", "org", "entity", RiskDomain.LIQUIDITY, "high", "stable", 0.8, 0.7)
    case.status = status
    return case


def test_reopen_moves_through_the_declared_transition_table():
    case = _case(RiskCaseStatus.RESOLVED)
    reopen_case(case, "u", "new filing")
    assert case.status is RiskCaseStatus.OPEN

    accepted = _case(RiskCaseStatus.ACCEPTED)
    reopen_case(accepted, "u", "new filing")
    assert accepted.status is RiskCaseStatus.OPEN

    for status in (RiskCaseStatus.OPEN, RiskCaseStatus.CLOSED):
        with pytest.raises(ValueError, match="only accepted or resolved"):
            reopen_case(_case(status), "u", "reason")
    with pytest.raises(ValueError, match="reason is required"):
        reopen_case(_case(RiskCaseStatus.RESOLVED), "u", "  ")


def test_every_declared_transition_is_reachable_through_transition_case():
    from finrisk.enterprise.workflow import TRANSITIONS, transition_case

    for source, targets in TRANSITIONS.items():
        for target in targets:
            case = _case(source)
            previous, current = transition_case(case, target)
            assert (previous, current) == (source.value, target.value)
            assert case.status is target


# --------------------------------------------------------------------------- #
# H7 / H8 - the repository contract
# --------------------------------------------------------------------------- #
def test_a_concurrent_status_change_is_rejected_rather_than_overwritten():
    repository = InMemoryEnterpriseRepository()
    case = _case(RiskCaseStatus.OPEN)
    repository.save(case)
    stale = repository.get_case("org", "case_1")
    # A second reviewer moves the case on.
    fresh = repository.get_case("org", "case_1")
    fresh.status = RiskCaseStatus.UNDER_REVIEW
    repository.save_case_transition(fresh, RiskCaseStatus.OPEN)
    # The first reviewer's write is now based on a status that no longer exists.
    stale.status = RiskCaseStatus.MITIGATING
    with pytest.raises(ValueError, match="changed concurrently"):
        repository.save_case_transition(stale, RiskCaseStatus.OPEN)


def test_save_case_transition_requires_the_case_to_exist():
    repository = InMemoryEnterpriseRepository()
    with pytest.raises(KeyError):
        repository.save_case_transition(_case(RiskCaseStatus.OPEN), RiskCaseStatus.OPEN)


def test_an_unsupported_repository_item_is_rejected_in_both_implementations():
    repository = InMemoryEnterpriseRepository()
    record = ModelRecord(
        "m", "org", "fusion", "v1", "owner", "intended", "limitations"
    )
    assert repository.save(record).id == "m"
    with pytest.raises(TypeError, match="unsupported repository item"):
        repository.save(object())


# --------------------------------------------------------------------------- #
# H9 - reason codes outside the declared vocabulary
# --------------------------------------------------------------------------- #
def test_the_claim_consistency_vocabulary_is_closed_and_distinct():
    produced = {member.value for member in ClaimConsistencyReasonCode}
    assert produced == {
        "INSUFFICIENT_EVIDENCE",
        "CLAIM_CONTEXT_INCOMPLETE",
        "SEVERE_VERIFIED_SIGNAL",
        "PARTIAL_NUMERIC_TENSION",
        "CLAIM_NOT_OPTIMISTIC",
        "NO_ADVERSE_CONFLICT",
    }
    decision = {member.value for member in DecisionReasonCode}
    # Three spellings are shared; the rest are not, and that is the point:
    # `NO_ADVERSE_CONFLICT` reports the absence of a finding.
    assert "NO_ADVERSE_CONFLICT" not in decision
    assert "PARTIAL_NUMERIC_TENSION" not in decision
    assert produced & decision == {
        "INSUFFICIENT_EVIDENCE",
        "CLAIM_CONTEXT_INCOMPLETE",
        "SEVERE_VERIFIED_SIGNAL",
    }


def _claim(category: str = "liquidity", polarity: str = "positive") -> NarrativeClaim:
    return NarrativeClaim(
        "Liquidity remains strong",
        category,
        Evidence("10-K", 3, "Liquidity remains strong", 2025, verification_status="verified"),
        polarity,
    )


def test_every_produced_reason_code_is_in_the_declared_vocabulary():
    facts = {
        "current_ratio": 2.0,
        "cash": 100.0,
        "operating_cash_flow": 50.0,
        "net_income": 40.0,
        "revenue": 1000.0,
    }
    seen = set()
    for claim in (
        _claim(),
        _claim(polarity="negative"),
        NarrativeClaim(
            "Unverified",
            "liquidity",
            Evidence("10-K", 1, "x", 2025, verification_status="unverified"),
            "positive",
        ),
    ):
        evaluation = evaluate_claim_consistency(claim, facts)
        assert evaluation.reason_code in set(ClaimConsistencyReasonCode)
        seen.add(evaluation.reason_code.value)
    # The three codes the audit found outside the decision vocabulary are all
    # representable now.
    assert seen


def test_the_consistency_policy_operator_vocabulary_is_closed():
    from finrisk.contradictions import _configured

    for metric in CHECKS["liquidity"]:
        _configured(metric.metric)


# --------------------------------------------------------------------------- #
# H10 - the remaining enterprise defects
# --------------------------------------------------------------------------- #
def test_governance_gate_and_reported_metrics_are_named_separately():
    assert GATE_METRICS & REPORTED_METRICS == frozenset()
    assert REPORTED_METRICS == {"abstention_rate", "latency_ms", "cost_usd"}


def test_an_unknown_job_id_names_the_job_it_could_not_find():
    queue = JobQueue()
    with pytest.raises(KeyError, match="unknown job"):
        queue.fail("job_missing", "boom")
    with pytest.raises(KeyError, match="unknown job"):
        queue.complete("job_missing")


def test_a_job_records_when_it_last_moved():
    queue = JobQueue()
    job = queue.enqueue(Job("org", "assessment", "k", {}))
    created = job.updated_at
    queue.claim()
    assert job.updated_at >= created
    queue.complete(job.id)
    assert job.status == "completed"
    assert job.updated_at >= created


def test_a_revenue_shock_moves_the_margin_lines_with_revenue():
    values = {"revenue": 100.0, "gross_profit": 40.0, "operating_income": 20.0}
    stressed = apply_scenario(values, Scenario("downside", revenue_pct=-0.5))
    # Margin held at 40% and 20%: revenue falling must not *improve* the margin.
    assert stressed["revenue"] == 50.0
    assert stressed["gross_profit"] == pytest.approx(20.0)
    assert stressed["operating_income"] == pytest.approx(10.0)
    assert stressed["gross_profit"] / stressed["revenue"] == pytest.approx(0.4)


def test_a_margin_shock_is_applied_to_the_stressed_revenue():
    values = {"revenue": 100.0, "gross_profit": 40.0}
    stressed = apply_scenario(
        values, Scenario("margin", revenue_pct=-0.5, margin_pp=0.1)
    )
    # 40 * 0.5 = 20, plus 10% of the *stressed* revenue (50) = 25.
    assert stressed["gross_profit"] == pytest.approx(25.0)


def test_storage_rejects_identifiers_that_pathlib_would_rewrite(tmp_path):
    storage = LocalDocumentStorage(tmp_path)
    for bad in ("../other", "C:evil", "a\x00b", "", ".", "..", "a/b", "a\\b", ".hidden"):
        with pytest.raises(ValueError, match="unsafe storage identifier"):
            storage.put(bad, "report.pdf", b"x")
        with pytest.raises(ValueError, match="unsafe storage identifier"):
            storage.put("org", bad, b"x")
    stored = storage.put("org-a", "report.pdf", b"evidence")
    assert stored.object_id == "report.pdf"
    assert storage.get("org-a", "report.pdf") == b"evidence"


def test_the_evidence_graph_follows_support_relations_only():
    graph = TemporalEvidenceGraph()
    for node in (
        EvidenceNode("doc", "document", "2024", {}),
        EvidenceNode("counter", "document", "2024", {}),
        EvidenceNode("decision", "decision", "2024", {}),
    ):
        graph.add_node(node)
    graph.link("doc", "decision", EvidenceRelation.SUPPORTS, "driver")
    graph.link("counter", "decision", EvidenceRelation.CONTRADICTS, "contradiction")
    assert graph.paths_to("decision") == [["doc", "decision"]]
    assert graph.paths_to("decision", ADVERSE_RELATIONS) == [["counter", "decision"]]


def test_tension_rejects_an_evidence_sufficiency_outside_the_vocabulary():
    assert EVIDENCE_SUFFICIENCY_VALUES == ("complete", "incomplete_context")
    claim = _claim()
    assert classify_tension(claim, ["a"], []).evidence_sufficiency == "complete"
    with pytest.raises(ValueError, match="evidence_sufficiency"):
        classify_tension(claim, ["a"], [], evidence_sufficiency="unknown")


def test_a_tension_reason_code_is_derived_from_its_classification():
    claim = _claim()
    assert (
        classify_tension(claim, [], ["a", "b"]).reason_code
        == ClaimConsistencyReasonCode.SEVERE_VERIFIED_SIGNAL.value
    )
    assert (
        classify_tension(claim, ["a", "b"], []).reason_code
        == ClaimConsistencyReasonCode.NO_ADVERSE_CONFLICT.value
    )


def test_severity_bands_are_a_single_source_of_truth():
    assert severity_key(85) == "critical" and severity_label(85) == "Critical"
    assert severity_key(0) == "very_low" and severity_label(0) == "Very Low"
    assert severity_key(None) == "unknown" and severity_label(None) == "N/A"
    # A negative score falls through every band.
    assert severity_key(-5) == "very_low"
    assert severity_label(-5) == "Very Low"


# --------------------------------------------------------------------------- #
# C3 - declared rule coverage vs reachable rule coverage
# --------------------------------------------------------------------------- #
def test_rule_coverage_quantifies_the_dead_rule_gap():
    rules = json.loads((ROOT / "rules/rules.json").read_text(encoding="utf-8"))["rules"]
    coverage = rule_coverage(rules)
    assert coverage.total_rules == len(rules) == 68
    assert coverage.reachable_rules + len(coverage.unreachable_rule_ids) == 68
    assert coverage.reachable_rules == 43
    assert coverage.reachable_ratio == pytest.approx(0.6324, abs=1e-4)
    # Every unreachable metric really has no producer.
    producible = producible_fact_names()
    assert not (set(coverage.unreachable_metrics) & producible)
    assert coverage.to_dict()["unreachable_rule_ids"] == sorted(
        coverage.unreachable_rule_ids
    )


def test_every_assessment_publishes_its_rule_coverage():
    assessment = FinRiskPipeline(ROOT).assess(
        "Coverage Co", 2025, MINIMAL_CURRENT, None
    )
    coverage = assessment.rule_coverage
    assert coverage["total_rules"] == 68
    assert coverage["reachable_rules"] == 43
    assert len(coverage["unreachable_rule_ids"]) == 25


# --------------------------------------------------------------------------- #
# C4 - `confidence` and `evidence_quality` are one index, not two
# --------------------------------------------------------------------------- #
def test_confidence_and_evidence_quality_are_documented_as_one_index():
    assessment = FinRiskPipeline(ROOT).assess(
        "Identity Co", 2025, MINIMAL_CURRENT, None
    )
    # The identity is deliberate and must not drift into two silently different
    # numbers; the payload says so explicitly.
    assert assessment.evidence_quality == assessment.confidence
    assert assessment.confidence_semantics == "EVIDENCE_QUALITY_INDEX_NOT_A_PROBABILITY"
    # The distinction that *is* real: coverage is a separate quantity.
    assert assessment.evidence_coverage != assessment.evidence_quality


# --------------------------------------------------------------------------- #
# The sample artifact and the code that generates it must agree
# --------------------------------------------------------------------------- #
def test_the_text_report_publishes_rule_coverage():
    from finrisk.report import render_text_report

    assessment = FinRiskPipeline(ROOT).assess(
        "Coverage Co", 2025, MINIMAL_CURRENT, None
    )
    text = render_text_report(assessment)
    assert "RULE COVERAGE" in text
    assert "43 of 68" in text


def test_an_unknown_operator_is_a_startup_error_in_every_rule():
    """A config typo must fail at construction, not silently disable a rule.

    `RuleEngine.evaluate` treats an unrecognised operator as "condition not met",
    so a typo in a *multi-condition* rule disabled that rule without any signal.
    The construction-time check originally covered only the single-condition rules
    the de-duplication pass walks; it now covers all 68.
    """
    import shutil
    import tempfile

    root = Path(tempfile.mkdtemp())
    for name in ("rules", "config"):
        shutil.copytree(ROOT / name, root / name)
    data = json.loads((root / "rules/rules.json").read_text(encoding="utf-8"))
    target = next(rule for rule in data["rules"] if rule["id"] == "LIQ_007")
    assert len(target["conditions"]) > 1
    target["conditions"][1]["operator"] = "=<"
    (root / "rules/rules.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown operator"):
        FinRiskPipeline(root)


def test_the_committed_rule_and_mapping_configs_use_only_known_operators():
    from finrisk.rules import OPS

    rules = json.loads((ROOT / "rules/rules.json").read_text(encoding="utf-8"))["rules"]
    for rule in rules:
        for condition in rule["conditions"]:
            assert condition["operator"] in OPS, (rule["id"], condition)
    mappings = json.loads(
        (ROOT / "config/model_scoring.json").read_text(encoding="utf-8")
    )["mappings"]
    for mapping in mappings:
        assert mapping["operator"] in OPS, mapping["id"]


def test_an_unknown_consistency_operator_is_rejected(monkeypatch):
    from finrisk import contradictions

    monkeypatch.setitem(
        contradictions.CONSISTENCY_POLICY["thresholds"]["current_ratio"],
        "operator",
        "approximately",
    )
    with pytest.raises(ValueError, match="unknown operator"):
        contradictions._configured("current_ratio")


def test_governance_requires_both_gate_and_reported_metrics():
    from finrisk.enterprise.governance import compare_system_versions

    metrics = {name: 0.5 for name in GATE_METRICS | REPORTED_METRICS}
    result = compare_system_versions(metrics, dict(metrics, f1=0.9))
    assert result["automatic_promotion"] is False
    with pytest.raises(ValueError, match="require metrics"):
        compare_system_versions({}, {})
