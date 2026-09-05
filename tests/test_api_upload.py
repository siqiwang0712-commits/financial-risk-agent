import fitz
from fastapi.testclient import TestClient
from finrisk.api import app


def test_pdf_upload_reaches_assessment_pipeline():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72), "BALANCE SHEET\nCash and cash equivalents 1,250\nTotal assets 5,000"
    )
    pdf = doc.tobytes()
    doc.close()
    response = TestClient(app).post(
        "/api/v1/documents/analyze",
        data={"company": "Synthetic API Co", "fiscal_year": "2025"},
        files={"file": ("synthetic.pdf", pdf, "application/pdf")},
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
    response = TestClient(app).post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("x.pdf", b"not-pdf", "application/pdf")},
    )
    assert response.status_code == 415


def test_conflicting_candidates_are_not_silently_selected():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "BALANCE SHEET\nCash and cash equivalents 100\nCash and cash equivalents 200\nTotal assets 500",
    )
    pdf = doc.tobytes()
    doc.close()
    response = TestClient(app).post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("x.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 200
    issues = response.json()["extraction"]["review_issues"]
    assert any(x["line_item"] == "cash" for x in issues)


def test_pdf_upload_preserves_prior_year_for_trends():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "BALANCE SHEET\n2025 2024\nCash and cash equivalents 120 100\nTotal assets 500 450",
    )
    pdf = doc.tobytes()
    doc.close()
    response = TestClient(app).post(
        "/api/v1/documents/analyze",
        data={"company": "X", "fiscal_year": "2025"},
        files={"file": ("x.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["extraction"]["prior_year"] == 2024
