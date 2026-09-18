import os
from pathlib import Path

from finrisk.enterprise.postgres import PostgresEnterpriseRepository


def main() -> None:
    """Run every migration and assert the enterprise tables exist.

    Importing this module must not connect to a database or run migrations.
    """
    root = Path(__file__).resolve().parents[1]
    # A bare KeyError told a contributor nothing about what to set; the gate still
    # fails when the variable is absent.
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is not set; this check needs a PostgreSQL instance")
    repository = PostgresEnterpriseRepository.connect(dsn)
    for migration in sorted((root / "migrations").glob("*.sql")):
        repository.migrate(migration)
    with repository.connection_context() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('public.analysis_snapshots'), "
            "to_regclass('public.audit_events'), "
            "to_regclass('public.risk_snapshots'), "
            "to_regclass('public.decision_bundles')"
        )
        snapshots, audit, risk_snapshots, bundles = cursor.fetchone()
    repository.close()
    if not all((snapshots, audit, risk_snapshots, bundles)):
        raise SystemExit("enterprise migration did not create required tables")
    print("PostgreSQL enterprise migration validated")


if __name__ == "__main__":
    main()
