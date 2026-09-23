"""Verify the production compose API is ready and uses PostgreSQL persistence."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from finrisk.verification_http import (
    VerificationEndpoints,
    declared_runtime,
    expect_http_status,
    multipart,
    pdf_with_text,
    request_json,
    wait_for_json_object,
    wait_for_readiness,
)

ENDPOINTS = VerificationEndpoints.from_env()
API = ENDPOINTS.api
WEB = ENDPOINTS.web
EXPECTED_RUNTIME = os.getenv("FINRISK_EXPECTED_RUNTIME", declared_runtime())


def assert_frontend_runtime(payload: dict) -> None:
    if payload.get("runtime") != EXPECTED_RUNTIME:
        raise RuntimeError(f"frontend API proxy failed: {payload!r}")


def main() -> None:
    """Verify the composed production stack end to end.

    Importing this module must not make any request.
    """
    try:
        wait_for_readiness(API, timeout=90)
        wait_for_json_object(
            f"{WEB}/api/v1/public-pilot",
            timeout=90,
            label="frontend proxy",
            request_timeout=5,
            validator=assert_frontend_runtime,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        raise SystemExit(f"production compose readiness failed: {exc}") from exc
    print("production compose API is ready")

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
