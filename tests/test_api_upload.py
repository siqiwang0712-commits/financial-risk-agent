import time

import fitz
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
    assert body["extraction"]["review_required"] is True
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
    assert statuses == {"located"}


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
