import os
import time
from pathlib import Path

import pytest
from finrisk.enterprise.domain import (
    AuditEvent,
    Entity,
    Organization,
    RiskCase,
    RiskDomain,
    Role,
    new_id,
)
from finrisk.enterprise.postgres import PostgresEnterpriseRepository
from finrisk.enterprise.security import PostgresCredentialStore, issue_api_key
from finrisk.enterprise.temporal import RiskSnapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_postgres_runtime_survives_repository_restart_and_rotates_credentials():
    first = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    for migration in sorted((ROOT / "migrations").glob("*.sql")):
        first.migrate(migration)
    organization = Organization(new_id("org"), "Restart persistence test")
    entity = Entity(new_id("ent"), organization.id, "Persistent issuer")
    first.save(organization)
    first.save(entity)
    credentials = PostgresCredentialStore(first)
    raw, credential = issue_api_key(organization.id, "admin", Role.ADMIN)
    credentials.register(credential)
    replacement, _ = credentials.rotate(credential.id)
    with pytest.raises(PermissionError):
        credentials.authenticate(raw)
    first.close()

    second = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    assert second.get_entity(organization.id, entity.id).name == "Persistent issuer"
    assert PostgresCredentialStore(second).authenticate(replacement).role is Role.ADMIN
    second.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_postgres_duplicate_risk_snapshot_rolls_back_as_domain_error():
    repository = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    for migration in sorted((ROOT / "migrations").glob("*.sql")):
        repository.migrate(migration)
    organization = Organization(new_id("org"), "Duplicate snapshot test")
    entity = Entity(new_id("ent"), organization.id, "Issuer")
    repository.save(organization)
    repository.save(entity)
    snapshot = RiskSnapshot(entity.id, "2024", "filing", 50, {}, {}, {}, "REVIEW", 0.5)
    repository.save_risk_snapshot(organization.id, snapshot)
    with pytest.raises(ValueError, match="already exists"):
        repository.save_risk_snapshot(organization.id, snapshot)
    assert repository.get_entity(organization.id, entity.id).id == entity.id
    repository.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_postgres_mutation_audit_atomicity_and_optimistic_locking():
    repository = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    for migration in sorted((ROOT / "migrations").glob("*.sql")):
        repository.migrate(migration)
    organization = Organization(new_id("org"), "Concurrency test")
    entity = Entity(new_id("ent"), organization.id, "Atomic issuer")
    repository.save(organization)

    event_id = new_id("audit")
    repository.append_event(
        AuditEvent(event_id, organization.id, "actor", "seed", "entity", entity.id, {})
    )
    duplicate_event = AuditEvent(
        event_id, organization.id, "actor", "create", "entity", entity.id, {}
    )
    with pytest.raises(Exception) as atomicity_error:
        repository.save(entity, duplicate_event)
    assert atomicity_error.value.__class__.__name__ == "UniqueViolation"
    with pytest.raises(KeyError):
        repository.get_entity(organization.id, entity.id)

    repository.save(entity)
    case = RiskCase(
        new_id("case"), organization.id, entity.id, RiskDomain.LIQUIDITY,
        "high", "stable", 0.5, 0.5,
    )
    repository.save(case)
    first = repository.get_case(organization.id, case.id)
    stale = repository.get_case(organization.id, case.id)
    assert repository.save(first).version == 1
    with pytest.raises(ValueError, match="concurrent"):
        repository.save(stale)
    assert repository.get_case(organization.id, case.id).version == 1
    repository.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_migrations_create_every_required_table_and_are_idempotent():
    """The migration gate used to be a substring check on the SQL text.

    That proves the file mentions a table name; it proves nothing about whether the
    statements run, in order, twice. This executes them against a real server.
    """
    repository = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    migrations = sorted((ROOT / "migrations").glob("*.sql"))
    assert migrations, "no migrations found"
    for migration in migrations:
        repository.migrate(migration)
    # Re-running every migration must be a no-op: the production overlay runs this
    # on every deploy.
    for migration in migrations:
        repository.migrate(migration)
    with repository.connection_context() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        tables = {row[0] for row in cursor.fetchall()}
    repository.close()
    expected = {
        "organizations", "entities", "policy_versions", "risk_cases", "analysis_snapshots",
        "audit_events", "risk_snapshots", "decision_bundles", "api_credentials",
        "model_registry", "rate_limit_events",
    }
    assert expected <= tables, f"missing tables: {sorted(expected - tables)}"


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_shared_rate_limiter_is_enforced_across_connections():
    """The bootstrap limiter must hold for a *new* client, not just this process."""
    from finrisk.enterprise.security import PostgresRateLimiter

    first = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    for migration in sorted((ROOT / "migrations").glob("*.sql")):
        first.migrate(migration)
    scope_key = f"bootstrap:{new_id('probe')}"
    limiter = PostgresRateLimiter(first, limit=3, window_seconds=900)
    assert [limiter.allow(scope_key) for _ in range(3)] == [True, True, True]
    assert limiter.allow(scope_key) is False
    first.close()

    # A different connection (i.e. another worker or a restarted process) must see the
    # same window; the in-process fallback would start from zero here.
    second = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    assert PostgresRateLimiter(second, limit=3, window_seconds=900).allow(scope_key) is False
    second.close()


def _migrated_repository() -> PostgresEnterpriseRepository:
    repository = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    for migration in sorted((ROOT / "migrations").glob("*.sql")):
        repository.migrate(migration)
    return repository


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_shared_rate_limiter_drains_its_window_instead_of_latching():
    """After the window passes, the key must be admitted again.

    The first implementation used one data-modifying CTE for prune+count+insert;
    PostgreSQL evaluates every part of a statement against the same snapshot, so the
    count still saw the rows the DELETE had just removed and the key stayed blocked
    for as long as traffic continued.
    """
    from finrisk.enterprise.security import PostgresRateLimiter

    repository = _migrated_repository()
    key = f"bootstrap:{new_id('drain')}"
    limiter = PostgresRateLimiter(repository, limit=2, window_seconds=1)
    assert [limiter.allow(key) for _ in range(3)] == [True, True, False]
    time.sleep(1.5)
    assert limiter.allow(key) is True
    repository.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_shared_rate_limiter_sweeps_expired_rows_belonging_to_other_keys():
    """A flood of one-shot keys must not accumulate forever.

    The per-key prune only ever removed the rows of the key being checked, so an
    attacker rotating the key (the bootstrap limiter keys on the client address) left
    one stale row set per key behind.
    """
    from finrisk.enterprise.security import PostgresRateLimiter

    repository = _migrated_repository()
    stale_keys = [f"round8-stale:{new_id('k')}" for _ in range(25)]
    with repository.connection_context() as connection, connection.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO rate_limit_events (scope, key, occurred_at)
               VALUES ('api', %s, now() - interval '2 hours')""",
            [(key,) for key in stale_keys],
        )
        connection.commit()
        cursor.execute(
            "SELECT count(*) FROM rate_limit_events WHERE key = ANY(%s)", (stale_keys,)
        )
        assert cursor.fetchone()[0] == len(stale_keys)

    limiter = PostgresRateLimiter(repository, limit=5, window_seconds=60)
    assert limiter.allow(f"bootstrap:{new_id('fresh')}") is True

    with repository.connection_context() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM rate_limit_events WHERE key = ANY(%s)", (stale_keys,)
        )
        assert cursor.fetchone()[0] == 0, "expired rows for untouched keys must be swept"
    repository.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_shared_rate_limiter_keeps_the_table_bounded_by_its_row_cap():
    from finrisk.enterprise.security import PostgresRateLimiter

    repository = _migrated_repository()
    prefix = f"round8-cap-{new_id('c')}-"
    keys = [f"{prefix}{index}" for index in range(120)]
    with repository.connection_context() as connection, connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO rate_limit_events (scope, key) VALUES ('api', %s)",
            [(key,) for key in keys],
        )
        connection.commit()

    limiter = PostgresRateLimiter(repository, limit=5, window_seconds=60, max_rows=40)
    limiter.allow(f"bootstrap:{new_id('fresh')}")

    with repository.connection_context() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM rate_limit_events")
        total = cursor.fetchone()[0]
        # The sweep trims to the cap, and this request then records its own admission,
        # so the retained count is bounded by the cap plus the rows admitted since the
        # sweep — one per concurrent request, one here.
        assert total <= 41, f"row cap not enforced: {total} rows retained"
        cursor.execute("DELETE FROM rate_limit_events WHERE key LIKE %s", (f"{prefix}%",))
        connection.commit()
    repository.close()


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_shared_rate_limiter_fails_closed_when_the_store_is_unavailable():
    """An admission decision that cannot be made must not be an admission.

    The limiter is the only bound on the unauthenticated bootstrap route. Letting the
    driver error escape produced an unhandled 500; treating it as "allowed" would have
    silently removed the limit for the duration of the outage. It must be a distinct,
    catchable failure so the API can answer a controlled 503.
    """
    from finrisk.enterprise.security import PostgresRateLimiter, RateLimiterUnavailable

    repository = _migrated_repository()
    repository.close()
    limiter = PostgresRateLimiter(repository, limit=5, window_seconds=60)
    with pytest.raises(RateLimiterUnavailable):
        limiter.allow(f"bootstrap:{new_id('down')}")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PostgreSQL integration requires DATABASE_URL")
def test_shared_rate_limiter_recovers_when_the_store_comes_back():
    from finrisk.enterprise.security import PostgresRateLimiter

    down = _migrated_repository()
    down.close()
    from finrisk.enterprise.security import RateLimiterUnavailable

    with pytest.raises(RateLimiterUnavailable):
        PostgresRateLimiter(down, limit=5, window_seconds=60).allow(f"bootstrap:{new_id('x')}")

    # A fresh connection (a restarted worker, or a database that came back) works again
    # with no cached failure state.
    recovered = _migrated_repository()
    assert PostgresRateLimiter(recovered, limit=5, window_seconds=60).allow(
        f"bootstrap:{new_id('y')}"
    ) is True
    recovered.close()
