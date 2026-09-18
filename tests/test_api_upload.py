import time

import pymupdf as fitz
from fastapi.testclient import TestClient
from finrisk.api import agent, app


def authenticated_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(app)
    response = client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "API test tenant", "actor_id": "test-admin"},
    )
    assert response.status_code == 200
    return client, {"X-API-Key": response.json()["api_key"]}


def pdf_bytes(*texts: str) -> bytes:
    doc = fitz.open()
    for text in texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    result = doc.tobytes()
    doc.close()
    return result


def test_pdf_upload_reaches_assessment_pipeline():
    client, headers = authenticated_client()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72), "BALANCE SHEET\nCash and cash equivalents 1,250\nTotal assets 5,000"
    )
    pdf = doc.tobytes()
    doc.close()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "Synthetic API Co", "fiscal_year": "2025"},
        files={"file": ("synthetic.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["company"] == "Synthetic API Co"
    assert body["extraction"]["candidate_count"] >= 2
    assert body["extraction"]["review_required"] is False
    assert body["agent"]["trace"]
    assert body["agent"]["status"] in {
        "COMPLETED",
        "INSUFFICIENT_EVIDENCE",
        "REVIEW_REQUIRED",
    }
    statuses = {
        n.get("status")
        for n in body["evidence_graph"]["nodes"]
        if n["type"] == "financial_value"
    }
    assert statuses == {"verified"}


def test_upload_rejects_non_pdf():
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("x.pdf", b"not-pdf", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 415


def test_upload_limit_comes_from_environment(monkeypatch):
    monkeypatch.setenv("FINRISK_MAX_UPLOAD_MB", "1")
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("large.pdf", b"%PDF" + b"x" * 1024 * 1024, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "PDF upload-size limit exceeded"


def test_pdf_page_limit_is_fail_closed(monkeypatch):
    monkeypatch.setenv("FINRISK_MAX_PDF_PAGES", "1")
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("pages.pdf", pdf_bytes("one", "two"), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "PDF page limit exceeded"


def test_pdf_text_limit_is_fail_closed(monkeypatch):
    monkeypatch.setenv("FINRISK_MAX_EXTRACTED_CHARS", "4")
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("text.pdf", pdf_bytes("long text"), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "PDF extracted-text limit exceeded"


def test_invalid_and_encrypted_pdfs_are_rejected():
    client, headers = authenticated_client()
    invalid = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("invalid.pdf", b"%PDF broken", "application/pdf")},
        headers=headers,
    )
    assert invalid.status_code == 422

    doc = fitz.open()
    doc.new_page()
    encrypted_bytes = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    doc.close()
    encrypted = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("encrypted.pdf", encrypted_bytes, "application/pdf")},
        headers=headers,
    )
    assert encrypted.status_code == 422
    assert encrypted.json()["detail"] == "encrypted PDFs are not supported"


def test_analysis_timeout_cleans_temporary_file(monkeypatch):
    seen_paths = []

    def slow_run(*args, **kwargs):
        seen_paths.append(args[2])
        time.sleep(0.1)

    monkeypatch.setattr(agent, "run_document", slow_run)
    monkeypatch.setenv("FINRISK_ANALYSIS_TIMEOUT_SECONDS", "0.02")
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("timeout.pdf", pdf_bytes("valid"), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 504
    assert seen_paths
    assert all(not path.exists() for path in seen_paths)


def test_conflicting_candidates_are_not_silently_selected():
    client, headers = authenticated_client()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "BALANCE SHEET\nCash and cash equivalents 100\nCash and cash equivalents 200\nTotal assets 500",
    )
    pdf = doc.tobytes()
    doc.close()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("x.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200
    issues = response.json()["extraction"]["review_issues"]
    assert any(x["line_item"] == "cash" for x in issues)
    assert not any(
        node["type"] == "financial_value" and node["label"] == "cash"
        for node in response.json()["evidence_graph"]["nodes"]
    )


def test_pdf_upload_preserves_prior_year_for_trends():
    client, headers = authenticated_client()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "BALANCE SHEET\n2025 2024\nCash and cash equivalents 120 100\nTotal assets 500 450",
    )
    pdf = doc.tobytes()
    doc.close()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("x.pdf", pdf, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["extraction"]["prior_year"] == 2024


def test_document_analysis_rejects_missing_or_cross_tenant_entity_before_processing(monkeypatch):
    monkeypatch.setenv("FINRISK_ENV", "production")
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025", "entity_id": "not-owned"},
        files={"file": ("x.pdf", pdf_bytes("valid"), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "entity_id is not available to this tenant"


def test_agent_analysis_persists_tenant_snapshot_for_risk_case():
    client, headers = authenticated_client()
    entity = client.post(
        "/api/v1/enterprise/entities", headers=headers, json={"name": "Analyzed entity"}
    ).json()
    analysis = client.post(
        "/api/v1/agent/assess",
        headers=headers,
        json={
            "company": "Analyzed entity",
            "fiscal_year": 2025,
            "entity_id": entity["id"],
            "current": {
                "cash": 100, "current_assets": 300, "current_liabilities": 200,
                "total_assets": 1000, "total_liabilities": 500,
                "short_term_debt": 20, "long_term_debt": 180,
                "shareholder_equity": 500, "revenue": 800,
                "net_income": 80, "operating_cash_flow": 100,
            },
        },
    )
    assert analysis.status_code == 200
    snapshot = analysis.json()["analysis_snapshot"]
    assert snapshot["organization_id"]
    assert snapshot["entity_id"] == entity["id"]
    assert analysis.json()["decision_bundle"]["organization_id"] == snapshot["organization_id"]
    assert analysis.json()["decision_bundle"]["entity_id"] == entity["id"]
    created = client.post(
        "/api/v1/enterprise/risk-cases",
        headers=headers,
        json={
            "entity_id": entity["id"], "domain": "liquidity",
            "snapshot_id": snapshot["id"], "rationale": "server-derived assessment",
        },
    )
    assert created.status_code == 200
    assert created.json()["snapshot_id"] == snapshot["id"]


def test_risk_case_rejects_snapshot_from_other_entity_in_same_tenant():
    client, headers = authenticated_client()
    first = client.post(
        "/api/v1/enterprise/entities", headers=headers, json={"name": "First"}
    ).json()
    second = client.post(
        "/api/v1/enterprise/entities", headers=headers, json={"name": "Second"}
    ).json()
    analysis = client.post(
        "/api/v1/agent/assess",
        headers=headers,
        json={
            "company": "First", "fiscal_year": 2025, "entity_id": first["id"],
            "current": {"cash": 10, "current_assets": 20, "current_liabilities": 10},
        },
    ).json()
    response = client.post(
        "/api/v1/enterprise/risk-cases",
        headers=headers,
        json={
            "entity_id": second["id"], "domain": "liquidity",
            "snapshot_id": analysis["analysis_snapshot"]["id"], "rationale": "invalid scope",
        },
    )
    assert response.status_code == 422


def test_assessment_rejects_nonfinite_and_boolean_numeric_inputs():
    client, headers = authenticated_client()
    for value in ("NaN", "Infinity", "-Infinity", True):
        response = client.post(
            "/api/v1/agent/assess", headers=headers,
            json={"company": "Invalid", "fiscal_year": 2025, "current": {"cash": value}},
        )
        assert response.status_code == 422


def test_entity_creation_with_an_unknown_parent_is_rejected_not_a_500():
    """A caller-supplied parent_id used to raise KeyError out of the service.

    `/entities` was the only enterprise route without the sibling error mapping,
    so the catch-all middleware turned it into `500 internal server error`.
    """
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/enterprise/entities",
        headers=headers,
        json={"name": "Child", "parent_id": "does-not-exist"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "entity creation rejected"


def test_reanalysing_the_same_entity_is_idempotent_not_a_500():
    """Re-running a filing for an existing entity used to return 500.

    The decision bundle id is derived from the organisation, entity and document
    versions, so the second analysis of the *same* filing produces the same id
    and both repositories reject the duplicate write (`decision bundle already
    exists`). That ValueError escaped `persist_agent_snapshot`, and the route
    answered `500 internal server error` for a perfectly ordinary action.
    """
    client, headers = authenticated_client()
    entity = client.post(
        "/api/v1/enterprise/entities", headers=headers, json={"name": "Repeat entity"}
    ).json()
    pdf = pdf_bytes(
        "BALANCE SHEET\nCash and cash equivalents 1,250\nTotal assets 5,000\n"
        "Total liabilities 2,000\nRevenue 4,000\nNet income 300"
    )
    responses = [
        client.post(
            "/api/v1/documents/analyze",
            headers=headers,
            data={"company": "Repeat Co", "fiscal_year": "2025", "entity_id": entity["id"]},
            files={"file": ("repeat.pdf", pdf, "application/pdf")},
        )
        for _ in range(3)
    ]
    for response in responses:
        assert response.status_code == 200, response.text
    decisions = {response.json()["agent"]["decision"] for response in responses}
    assert len(decisions) == 1, decisions


def test_caller_supplied_model_metric_does_not_crash_the_assess_endpoints():
    """A model metric in `current` can cross its threshold without the model
    having been evaluated (Beneish/Piotroski need a prior period). That lookup
    used to raise StopIteration out of `/api/v1/assess` as a 500."""
    client, headers = authenticated_client()
    for metric in ("beneish_m_score", "piotroski_f_score", "altman_z_score", "ohlson_probability"):
        for path in ("/api/v1/assess", "/api/v1/agent/assess"):
            response = client.post(
                path,
                headers=headers,
                json={"company": "Caller metric", "fiscal_year": 2025, "current": {metric: 0.5}},
            )
            assert response.status_code == 200, f"{path} with {metric}: {response.text}"
