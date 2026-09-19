"""`<NAME>_FILE` secret injection: precedence, fallback and failure behaviour.

Round 7 added the `*_FILE` form so secrets can be mounted instead of exported (the
process environment is readable through `docker inspect` and inherited by every child
process). The helper was never exercised, though, and its failure behaviour is the
part that matters: a *silently* ignored file means the protection is off (an unread
bootstrap token) or the wrong database is used while the service still reports
healthy. These tests pin precedence, fallback and the loud-failure cases, and check
that no secret material reaches the message.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from finrisk.api import _env_or_file
from finrisk.enterprise.api import enterprise_router

SECRET = "s3cret-mounted-value"
OTHER = "value-from-the-environment"


def test_the_file_wins_over_the_environment(tmp_path, monkeypatch):
    mounted = tmp_path / "token"
    mounted.write_text(SECRET + "\n", encoding="utf-8")
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN", OTHER)
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN_FILE", str(mounted))
    # Trailing newline from `echo`/a mounted secret must not become part of the value.
    assert _env_or_file("FINRISK_BOOTSTRAP_TOKEN") == SECRET


def test_the_environment_is_used_when_no_file_is_configured(monkeypatch):
    monkeypatch.delenv("FINRISK_BOOTSTRAP_TOKEN_FILE", raising=False)
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN", OTHER)
    assert _env_or_file("FINRISK_BOOTSTRAP_TOKEN") == OTHER


def test_an_empty_file_falls_back_to_the_environment(tmp_path, monkeypatch):
    """An empty mount is how a missing secret usually presents itself."""
    mounted = tmp_path / "empty"
    mounted.write_text("   \n", encoding="utf-8")
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN", OTHER)
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN_FILE", str(mounted))
    assert _env_or_file("FINRISK_BOOTSTRAP_TOKEN") == OTHER


def test_neither_source_configured_is_none(monkeypatch):
    monkeypatch.delenv("FINRISK_BOOTSTRAP_TOKEN_FILE", raising=False)
    monkeypatch.delenv("FINRISK_BOOTSTRAP_TOKEN", raising=False)
    assert _env_or_file("FINRISK_BOOTSTRAP_TOKEN") is None


def test_a_missing_file_fails_loudly_instead_of_falling_back(tmp_path, monkeypatch):
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN", OTHER)
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN_FILE", str(tmp_path / "absent"))
    with pytest.raises(RuntimeError) as failure:
        _env_or_file("FINRISK_BOOTSTRAP_TOKEN")
    message = str(failure.value)
    # Actionable, and it must not leak the value it would otherwise have used.
    assert "FINRISK_BOOTSTRAP_TOKEN_FILE" in message
    assert OTHER not in message


def test_an_unreadable_file_fails_loudly(tmp_path, monkeypatch):
    """A directory is unreadable as a file on every platform; no chmod needed."""
    monkeypatch.setenv("DATABASE_URL_FILE", str(tmp_path))
    with pytest.raises(RuntimeError) as failure:
        _env_or_file("DATABASE_URL")
    assert "DATABASE_URL_FILE" in str(failure.value)


def test_a_token_loaded_from_a_file_still_gates_the_bootstrap_route(tmp_path, monkeypatch):
    """The file form must feed the real gate, not just the helper."""
    mounted = tmp_path / "bootstrap-token"
    mounted.write_text(SECRET, encoding="utf-8")
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN_FILE", str(mounted))
    monkeypatch.setenv("FINRISK_BOOTSTRAP_TOKEN", OTHER)

    router = enterprise_router(
        require_bootstrap_token=True,
        bootstrap_token=_env_or_file("FINRISK_BOOTSTRAP_TOKEN"),
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    assert client.post(
        "/api/v1/enterprise/organizations", json={"name": "No token", "actor_id": "a"}
    ).status_code == 403
    assert client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Env value", "actor_id": "a"},
        headers={"X-Bootstrap-Token": OTHER},
    ).status_code == 403
    assert client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Mounted value", "actor_id": "a"},
        headers={"X-Bootstrap-Token": SECRET},
    ).status_code == 200


def test_the_migration_job_resolves_the_secret_the_same_way(tmp_path, monkeypatch):
    """The migration job gates every production deploy.

    It used to read `os.environ["DATABASE_URL"]` directly, so an operator who
    mounted the DSN as a file got an API using the file and a migration using a
    stale environment value — the deploy gate then failed with a pool timeout
    that named neither cause.
    """
    import importlib.util
    from contextlib import contextmanager
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "scripts" / "validate_postgres_migration.py"
    spec = importlib.util.spec_from_file_location("validate_postgres_migration", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.env_or_file is _env_or_file

    mounted = tmp_path / "database_url"
    mounted.write_text("postgresql://finrisk:from-the-file@db:5432/finrisk\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL_FILE", str(mounted))
    monkeypatch.setenv("DATABASE_URL", "postgresql://finrisk:stale-env@db:5432/finrisk")

    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def execute(self, sql):
            captured["sql"] = sql

        def fetchone(self):
            return ("ok",) * 5

    @contextmanager
    def fake_connection(*args, **kwargs):
        class FakeConnection:
            def cursor(self):
                return FakeCursor()

        yield FakeConnection()

    class FakeRepository:
        def migrate(self, path):
            captured.setdefault("migrations", []).append(Path(path).name)

        connection_context = staticmethod(fake_connection)

        def close(self):
            captured["closed"] = True

    seen: dict[str, str] = {}

    def remember(dsn):
        seen["dsn"] = dsn
        return FakeRepository()

    monkeypatch.setattr(module.PostgresEnterpriseRepository, "connect",
                        classmethod(lambda cls, dsn: remember(dsn)))
    module.main()

    assert seen["dsn"] == "postgresql://finrisk:from-the-file@db:5432/finrisk", seen
    expected = len(list((source.parents[1] / "migrations").glob("*.sql"))) * 2
    assert len(captured["migrations"]) == expected, captured["migrations"]
    assert captured["closed"] is True
