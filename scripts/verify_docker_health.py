"""Verify the production compose API is ready and uses PostgreSQL persistence."""

from __future__ import annotations

import json
import os
import time
import tomllib
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def verification_base(variable: str, default: str) -> str:
    """Return a loopback-only base URL so test credentials cannot be exfiltrated."""
    value = os.getenv(variable, default).rstrip("/")
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{variable} has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or port is None
    ):
        raise ValueError(f"{variable} must be an explicit loopback HTTP(S) origin")
    return value


def declared_runtime() -> str:
    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    version = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["version"]
    return f"v{version}"


API = verification_base("FINRISK_VERIFY_API", "http://127.0.0.1:8000")
WEB = verification_base("FINRISK_VERIFY_WEB", "http://127.0.0.1:3000")
EXPECTED_READINESS = {"status": "ready", "datastore": "postgres", "schema": "complete"}
EXPECTED_RUNTIME = os.getenv("FINRISK_EXPECTED_RUNTIME", declared_runtime())


def request_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def expect_http_status(request: Request, expected: int) -> HTTPError:
    try:
        with urlopen(request, timeout=10) as response:
            response.read(64 * 1024)
    except HTTPError as exc:
        if exc.code != expected:
            exc.read(64 * 1024)
            exc.close()
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


def assert_readiness(payload: dict) -> None:
    """Reject a healthy-looking API backed by the wrong store or schema."""
    mismatches = {
        name: (expected, payload.get(name))
        for name, expected in EXPECTED_READINESS.items()
        if payload.get(name) != expected
    }
    if mismatches:
        raise RuntimeError(
            f"unexpected readiness payload (expected/actual): {mismatches!r}; "
            f"full payload: {payload!r}"
        )


def main() -> None:
    """Verify the composed production stack end to end.

    Importing this module must not make any request.
    """
    deadline = time.monotonic() + 90
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{API}/health/ready", timeout=3) as response:
                payload = json.load(response)
            assert_readiness(payload)
            with urlopen(f"{WEB}/api/v1/public-pilot", timeout=5) as response:
                frontend_payload = json.load(response)
            if frontend_payload.get("runtime") != EXPECTED_RUNTIME:
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
    organization = request_json(
        f"{API}/api/v1/enterprise/organizations",
        {"name": "Smoke tenant", "actor_id": "smoke-admin"},
        {"X-Bootstrap-Token": bootstrap_token},
    )
    api_key = organization["api_key"]
    headers = {"X-API-Key": api_key}
    entity = request_json(
        f"{WEB}/api/v1/enterprise/entities",
        {"name": "Smoke issuer", "sector": "industrial"},
        headers,
    )
    body, boundary = multipart({"company": "Smoke issuer", "fiscal_year": "2025", "entity_id": entity["id"]}, "smoke.pdf", pdf_with_text("BALANCE SHEET\nCash and cash equivalents 100\nTotal assets 500"))
    analysis_request = Request(
        f"{WEB}/api/v1/documents/analyze",
        data=body,
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
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
        f"{WEB}/api/v1/enterprise/entities",
        data=b'{"name":"Unauthorized"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    expect_http_status(unauthorized, 401)

    invalid_entity = Request(
        f"{WEB}/api/v1/enterprise/entities",
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
        f"{WEB}/api/v1/documents/analyze",
        data=bad_body,
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={bad_boundary}"},
        method="POST",
    )
    expect_http_status(unsupported, 415)

    # The configured ceiling is a *file* size: the API compares the uploaded PDF bytes
    # against it, and the proxy therefore has to tolerate the multipart framing on top
    # of it. A declared body length of `limit + 1` is consequently ambiguous — it may
    # well be a legal file plus framing — so an unambiguous oversized *request body* is
    # used here. The "a file of exactly the limit is accepted, one byte more is not"
    # boundary is covered by tests/test_upload_size_boundary.py against a small limit.
    upload_limit = int(os.getenv("FINRISK_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    oversized = Request(
        f"{WEB}/api/v1/documents/analyze",
        data=b"x",
        headers={
            **headers,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(2 * upload_limit),
        },
        method="POST",
    )
    expect_http_status(oversized, 413)

    rate_limited = False
    for _ in range(70):
        request = Request(
            f"{WEB}/api/v1/enterprise/entities",
            data=b'{"name":""}',
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            # 70 iterations: an unclosed success response leaks a socket each time,
            # so the result is always drained and closed on both paths.
            with urlopen(request, timeout=10) as response:
                response.read(64 * 1024)
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
