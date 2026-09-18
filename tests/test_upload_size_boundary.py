"""The upload ceiling is a *file* size, tested at the boundary.

Round 7 unified the variable name, but the two layers still measured different
things: the backend compares the uploaded PDF bytes against the limit, while the
proxy compared the whole encoded multipart body against the same number. A PDF of
exactly the configured size therefore came back 413 from the proxy before the
backend ever saw it. These tests pin the backend half of the contract — `<= limit`
must be analysed, `> limit` must be refused — and `frontend/test/proxy.test.mjs`
pins the proxy half (the framing allowance).

The boundary file is a genuinely parseable PDF padded to an exact byte length with
trailing PDF comment bytes, so the size gate is the only thing under test.
"""

from __future__ import annotations

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient
from finrisk.api import app

LIMIT = 4096


def authenticated_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(app)
    response = client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Boundary tenant", "actor_id": "boundary-admin"},
    )
    assert response.status_code == 200, response.text[:200]
    return client, {"X-API-Key": response.json()["api_key"]}


def _base_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "BOUNDARY CO\nBALANCE SHEET\nCash and cash equivalents 1,250\n"
        "Total assets 5,000\nRevenue 9,000\nNet income 400\n",
    )
    payload = document.tobytes()
    document.close()
    return payload


def pdf_of_exact_size(size: int) -> bytes:
    """A valid, parseable PDF whose byte length is exactly `size`."""
    base = _base_pdf()
    assert size >= len(base), f"the base PDF is already {len(base)} bytes"
    padded = base + b"%" + b" " * max(0, size - len(base) - 2) + b"\n"
    padded = padded[:size] if len(padded) > size else padded + b"%" * (size - len(padded))
    assert len(padded) == size
    # The padding must not have broken the document, otherwise the test would be
    # measuring a parse failure rather than the size gate.
    with fitz.open(stream=padded, filetype="pdf") as check:
        assert check.page_count == 1
    return padded


@pytest.fixture(autouse=True)
def _small_limit(monkeypatch):
    monkeypatch.setenv("FINRISK_MAX_UPLOAD_BYTES", str(LIMIT))
    monkeypatch.delenv("FINRISK_MAX_UPLOAD_MB", raising=False)


@pytest.mark.parametrize("size", [LIMIT - 1, LIMIT])
def test_a_file_at_or_under_the_limit_is_analysed(size):
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "Boundary Co", "fiscal_year": "2025"},
        files={"file": ("boundary.pdf", pdf_of_exact_size(size), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200, f"{size} bytes -> {response.status_code} {response.text[:200]}"


def test_a_file_over_the_limit_is_refused():
    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        data={"company": "Boundary Co", "fiscal_year": "2025"},
        files={"file": ("boundary.pdf", pdf_of_exact_size(LIMIT + 1), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "PDF upload-size limit exceeded"


def test_the_limit_counts_the_file_not_the_encoded_request():
    """A file exactly at the limit still fits inside the multipart envelope."""
    boundary = "----boundary"
    payload = pdf_of_exact_size(LIMIT)
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in (("company", "Boundary Co"), ("fiscal_year", "2025"))
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="boundary.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
        + payload
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    encoded = b"".join(parts)
    # The encoded body is strictly larger than the file — which is exactly why the
    # proxy must not use the file limit as its body ceiling.
    assert len(encoded) > LIMIT

    client, headers = authenticated_client()
    response = client.post(
        "/api/v1/documents/analyze",
        content=encoded,
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 200, response.text[:200]
