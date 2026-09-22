import asyncio
import json
import shutil
from pathlib import Path

import pytest
from finrisk.api import AssessmentRequest, _run_document_isolated
from finrisk.document_worker import PdfBoundaryError, inspect_pdf, run_inspect_worker
from finrisk.domain import RuleSignal
from finrisk.enterprise.api import FusionRequest, RiskSnapshotRequest
from finrisk.enterprise.applicability import MODEL_KEYS
from finrisk.enterprise.domain import (
    AuditEvent,
    Entity,
    Organization,
    PolicyVersion,
    Principal,
    RiskCase,
    RiskDomain,
    Role,
)
from finrisk.enterprise.evidence_graph import (
    EvidenceNode,
    EvidenceRelation,
    TemporalEvidenceGraph,
)
from finrisk.enterprise.policy import evaluate_kri
from finrisk.enterprise.repository import InMemoryEnterpriseRepository
from finrisk.enterprise.scenario import Scenario, apply_scenario
from finrisk.evidence import claim_is_grounded
from finrisk.metrics import calculate_metrics, growth_ratio
from finrisk.models import altman_variant
from finrisk.normalization import normalize_line_item, parse_number
from finrisk.numeric_benchmark import temporal_trajectories
from finrisk.parser import DocumentParser
from finrisk.pipeline import FinRiskPipeline
from finrisk.rules import RuleEngine, unproducible_rule_conditions
from finrisk.scoring import effective_signals
from finrisk.tools.ingestion import ingest_pdf
from finrisk.xbrl import parse_companyfacts

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


def test_parse_number_handles_both_separator_conventions():
    """A comma plus a dot is unambiguous: the last separator is the decimal one.

    Only one convention used to be understood, so ``1,234.56`` -- the usual way a
    US filing writes a non-integer -- fell through to float() and returned None,
    which silently dropped the value from a PDF extraction.
    """
    assert parse_number("1,234.56") == 1234.56
    assert parse_number("12,345.6") == 12345.6
    assert parse_number("(1,234.56)") == -1234.56
    assert parse_number("1,234.56%") == 12.3456
    assert parse_number("1,234.56", "millions") == 1_234_560_000.0
    # European convention: the dot groups thousands, the comma is the decimal.
    assert parse_number("1.234,56") == 1234.56
    # Single-separator behaviour is unchanged.
    assert parse_number("1,234") == 1234.0
    assert parse_number("1,234,567") == 1234567.0
    assert parse_number("1234,56") == 1234.56
    assert parse_number("0,5") == 0.5
    assert parse_number("1.5") == 1.5


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


def test_model_scoring_config_only_names_known_models():
    """Every model named by the config must be routable by the code."""
    config = json.loads((ROOT / "config" / "model_scoring.json").read_text(encoding="utf-8"))
    assert {mapping["model"] for mapping in config["mappings"]} <= set(MODEL_KEYS)
    FinRiskPipeline(ROOT)  # the construction-time assertion must hold


def test_pipeline_rejects_a_config_with_an_unknown_model_name(tmp_path):
    """A config typo must fail at construction, not as an unexplained 500."""
    for item in ("rules", "config"):
        shutil.copytree(ROOT / item, tmp_path / item)
    config = json.loads((tmp_path / "config" / "model_scoring.json").read_text(encoding="utf-8"))
    config["mappings"][0]["model"] = "Typo Z-Score"
    (tmp_path / "config" / "model_scoring.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown models"):
        FinRiskPipeline(tmp_path)


def test_the_model_name_registry_has_a_single_source():
    """The report-label -> key map must not be re-duplicated per module."""
    literal = '"Altman Z-Score": "altman"'
    carriers = [
        path.name
        for path in (ROOT / "backend").rglob("*.py")
        if literal in path.read_text(encoding="utf-8")
    ]
    assert carriers == ["applicability.py"], carriers


def test_a_denormal_prior_period_yields_no_growth_not_infinity():
    """`inf` is not JSON: it serialises as the `Infinity` token and breaks clients.

    `_safe_div` already rejected non-finite quotients, but the growth calculations
    divided directly, so a prior of 1e-320 published `inf` as a growth rate.
    """
    assert growth_ratio(1.0, 1e-320) is None
    assert growth_ratio(110.0, 100.0) == pytest.approx(0.1)
    # A sign change is still "undefined", not growth.
    assert growth_ratio(-50.0, -100.0) is None
    metrics = calculate_metrics({"revenue": 1.0}, 2025, {"revenue": 1e-320})
    assert metrics["revenue_growth"].value is None


def test_parse_companyfacts_survives_a_malformed_caller_payload():
    """`companyfacts` arrives from a public POST body with no schema behind it."""
    assert parse_companyfacts({}) == []
    assert parse_companyfacts({"facts": "not-a-dict"}) == []
    assert parse_companyfacts({"facts": {"us-gaap": [1, 2]}}) == []
    assert parse_companyfacts({"facts": {"us-gaap": {"Revenues": "oops"}}}) == []
    assert parse_companyfacts(
        {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"val": "abc", "fy": 2024}]}}}}},
        [2024],
    ) == []


def test_temporal_trajectory_delta_skips_unscored_endpoints():
    """A filing with none of the growth inputs scores None; `None - None` crashed."""
    sparse = [
        {"ticker": "X", "fiscal_year": 2023, "metrics": {"current_ratio": None}},
        {"ticker": "X", "fiscal_year": 2024, "metrics": {"current_ratio": None}},
    ]
    trajectory = temporal_trajectories(sparse)[0]
    assert trajectory["delta"] is None
    assert [point["risk"] for point in trajectory["points"]] == [None, None]


def test_policy_evaluation_refuses_a_kri_without_a_direction():
    """Reading a missing `risk_direction` as 'high' failed open."""
    policy = PolicyVersion("p", "o", 1, "base", {"leverage": {"warning": 3.0}}, "u")
    with pytest.raises(ValueError, match="risk_direction"):
        evaluate_kri(policy, {"leverage": 4.0})
    directed = PolicyVersion(
        "p", "o", 1, "base", {"leverage": {"warning": 3.0, "risk_direction": "low"}}, "u"
    )
    assert evaluate_kri(directed, {"leverage": 4.0})[0]["status"] == "within_appetite"


def test_a_margin_shock_is_priced_on_the_stressed_revenue():
    stressed = apply_scenario(
        {"revenue": 100.0, "gross_profit": 40.0},
        Scenario("downside", revenue_pct=-0.1, margin_pp=-0.02),
    )
    assert stressed["revenue"] == pytest.approx(90.0)
    assert stressed["gross_profit"] == pytest.approx(40.0 - 1.8)


def test_path_enumeration_is_bounded():
    """A densely linked DAG used to enumerate paths until the process OOMed."""
    graph = TemporalEvidenceGraph()
    graph.add_node(EvidenceNode("t", "claim", "2024", {"value": 1.0}))
    for index in range(12):
        graph.add_node(EvidenceNode(f"n{index}", "claim", "2024", {"value": 1.0}))
        graph.link(f"n{index}", "t", EvidenceRelation.SUPPORTS, "because")
    assert len(graph.paths_to("t", max_paths=5)) == 5
    with pytest.raises(ValueError):
        graph.paths_to("t", max_paths=0)


def _pdf_with_text(text: str) -> bytes:
    stream = ("BT /F1 11 Tf 72 720 Td (" + text + ") Tj ET").encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, item in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + item + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{start}\n%%EOF\n").encode()
    return bytes(out)


def _encrypted_pdf() -> bytes:
    import io

    import pymupdf as fitz

    document = fitz.open()
    document.new_page().insert_text((72, 720), "BALANCE SHEET")
    buffer = io.BytesIO()
    document.save(buffer, encryption=fitz.PDF_ENCRYPT_AES_256,
                  owner_pw="owner", user_pw="user")
    return buffer.getvalue()


def test_inspect_pdf_enforces_page_and_text_boundaries():
    # `inspect_pdf` runs in a spawned child, which coverage cannot measure, so it is
    # exercised directly here as well.
    inspect_pdf(_pdf_with_text("BALANCE SHEET"), 500, 5_000_000)
    with pytest.raises(PdfBoundaryError) as exc:
        inspect_pdf(_encrypted_pdf(), 500, 5_000_000)
    assert exc.value.status_code == 422
    assert "encrypted" in exc.value.detail
    with pytest.raises(PdfBoundaryError) as exc:
        inspect_pdf(_pdf_with_text("x"), 0, 5_000_000)
    assert exc.value.status_code == 413
    with pytest.raises(PdfBoundaryError) as exc:
        inspect_pdf(_pdf_with_text("BALANCE SHEET"), 500, 1)
    assert exc.value.status_code == 413
    with pytest.raises(PdfBoundaryError) as exc:
        inspect_pdf(b"not a PDF at all", 500, 5_000_000)
    assert exc.value.status_code == 422


def test_inspect_worker_reports_boundaries_through_the_queue():
    class Queue:
        def __init__(self):
            self.payload = None

        def put(self, value):
            self.payload = value

    queue = Queue()
    run_inspect_worker(queue, _pdf_with_text("BALANCE SHEET"), 500, 5_000_000)
    assert queue.payload == ("ok", None)

    queue = Queue()
    run_inspect_worker(queue, b"not a PDF", 500, 5_000_000)
    assert queue.payload[0] == "boundary"
    assert queue.payload[1][0] == 422
