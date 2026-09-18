"""Verify the production compose API is ready and uses PostgreSQL persistence."""

from __future__ import annotations

import json
import os
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def expect_http_status(request: Request, expected: int) -> HTTPError:
    try:
        urlopen(request, timeout=10)
    except HTTPError as exc:
        if exc.code != expected:
            raise AssertionError(f"expected HTTP {expected}, received {exc.code}") from exc
        exc.read(64 * 1024)
        exc.close()
        return exc
    raise AssertionError(f"expected HTTP {expected}, request succeeded")


def pdf_with_text(text: str) -> bytes:
    """Small standards-compliant PDF for an integration smoke, no host deps."""
    lines = [line.replace("(", "\\(").replace(")", "\\)") for line in text.splitlines()]
    stream = ("BT /F1 11 Tf 72 720 Td " + " ".join(f"({line}) Tj T*" for line in lines) + " ET").encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, item in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{number} 0 obj\n".encode()); output.extend(item); output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def multipart(fields: dict[str, str], filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"----finrisk-{uuid.uuid4().hex}"
    parts = []
    for name, value in fields.items():
        parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), value.encode(), b"\r\n"])
    parts.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(), b"Content-Type: application/pdf\r\n\r\n", content, b"\r\n", f"--{boundary}--\r\n".encode()])
    return b"".join(parts), boundary


def main() -> None:
    """Verify the composed production stack end to end.

    Importing this module must not make any request.
    """
    deadline = time.monotonic() + 90
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen("http://127.0.0.1:8000/health/ready", timeout=3) as response:
                payload = json.load(response)
            if payload.get("status") != "ready":
                raise RuntimeError(f"unexpected readiness status: {payload!r}")
            with urlopen("http://127.0.0.1:3000/api/v1/public-pilot", timeout=5) as response:
                frontend_payload = json.load(response)
            if frontend_payload.get("runtime") != "v0.3.2":
                raise RuntimeError(f"frontend API proxy failed: {frontend_payload!r}")
            print("production compose API is ready")
            break
        except (OSError, URLError, ValueError, RuntimeError) as exc:
            last_error = exc
            time.sleep(2)
    else:
        raise SystemExit(f"production compose readiness failed: {last_error}")

    # Exercise the deployed production path, rather than only liveness and a public
    # frozen artifact: securely provision the first tenant, create its entity, and
    # persist an authenticated document analysis.
    bootstrap_token = os.environ["FINRISK_BOOTSTRAP_TOKEN"]
    organization = request_json("http://127.0.0.1:8000/api/v1/enterprise/organizations", {"name": "Smoke tenant", "actor_id": "smoke-admin"}, {"X-Bootstrap-Token": bootstrap_token})
    api_key = organization["api_key"]
    headers = {"X-API-Key": api_key}
    entity = request_json("http://127.0.0.1:3000/api/v1/enterprise/entities", {"name": "Smoke issuer", "sector": "industrial"}, headers)
    body, boundary = multipart({"company": "Smoke issuer", "fiscal_year": "2025", "entity_id": entity["id"]}, "smoke.pdf", pdf_with_text("BALANCE SHEET\nCash and cash equivalents 100\nTotal assets 500"))
    analysis_request = Request("http://127.0.0.1:3000/api/v1/documents/analyze", data=body, headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urlopen(analysis_request, timeout=90) as response:
        analysis = json.load(response)
    if analysis.get("company") != "Smoke issuer" or not analysis.get("agent", {}).get("trace"):
        raise SystemExit(f"production document workflow returned an invalid contract: {analysis!r}")
    print("production authenticated entity/document workflow passed")

    # Cross-layer failure contracts: these requests enter through the production
    # Next proxy and must preserve the backend status while returning a safe,
    # correlated error response. The rate-limit check is last because a 429 is
    # intentionally absorbing for the remainder of this short smoke run.
    unauthorized = Request(
        "http://127.0.0.1:3000/api/v1/enterprise/entities",
        data=b'{"name":"Unauthorized"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    expect_http_status(unauthorized, 401)

    invalid_entity = Request(
        "http://127.0.0.1:3000/api/v1/enterprise/entities",
        data=b'{"name":""}',
        headers={**headers, "Content-Type": "application/json", "X-Correlation-Id": "smoke-correlation"},
        method="POST",
    )
    validation_error = expect_http_status(invalid_entity, 422)
    if validation_error.headers.get("X-Correlation-Id") != "smoke-correlation":
        raise SystemExit("proxy did not preserve the correlation ID on a 422 response")

    bad_body, bad_boundary = multipart(
        {"company": "Smoke issuer", "fiscal_year": "2025", "entity_id": entity["id"]},
        "not-a-pdf.txt",
        b"not a PDF",
    )
    unsupported = Request(
        "http://127.0.0.1:3000/api/v1/documents/analyze",
        data=bad_body,
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={bad_boundary}"},
        method="POST",
    )
    expect_http_status(unsupported, 415)

    oversized = Request(
        "http://127.0.0.1:3000/api/v1/documents/analyze",
        data=b"x",
        headers={**headers, "Content-Type": "application/octet-stream", "Content-Length": str(50 * 1024 * 1024 + 1)},
        method="POST",
    )
    expect_http_status(oversized, 413)

    rate_limited = False
    for _ in range(70):
        request = Request(
            "http://127.0.0.1:3000/api/v1/enterprise/entities",
            data=b'{"name":""}',
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(request, timeout=10)
        except HTTPError as exc:
            exc.read(64 * 1024)
            exc.close()
            if exc.code == 429:
                rate_limited = True
                break
            if exc.code != 422:
                raise
    if not rate_limited:
        raise SystemExit("production proxy/backend rate limit did not return HTTP 429")
    print("production proxy failure contracts passed (401/413/415/422/429)")


if __name__ == "__main__":
    main()
