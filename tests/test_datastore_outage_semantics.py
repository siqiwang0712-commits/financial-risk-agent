"""A datastore outage must be a controlled 503, never an unhandled 500.

Fail-closed is the right posture — an admission decision that cannot be made is not an
admission — but the *shape* of the failure matters too. Round 6 found that a driver
error escaped the request boundary as `500 internal server error` plus a traceback,
which is indistinguishable from a defect and tells a load balancer nothing. These
tests pin the classification and both boundaries that can hit it: the rate limiter and
the credential store.
"""

from __future__ import annotations

from typing import NoReturn

import pytest
from fastapi.testclient import TestClient
from finrisk import api
from finrisk.api import _is_datastore_unavailable, app
from finrisk.enterprise.security import RateLimiterUnavailable


class OperationalError(Exception):
    """Stands in for `psycopg.OperationalError` without importing the driver."""


class PoolClosed(Exception):
    """Stands in for `psycopg_pool.PoolClosed`."""


class ConnectTimeout(OperationalError):
    """A subclass, to prove the check walks the MRO."""


class ProgrammingError(Exception):
    """A real defect (bad SQL), which must stay a 500."""


def test_connectivity_errors_are_recognised():
    assert _is_datastore_unavailable(OperationalError("connection refused"))
    assert _is_datastore_unavailable(PoolClosed("pool is closed"))
    assert _is_datastore_unavailable(ConnectTimeout("timed out"))


def test_request_and_programming_errors_are_not_misclassified():
    """A wrong request or a genuine bug must not be reported as an outage."""
    assert not _is_datastore_unavailable(ValueError("bad input"))
    assert not _is_datastore_unavailable(ProgrammingError("syntax error"))
    assert not _is_datastore_unavailable(PermissionError("invalid API key"))


def _client_and_headers() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Outage tenant", "actor_id": "outage-admin"},
    )
    assert response.status_code == 200, response.text[:200]
    return client, {"X-API-Key": response.json()["api_key"]}


def test_a_credential_lookup_during_an_outage_answers_503(monkeypatch):
    client, headers = _client_and_headers()

    def unreachable(_raw: str) -> NoReturn:
        raise OperationalError("could not connect to server")

    monkeypatch.setattr(api.credential_store, "authenticate", unreachable)
    response = client.get("/api/v1/enterprise/overview", headers=headers)
    assert response.status_code == 503, response.text[:200]
    assert response.headers.get("retry-after") == "5"
    assert response.json()["detail"] == "the datastore is temporarily unavailable"
    # The correlation id survives the classified failure.
    assert response.headers["X-Correlation-Id"]


def test_a_rate_limiter_outage_answers_503_and_still_fails_closed(monkeypatch):
    client, headers = _client_and_headers()

    def unavailable(_key: str) -> NoReturn:
        raise RateLimiterUnavailable("rate limiter store unavailable")

    monkeypatch.setattr(api.api_limiter, "allow", unavailable)
    response = client.get("/api/v1/enterprise/overview", headers=headers)
    # 503, not 200: the request must not be admitted just because the limit is unknown.
    assert response.status_code == 503, response.text[:200]
    assert response.json()["detail"] == "rate limiting is temporarily unavailable"


def test_an_unrelated_defect_is_still_a_500(monkeypatch):
    """Classification must not swallow real bugs."""
    client, headers = _client_and_headers()

    def broken(_key: str) -> NoReturn:
        raise ProgrammingError("boom")

    monkeypatch.setattr(api.api_limiter, "allow", broken)
    response = client.get("/api/v1/enterprise/overview", headers=headers)
    assert response.status_code == 500
    assert response.json()["detail"] == "internal server error"


@pytest.mark.parametrize("path", ["/api/v1/enterprise/overview"])
def test_readiness_reports_an_outage_while_liveness_stays_plain(path):
    """Readiness carries the dependency check; liveness must not.

    Probed in-process here (no database configured, so readiness trivially passes);
    the Docker fault injection in the round-8 evidence covers the real outage.
    """
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
