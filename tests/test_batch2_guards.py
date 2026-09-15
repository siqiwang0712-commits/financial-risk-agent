"""Guards for the decision, security, ingestion and metrics fixes (batch 2)."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from finrisk.api import app as full_app
from finrisk.enterprise.api import enterprise_router
from finrisk.enterprise.fusion import (
    failure_aware_decision,
    hierarchical_escalation,
    interaction_aware,
)
from finrisk.enterprise.observability import configure_logging
from finrisk.evaluation import average_precision, roc_auc
from finrisk.llm import MockNarrativeProvider, StructuredLLMProvider
from finrisk.normalization import normalize_line_item, parse_number
from finrisk.pipeline import FinRiskPipeline
from finrisk.tools.ingestion import ingest_pdf

ROOT = Path(__file__).resolve().parents[1]


# --- FUS-01: interaction_aware must not let a risk-free dimension lower the score
def test_interaction_aware_is_non_compensatory_in_added_dimensions():
    base = interaction_aware({"liquidity": 90, "solvency_leverage": 60}, 0.8, 0.9)
    with_zero = interaction_aware(
        {"liquidity": 90, "solvency_leverage": 60, "cash_flow": 0}, 0.8, 0.9
    )
    assert with_zero.score >= base.score


# --- AGT-02: one decision-bearing score, shared by both endpoints -------------
def test_decide_exposes_a_single_decision_score():
    payload = FinRiskPipeline(ROOT).decide(
        FinRiskPipeline(ROOT).assess(
            "Unify Co", 2025, {"current_assets": 80, "current_liabilities": 100, "cash": 5}
        )
    )
    assert payload["overall_score"] == payload["enterprise_fusion"]["score"]
    assert payload["weighted_dimension_score"] == payload["legacy_weighted_score"]
    assert payload["final_decision"] == payload["enterprise_fusion"]["decision"]
    assert "final_decision" in payload and "enterprise_fusion" in payload
    # DAT-03: the `/assess` response contract declares these three fields.
    assert set(payload["failure_state"]) >= {"decision", "degraded", "blocking_failures", "review_failures"}


# --- AGT-01: the registered claim_verification gate is real --------------------
def test_verification_gate_rejects_unsupported_and_accepts_derived():
    from finrisk.agent.state import MaterialConclusion
    from finrisk.agent.verification import verify_conclusions

    supported = MaterialConclusion(
        "net margin risk signal PRO_001", "loss", "risk_rules", "rule", 0.8,
        [{"verification_status": "verified"}],
    )
    derived = MaterialConclusion(
        "solvency risk signal SOL_001", "leverage", "risk_rules", "rule", 0.8,
        [{"verification_status": "derived"}],
    )
    located = MaterialConclusion(
        "unchecked claim", "x", "risk_rules", "rule", 0.8,
        [{"verification_status": "located"}],
    )
    accepted, warnings = verify_conclusions([supported, derived, located])
    assert {c.claim for c in accepted} == {supported.claim, derived.claim}
    assert any("unchecked claim" in warning for warning in warnings)


# --- SEC-01 / SEC-23: bootstrap is fail-closed when hardened -------------------
def _bootstrap_client(**kwargs) -> TestClient:
    router = enterprise_router(**kwargs)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_bootstrap_requires_the_configured_token():
    client = _bootstrap_client(bootstrap_token="s3cret")
    assert client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "No token", "actor_id": "a"},
    ).status_code == 403
    assert client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Wrong token", "actor_id": "a"},
        headers={"X-Bootstrap-Token": "wrong"},
    ).status_code == 403
    allowed = client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Right token", "actor_id": "a"},
        headers={"X-Bootstrap-Token": "s3cret"},
    )
    assert allowed.status_code == 200 and allowed.json()["api_key"]


def test_bootstrap_fails_closed_when_production_requires_a_token():
    client = _bootstrap_client(bootstrap_token=None, require_bootstrap_token=True)
    assert client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Prod", "actor_id": "a"},
    ).status_code == 403


# --- SEC-02: every route except the bootstrap whitelist is authenticated ------
def _requires_principal(route: object) -> bool:
    def walk(dependant: object) -> bool:
        for sub in getattr(dependant, "dependencies", []):
            if getattr(getattr(sub, "call", None), "__name__", "") == "principal":
                return True
            if walk(sub):
                return True
        return False

    return walk(getattr(route, "dependant", None))


def test_every_enterprise_route_requires_a_principal_except_bootstrap():
    router = enterprise_router()
    unauthenticated = {
        route.path
        for route in router.routes
        if getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
        and not _requires_principal(route)
    }
    assert unauthenticated == {"/api/v1/enterprise/organizations"}


# --- SEC-01: bootstrap is independently rate limited --------------------------
def test_bootstrap_is_rate_limited_even_without_a_token():
    client = _bootstrap_client(bootstrap_rate_limit=3)
    codes = [
        client.post(
            "/api/v1/enterprise/organizations",
            json={"name": f"Org {index}", "actor_id": "a"},
        ).status_code
        for index in range(5)
    ]
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429


# --- FIN-01: Altman routes by population and does not publish the Z key --------
def test_altman_variant_routes_by_entity_type():
    from finrisk.models import altman_z

    values = {
        "working_capital": 60, "retained_earnings": 50, "ebit": 30,
        "operating_income": 30, "shareholder_equity": 200, "total_liabilities": 300,
        "total_assets": 500, "revenue": 600, "current_assets": 100, "current_liabilities": 40,
        "cash": 20, "market_value_equity": 400,
    }
    assert altman_z(values, "industrial").derived_outputs["fact_key"] == "altman_z_score"
    private = altman_z(values, "private")
    assert private.derived_outputs["fact_key"] == "altman_z_prime_score"
    retail = altman_z(values, "retail")
    assert retail.derived_outputs["fact_key"] == "altman_z_double_prime_score"

    assessment = FinRiskPipeline(ROOT).assess(
        "Retail Co", 2025, values, entity_type="retail"
    )
    assert not [r for r in assessment.triggered_rules if r.rule_id == "MODEL_ALTMAN_DISTRESS"]
    altman = next(m for m in assessment.models if m.name == "Altman Z-Score")
    assert altman.derived_outputs.get("fact_key") == "altman_z_double_prime_score"


# --- FIN-21 / FIN-04: model inputs are reachable from line-item labels --------
def test_model_input_aliases_exist():
    assert normalize_line_item("Property, plant and equipment") == "ppe"
    assert normalize_line_item("Depreciation and amortization") == "depreciation"
    assert normalize_line_item("EBITDA") == "ebitda"
    assert normalize_line_item("Selling, general and administrative expenses") == "sga"


# --- RES-02: AUPRC must not reward tied scores --------------------------------
def test_average_precision_does_not_reward_tied_scores():
    assert average_precision([0, 0, 1], [0.0, 0.0, 0.0]) == pytest.approx(1 / 3)
    assert average_precision([0, 0, 1], [0.5, 0.5, 0.5]) == pytest.approx(1 / 3)
    # A constant-score baseline has no discriminative power: AUROC is 0.5.
    assert roc_auc([0, 0, 1], [0.5, 0.5, 0.5]) == pytest.approx(0.5)
    # A genuinely ranked prediction still scores well.
    assert average_precision([0, 0, 1], [0.1, 0.2, 0.9]) == pytest.approx(1.0)


# --- AGT-07: providers report their prompt version -----------------------------
def test_providers_expose_prompt_version():
    prompt_version = MockNarrativeProvider.prompt_version
    assert prompt_version and prompt_version != "mock-or-unversioned"
    provider = StructuredLLMProvider(transport=lambda payload: {})
    assert provider.prompt_version == provider.PROMPT_VERSION
    assert provider.model_id == provider.model


# --- OPS-01: logging is configured --------------------------------------------
def test_configure_logging_attaches_a_handler(monkeypatch):
    import logging

    from finrisk.enterprise import observability

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    root.handlers = []
    monkeypatch.setattr(observability, "_logging_configured", False)
    try:
        configure_logging("INFO")
        assert len(root.handlers) == 1
        assert root.level == logging.INFO
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)


def test_configure_logging_preserves_host_owned_handlers(monkeypatch):
    import logging

    from finrisk.enterprise import observability

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    host_handlers = [logging.NullHandler(), logging.NullHandler()]
    root.handlers = host_handlers
    monkeypatch.setattr(observability, "_logging_configured", False)
    try:
        configure_logging("DEBUG")
        assert root.handlers == host_handlers
        assert root.level == original_level
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)


# --- DAT-01 / DAT-02: prior-year evidence with value and unit ------------------
def test_ingestion_records_prior_year_evidence_with_value_and_unit(tmp_path):
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "CONSOLIDATED BALANCE SHEET\nAmounts in millions USD\n2025 2024\n"
        "Cash and cash equivalents 120 100",
    )
    path = tmp_path / "filing.pdf"
    path.write_bytes(document.tobytes())
    document.close()

    ingested = ingest_pdf(path, "10-K", 2025)
    sources = ingested["source_map"]["cash"]
    assert {ref.fiscal_year for ref in sources} == {2025, 2024}
    current = next(ref for ref in sources if ref.fiscal_year == 2025)
    assert current.value == 120_000_000 and current.unit == "USD"


# --- FIN-06: dead rules are audited and cannot silently grow -------------------
def test_dead_rule_count_does_not_grow():
    import json

    from finrisk.rules import unproducible_rule_conditions

    rules = json.loads((ROOT / "rules" / "rules.json").read_text(encoding="utf-8"))["rules"]
    dead_rules = {rule_id for rule_id, _ in unproducible_rule_conditions(rules)}
    # 25 checked-in rules reference a metric with no producer anywhere in the
    # codebase, so they can never fire. Repairing or deleting them is a product
    # decision; this ratchet only stops the number from growing.
    assert len(dead_rules) <= 25, sorted(dead_rules)
    # The rule added for negative-EBITDA leverage does have a producer.
    assert "SOL_009" not in dead_rules


# --- regression: the full application still constructs ------------------------
def test_full_app_still_boots():
    client = TestClient(full_app)
    assert client.get("/health/live").status_code == 200
    assert parse_number("1,234") == 1234
    assert failure_aware_decision(
        hierarchical_escalation({"liquidity": 70}, 0.8, 0.8), {"parser_failure": True}
    )["decision"] == "ABSTAIN"
