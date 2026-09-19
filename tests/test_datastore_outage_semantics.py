"""A datastore outage must be a controlled 503, never an unhandled 500.

Fail-closed is the right posture — an admission decision that cannot be made is not an
admission — but the *shape* of the failure matters too. Round 6 found that a driver
error escaped the request boundary as `500 internal server error` plus a traceback,
which is indistinguishable from a defect and tells a load balancer nothing. These
tests pin the classification and both boundaries that can hit it: the rate limiter and
the credential store.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
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


def _repository_that_cannot_reach_its_pool(monkeypatch, *, credential_rejected: bool):
    """A PostgreSQL repository whose readiness probe fails for a known reason."""
    from finrisk.enterprise.postgres import PostgresEnterpriseRepository

    repository = PostgresEnterpriseRepository(dsn="postgresql://finrisk:secret@db:5432/finrisk")

    def broken_probe():
        raise RuntimeError("couldn't get a connection after 30.00 sec")

    monkeypatch.setattr(repository, "check_ready", broken_probe)
    monkeypatch.setattr(repository, "credentials_rejected", lambda: credential_rejected)
    monkeypatch.setattr(api, "enterprise_service", SimpleNamespace(repository=repository))
    return repository


def test_readiness_names_a_rejected_credential(monkeypatch):
    """A rotated password must be reported as such, not as an outage.

    The connection pool raises only a bare `PoolTimeout` when every attempt
    fails, so the driver's real reason never reached this branch and the
    operator was told "database readiness check failed" — the same answer a
    genuine outage produces, for a problem with a completely different fix.
    """
    _repository_that_cannot_reach_its_pool(monkeypatch, credential_rejected=True)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert "rejected the configured credentials" in response.json()["detail"]


def test_readiness_keeps_the_generic_outage_answer_when_the_credential_is_fine(monkeypatch):
    """The credential answer must not swallow a plain unavailability."""
    _repository_that_cannot_reach_its_pool(monkeypatch, credential_rejected=False)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "database readiness check failed"


def test_credentials_rejected_reads_the_servers_own_answer(monkeypatch):
    """Only an authentication refusal counts; every other failure is an outage."""
    psycopg = pytest.importorskip("psycopg")
    from finrisk.enterprise.postgres import PostgresEnterpriseRepository

    repository = PostgresEnterpriseRepository(dsn="postgresql://finrisk:secret@db:5432/finrisk")

    def authentication_failure(*args, **kwargs):
        raise psycopg.OperationalError(
            'connection to server at "db", port 5432 failed: FATAL: '
            'password authentication failed for user "finrisk"'
        )

    def refused(*args, **kwargs):
        raise psycopg.OperationalError('connection to server at "db", port 5432 failed: Connection refused')

    monkeypatch.setattr(psycopg, "connect", authentication_failure)
    assert repository.credentials_rejected() is True
    monkeypatch.setattr(psycopg, "connect", refused)
    assert repository.credentials_rejected() is False
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: nullcontext())
    assert repository.credentials_rejected() is False
    # No DSN means no way to ask, so the caller keeps its original answer.
    assert PostgresEnterpriseRepository().credentials_rejected() is False


def test_a_misconfigured_probe_timeout_is_not_reported_as_an_outage(monkeypatch):
    """A typo in the timeout knob must not make readiness call a healthy database down.

    The knob feeds the same `try` as the probe itself, so a `ValueError` from
    `float("5s")` was indistinguishable from the database being unreachable: readiness
    answered 503 about a database that was fine, and orchestrators restart instances
    on the strength of that answer.
    """
    from finrisk.enterprise.postgres import PostgresEnterpriseRepository

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *excursion):
            return False

        def execute(self, query):
            return None

        def fetchone(self):
            return (1,)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    repository = PostgresEnterpriseRepository(connection=FakeConnection())
    for broken in ("not-a-number", "", "5s", "-1", "0"):
        monkeypatch.setenv("FINRISK_READY_PROBE_TIMEOUT_SECONDS", broken)
        assert repository.check_ready() is True, broken


def test_credentials_rejected_answers_rather_than_raising_without_the_driver(monkeypatch):
    """This probe runs *inside* a failure path, so it must not add one of its own.

    `import psycopg` is deferred so the module stays importable without the driver.
    Left unguarded it would escape into the readiness handler's own `except` block,
    and an environment without the driver would turn a diagnosable 503 into an
    opaque 500 — the exact confusion this endpoint exists to remove.
    """
    from finrisk.enterprise.postgres import PostgresEnterpriseRepository

    monkeypatch.setitem(sys.modules, "psycopg", None)
    repository = PostgresEnterpriseRepository(dsn="postgresql://finrisk:secret@db:5432/finrisk")
    assert repository.credentials_rejected() is False


def _postgres_repository_with_schema(*, missing=(), probe_error=None):
    """A PostgreSQL repository whose readiness probe and schema lookup are stubbed."""
    from finrisk.enterprise.postgres import PostgresEnterpriseRepository

    repository = PostgresEnterpriseRepository(
        dsn="postgresql://finrisk:secret@db:5432/finrisk"
    )

    def check_ready():
        if probe_error is not None:
            raise probe_error
        return True

    monkeypatched = {"missing": missing, "probe_error": probe_error}
    repository.check_ready = check_ready  # type: ignore[method-assign]
    repository.credentials_rejected = lambda: False  # type: ignore[method-assign]
    repository.missing_schema_objects = lambda: tuple(monkeypatched["missing"])  # type: ignore[method-assign]
    monkeypatch_target = api
    return repository, monkeypatch_target


def test_readiness_refuses_a_reachable_but_unmigrated_database(monkeypatch):
    """`SELECT 1` succeeding used to be the whole answer.

    An API pointed at a database that was up, empty and never migrated reported
    `ready` while every business request failed. Reachability and schema are two
    different facts, and a deployment gate needs both.
    """
    from finrisk.enterprise.postgres import REQUIRED_SCHEMA_OBJECTS

    repository, _ = _postgres_repository_with_schema(missing=REQUIRED_SCHEMA_OBJECTS)
    monkeypatch.setattr(api, "enterprise_service", SimpleNamespace(repository=repository))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "not migrated" in detail
    assert "organizations" in detail
    # The detail is operator-facing: it names objects, never the DSN.
    assert "secret" not in detail and "db:5432" not in detail
    # Every readiness 503 carries a backoff hint, so a load balancer does not
    # hammer a database that is down or not yet migrated.
    assert response.headers["Retry-After"] == "5"


def test_readiness_refuses_a_partially_migrated_database(monkeypatch):
    """One missing object is enough — a half-applied migration set is not ready."""
    repository, _ = _postgres_repository_with_schema(missing=("rate_limit_events",))
    monkeypatch.setattr(api, "enterprise_service", SimpleNamespace(repository=repository))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert "rate_limit_events" in response.json()["detail"]


def test_readiness_reports_a_complete_schema(monkeypatch):
    """A migrated PostgreSQL database is ready, and says its schema is complete."""
    repository, _ = _postgres_repository_with_schema()
    monkeypatch.setattr(api, "enterprise_service", SimpleNamespace(repository=repository))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "datastore": "postgres", "schema": "complete"}


def test_a_schema_lookup_that_cannot_run_is_an_outage_not_a_500(monkeypatch):
    """Inspecting the schema needs a connection; failing to get one is an outage."""
    repository, _ = _postgres_repository_with_schema(
        probe_error=RuntimeError("couldn't get a connection")
    )
    monkeypatch.setattr(api, "enterprise_service", SimpleNamespace(repository=repository))
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/health/ready").status_code == 503


def test_missing_schema_objects_reads_one_row_of_regclass_lookups():
    """`to_regclass` resolves a missing name to NULL, so absence is data, not an error."""
    from finrisk.enterprise.postgres import (
        REQUIRED_SCHEMA_OBJECTS,
        PostgresEnterpriseRepository,
    )

    class FakeCursor:
        def __init__(self, row):
            self.row = row
            self.query = None

        def __enter__(self):
            return self

        def __exit__(self, *excursion):
            return False

        def execute(self, query, params=None):
            self.query = (query, params)

        def fetchone(self):
            return self.row

    class FakeConnection:
        def __init__(self, row):
            self.row = row
            self.cursor_obj = FakeCursor(row)

        def cursor(self):
            return self.cursor_obj

    present = ("regclass",) * len(REQUIRED_SCHEMA_OBJECTS)
    complete_conn = FakeConnection(present)
    repository = PostgresEnterpriseRepository(connection=complete_conn)
    assert repository.missing_schema_objects() == ()

    partial = ("regclass",) * (len(REQUIRED_SCHEMA_OBJECTS) - 1) + (None,)
    partial_conn = FakeConnection(partial)
    repository = PostgresEnterpriseRepository(connection=partial_conn)
    assert repository.missing_schema_objects() == (REQUIRED_SCHEMA_OBJECTS[-1],)

    # One round trip, whatever the number of required objects: every name is
    # resolved inside a single SELECT rather than probed one by one.
    query, params = partial_conn.cursor_obj.query
    assert query.count("to_regclass") == len(REQUIRED_SCHEMA_OBJECTS)
    assert params == [f"public.{name}" for name in REQUIRED_SCHEMA_OBJECTS]


class _RecordingPool:
    """Records the acquisition timeout the repository asks the pool for."""

    def __init__(self):
        self.seen: list[float | None] = []

    @contextmanager
    def connection(self, timeout=None):
        self.seen.append(timeout)
        yield object()


def test_connection_acquisition_is_bounded_by_default(monkeypatch):
    """An outage must fail in seconds, not after the pool's own 30 s default.

    Unbounded, every in-flight request waited the full window and piled up behind
    each other, which is how a short database blip became a request queue.
    """
    from finrisk.enterprise.postgres import (
        _OPERATION_TIMEOUT_DEFAULT,
        PostgresEnterpriseRepository,
    )

    monkeypatch.delenv("FINRISK_DATABASE_OPERATION_TIMEOUT_SECONDS", raising=False)
    pool = _RecordingPool()
    repository = PostgresEnterpriseRepository(pool=pool)
    with repository.connection_context():
        pass
    assert pool.seen == [_OPERATION_TIMEOUT_DEFAULT]


def test_the_operation_timeout_knob_falls_back_rather_than_crashing(monkeypatch):
    """`0`, negatives, `5s` and NaN must not hang requests or kill the process."""
    from finrisk.enterprise.postgres import (
        _OPERATION_TIMEOUT_DEFAULT,
        PostgresEnterpriseRepository,
        _operation_timeout_seconds,
    )

    for broken in ("not-a-number", "", "5s", "-1", "0", "nan", None):
        if broken is None:
            monkeypatch.delenv("FINRISK_DATABASE_OPERATION_TIMEOUT_SECONDS", raising=False)
        else:
            monkeypatch.setenv("FINRISK_DATABASE_OPERATION_TIMEOUT_SECONDS", broken)
        assert _operation_timeout_seconds() == _OPERATION_TIMEOUT_DEFAULT, broken
        pool = _RecordingPool()
        with PostgresEnterpriseRepository(pool=pool).connection_context():
            pass
        assert pool.seen[-1] == _OPERATION_TIMEOUT_DEFAULT

    monkeypatch.setenv("FINRISK_DATABASE_OPERATION_TIMEOUT_SECONDS", "2.5")
    assert _operation_timeout_seconds() == 2.5


def test_an_explicit_timeout_still_wins(monkeypatch):
    """The readiness probe keeps its own knob; the default must not override it."""
    from finrisk.enterprise.postgres import PostgresEnterpriseRepository

    pool = _RecordingPool()
    with PostgresEnterpriseRepository(pool=pool).connection_context(timeout=1.25):
        pass
    assert pool.seen == [1.25]


def test_the_pool_reconnects_on_a_short_window_not_a_five_minute_one(monkeypatch):
    """A failed reconnection chain must not own the pool for minutes.

    Measured against a stopped container: with the library's 300 s window, a burst
    of concurrent requests during the outage pushed the next retry out to +127 s,
    so readiness stayed red for two minutes after the database was already healthy.
    The chain blocks every fresh attempt while it runs, so the window is the knob
    that decides how fast an instance rejoins the fleet.
    """
    from finrisk.enterprise.postgres import (
        _CONNECT_TIMEOUT_DEFAULT,
        _RECONNECT_TIMEOUT_DEFAULT,
        PostgresEnterpriseRepository,
        _connect_timeout_seconds,
        _reconnect_timeout_seconds,
    )

    psycopg_pool = pytest.importorskip("psycopg_pool")
    seen: dict[str, object] = {}

    class RecordingPool:
        def __init__(self, dsn, **kwargs):
            seen.update(kwargs)

        def wait(self, timeout=0):
            return None

        def close(self):
            pass

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", RecordingPool)
    monkeypatch.delenv("FINRISK_DB_RECONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("FINRISK_DB_CONNECT_TIMEOUT_SECONDS", raising=False)
    PostgresEnterpriseRepository.connect("postgresql://u:p@localhost:5432/db")
    assert seen["reconnect_timeout"] == _RECONNECT_TIMEOUT_DEFAULT
    assert _RECONNECT_TIMEOUT_DEFAULT <= 30.0
    # The handshake itself is bounded too: a dropped-packets peer is never
    # refused, and an unbounded attempt holds a pool worker for minutes.
    assert seen["kwargs"]["connect_timeout"] == _CONNECT_TIMEOUT_DEFAULT
    assert _CONNECT_TIMEOUT_DEFAULT <= 30

    for broken in ("not-a-number", "", "5s", "-1", "0", None):
        if broken is None:
            monkeypatch.delenv("FINRISK_DB_RECONNECT_TIMEOUT_SECONDS", raising=False)
        else:
            monkeypatch.setenv("FINRISK_DB_RECONNECT_TIMEOUT_SECONDS", broken)
        assert _reconnect_timeout_seconds() == _RECONNECT_TIMEOUT_DEFAULT, broken

    monkeypatch.setenv("FINRISK_DB_RECONNECT_TIMEOUT_SECONDS", "12.5")
    assert _reconnect_timeout_seconds() == 12.5

    for broken in ("not-a-number", "", "5s", "-1", "0", None):
        if broken is None:
            monkeypatch.delenv("FINRISK_DB_CONNECT_TIMEOUT_SECONDS", raising=False)
        else:
            monkeypatch.setenv("FINRISK_DB_CONNECT_TIMEOUT_SECONDS", broken)
        assert _connect_timeout_seconds() == _CONNECT_TIMEOUT_DEFAULT, broken

    monkeypatch.setenv("FINRISK_DB_CONNECT_TIMEOUT_SECONDS", "3")
    assert _connect_timeout_seconds() == 3
