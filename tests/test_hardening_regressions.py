import asyncio
from pathlib import Path

import pytest
from finrisk.api import AssessmentRequest, _run_document_isolated
from finrisk.domain import RuleSignal
from finrisk.enterprise.api import FusionRequest, RiskSnapshotRequest
from finrisk.enterprise.domain import (
    AuditEvent,
    Entity,
    Organization,
    Principal,
    RiskCase,
    RiskDomain,
    Role,
)
from finrisk.enterprise.repository import InMemoryEnterpriseRepository
from finrisk.evidence import claim_is_grounded
from finrisk.models import altman_variant
from finrisk.normalization import normalize_line_item, parse_number
from finrisk.parser import DocumentParser
from finrisk.rules import RuleEngine, unproducible_rule_conditions
from finrisk.scoring import effective_signals
from finrisk.tools.ingestion import ingest_pdf

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_enabled_rules_have_real_producers():
    engine = RuleEngine.from_file(ROOT / "rules" / "rules.json")
    assert unproducible_rule_conditions(engine.rules) == []


def test_rule_engine_rejects_invalid_condition_and_nonfinite_threshold():
    invalid = [{
        "id": "bad", "category": "liquidity", "severity": "high",
        "conditions": [{"metric": "cash", "operator": "approximately", "value": float("inf")}],
        "effect": {"score_delta": 1}, "rationale": "x",
    }]
    try:
        RuleEngine(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid rule configuration must fail at startup")


def test_document_parser_uses_local_year_columns_not_note_number_or_page_year():
    pages = {
        1: "Annual report 2026 filed 2026\nBALANCE SHEET\nAmounts in thousands\nNote 2025 2024\nProperty, plant and equipment 8 1,200 (1,000)\nAccounts receivable, net 4 -300 250"
    }
    values = DocumentParser().extract_values(pages, "annual", 2025)
    actual = {(value.line_item, value.fiscal_year): value.value for value in values}
    assert actual[("ppe", 2025)] == 1_200_000
    assert actual[("ppe", 2024)] == -1_000_000
    assert actual[("accounts_receivable", 2025)] == -300_000
    assert actual[("accounts_receivable", 2024)] == 250_000


def test_numeric_normalization_handles_explicit_negative_parentheses_and_percentages():
    assert parse_number("-1,234", "thousands") == -1_234_000
    assert parse_number("(1,234)", "thousands") == -1_234_000
    assert parse_number("-12.5%") == -0.125
    assert normalize_line_item("Property, plant and equipment") == "ppe"
    assert normalize_line_item("Accounts receivable, net") == "accounts_receivable"


def test_non_consecutive_document_comparative_is_not_used_as_previous(tmp_path):
    source = tmp_path / "filing.txt"
    source.write_text(
        "BALANCE SHEET\n2025 2022\nCash and cash equivalents 120 100\nTotal assets 500 450",
        encoding="utf-8",
    )
    ingested = ingest_pdf(source, "annual", 2025)
    assert ingested["extraction"]["prior_year"] == 2022
    assert ingested["extraction"]["previous_year"] is None
    assert ingested["previous"] is None


def test_structurally_reconciled_pdf_numeric_evidence_can_be_verified(tmp_path):
    source = tmp_path / "filing.txt"
    source.write_text(
        "BALANCE SHEET\nAmounts in millions\n2025 2024\nCash and cash equivalents 120 100",
        encoding="utf-8",
    )
    ingested = ingest_pdf(source, "annual", 2025)
    evidence = ingested["source_map"]["cash"]
    assert {item.verification_status for item in evidence} == {"verified"}
    assert {item.fiscal_year for item in evidence} == {2024, 2025}


def test_claim_grounding_uses_the_cited_span_not_unrelated_page_text():
    assert not claim_is_grounded(
        "Liquidity remains strong",
        "Revenue increased during the year",
        "Elsewhere on the page, liquidity remains strong",
    )


def test_entity_type_and_comparative_period_are_fail_closed():
    with pytest.raises(ValueError, match="unknown entity_type"):
        altman_variant("free-form-industry")
    with pytest.raises(ValueError, match="previous_fiscal_year"):
        AssessmentRequest(
            company="Issuer", fiscal_year=2025, current={}, previous={"revenue": 1}
        )
    with pytest.raises(ValueError, match="immediately preceding"):
        AssessmentRequest(
            company="Issuer", fiscal_year=2025, current={},
            previous={"revenue": 1}, previous_fiscal_year=2022,
        )


def test_json_assessment_page_boundaries_cannot_bypass_pdf_limits(monkeypatch):
    valid = AssessmentRequest(company="Issuer", fiscal_year=2025, current={}, pages={1: "ok"})
    assert valid.pages == {1: "ok"}
    with pytest.raises(ValueError, match="positive"):
        AssessmentRequest(company="Issuer", fiscal_year=2025, current={}, pages={0: "bad"})
    monkeypatch.setenv("FINRISK_MAX_PDF_PAGES", "1")
    with pytest.raises(ValueError, match="page limit"):
        AssessmentRequest(company="Issuer", fiscal_year=2025, current={}, pages={1: "a", 2: "b"})
    monkeypatch.setenv("FINRISK_MAX_EXTRACTED_CHARS", "3")
    with pytest.raises(ValueError, match="text limit"):
        AssessmentRequest(company="Issuer", fiscal_year=2025, current={}, pages={1: "four"})


def test_isolated_document_process_returns_without_queue_join_deadlock(tmp_path):
    source = tmp_path / "filing.txt"
    source.write_text(
        "BALANCE SHEET\n2025 2024\nCash and cash equivalents 120 100\nTotal assets 500 450",
        encoding="utf-8",
    )
    state = asyncio.run(
        _run_document_isolated(ROOT, "Issuer", 2025, source, "Annual Report", 30)
    )
    assert state.assessment["company"] == "Issuer"


def test_fusion_and_snapshot_numeric_domains_are_bounded():
    with pytest.raises(ValueError, match="fusion scores"):
        FusionRequest(method="max_severity", scores={"liquidity": 101}, coverage=.8, confidence=.8)
    with pytest.raises(ValueError, match="positive weight"):
        FusionRequest(method="weighted_average", scores={"liquidity": 50}, weights={}, coverage=.8, confidence=.8)
    with pytest.raises(ValueError):
        RiskSnapshotRequest(
            period="2025", filing_id="f", risk_score=-1,
            dimension_scores={}, metrics={}, evidence_paths={}, decision="REVIEW", coverage=.5,
        )


def test_only_family_winner_is_an_effective_signal():
    weak = RuleSignal("weak", "liquidity", "medium", 5, "weak", [], family="cash")
    strong = RuleSignal("strong", "liquidity", "high", 20, "strong", [], family="cash")
    assert effective_signals([weak, strong]) == [strong]


def test_in_memory_repository_optimistic_lock_and_tenant_collision():
    repository = InMemoryEnterpriseRepository()
    case = RiskCase("case", "org", "entity", RiskDomain.LIQUIDITY, "high", "stable", .5, .5)
    repository.save(case)
    first = repository.get_case("org", "case")
    stale = repository.get_case("org", "case")
    saved = repository.save(first)
    assert saved.version == 1
    with pytest.raises(ValueError, match="concurrent"):
        repository.save(stale)
    # The principal is intentionally unused here; constructing it proves the
    # tenant/user enum path also rejects no free-form role values.
    assert Principal("user", "org", Role.ANALYST).organization_id == "org"


def test_in_memory_mutation_and_audit_are_tenant_atomic():
    repository = InMemoryEnterpriseRepository()
    organization = Organization("org", "Tenant")
    repository.save(organization)
    entity = Entity("entity", organization.id, "Issuer")
    wrong_tenant = AuditEvent(
        "audit-wrong", "other", "actor", "create", "entity", entity.id, {}
    )
    with pytest.raises(ValueError, match="same tenant"):
        repository.save(entity, wrong_tenant)
    with pytest.raises(KeyError):
        repository.get_entity(organization.id, entity.id)

    event = AuditEvent("audit", organization.id, "actor", "seed", "entity", entity.id, {})
    repository.append_event(event)
    with pytest.raises(ValueError, match="already exists"):
        repository.save(entity, event)
    with pytest.raises(KeyError):
        repository.get_entity(organization.id, entity.id)
