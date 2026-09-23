"""Verify production proxy timeout and explicit retry contracts."""

from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from finrisk.verification_http import (
    VerificationEndpoints,
    multipart,
    pdf_with_text,
    request_json,
    wait_for_readiness,
)

ENDPOINTS = VerificationEndpoints.from_env()
API = ENDPOINTS.api
WEB = ENDPOINTS.web


def main() -> None:
    """Verify the production proxy timeout and explicit retry contract.

    Importing this module must not make any request.
    """
    try:
        wait_for_readiness(API, timeout=60, interval=1)
    except TimeoutError as exc:
        raise SystemExit("timeout-smoke API readiness failed") from exc

    # The web proxy is recreated by the same `docker compose up --force-recreate` as
    # the API, but every request below goes through it on :3000. Waiting only for the
    # API left a window in which Next.js had not bound its port yet, so the proxy
    # answered with a transport-level reset instead of an HTTP status. Waiting for the
    # proxy as well removes the race without weakening any assertion.
    proxy_deadline = time.monotonic() + 60
    while time.monotonic() < proxy_deadline:
        try:
            with urlopen(f"{WEB}/", timeout=3) as response:
                if response.status == 200:
                    break
        except (OSError, URLError, ValueError):
            time.sleep(1)
    else:
        raise SystemExit("timeout-smoke web proxy readiness failed")

    organization = request_json(
        f"{API}/api/v1/enterprise/organizations",
        {"name": "Timeout tenant", "actor_id": "timeout-admin"},
        {"X-Bootstrap-Token": os.environ["FINRISK_BOOTSTRAP_TOKEN"]},
    )
    headers = {"X-API-Key": organization["api_key"]}
    entity = request_json(
        f"{WEB}/api/v1/enterprise/entities",
        {"name": "Timeout issuer"},
        headers,
    )
    body, boundary = multipart(
        {"company": "Timeout issuer", "fiscal_year": "2025", "entity_id": entity["id"]},
        "timeout.pdf",
        pdf_with_text("BALANCE SHEET\nCash and cash equivalents 100\nTotal assets 500"),
        boundary_prefix="----finrisk-timeout",
    )

    for attempt in (1, 2):
        correlation_id = f"timeout-retry-{attempt}"
        request = Request(
            f"{WEB}/api/v1/documents/analyze",
            data=body,
            headers={
                **headers,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Correlation-Id": correlation_id,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                response.read(64 * 1024)
        except HTTPError as exc:
            payload = json.load(exc)
            response_correlation = exc.headers.get("X-Correlation-Id")
            exc.close()
            if exc.code != 504 or response_correlation != correlation_id:
                raise SystemExit(
                    f"timeout attempt {attempt} returned HTTP {exc.code}, correlation={response_correlation!r}"
                )
            if "timed out" not in str(payload.get("detail", "")).lower():
                raise SystemExit(f"timeout attempt {attempt} returned unsafe contract: {payload!r}")
        else:
            raise SystemExit(f"timeout attempt {attempt} unexpectedly succeeded")

    print("production proxy timeout and explicit retry contracts passed (504 x2)")


if __name__ == "__main__":
    main()
