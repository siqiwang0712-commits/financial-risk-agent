from pathlib import Path

from finrisk.enterprise.postgres import PostgresEnterpriseRepository
from finrisk.secret_files import env_or_file


def main() -> None:
    """Run every migration and assert the enterprise tables exist.

    Importing this module must not connect to a database or run migrations.
    """
    root = Path(__file__).resolve().parents[1]
    # A bare KeyError told a contributor nothing about what to set; the gate still
    # fails when the variable is absent. The mounted-file form must be honoured
    # too: this job is what gates a production deploy, so it has to resolve the
    # secret exactly the way the API process does.
    dsn = env_or_file("DATABASE_URL")
    if not dsn:
        raise SystemExit(
            "DATABASE_URL (or DATABASE_URL_FILE) is not set; this check needs a PostgreSQL instance"
        )
    repository = PostgresEnterpriseRepository.connect(dsn)
    for migration in sorted((root / "migrations").glob("*.sql")):
        repository.migrate(migration)
    with repository.connection_context() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('public.analysis_snapshots'), "
            "to_regclass('public.audit_events'), "
            "to_regclass('public.risk_snapshots'), "
            "to_regclass('public.decision_bundles'), "
            "to_regclass('public.rate_limit_events')"
        )
        snapshots, audit, risk_snapshots, bundles, rate_limit = cursor.fetchone()
    # Migrations are idempotent, so a second pass must be a no-op rather than an
    # error: the prod overlay runs this on every deploy.
    for migration in sorted((root / "migrations").glob("*.sql")):
        repository.migrate(migration)
    repository.close()
    if not all((snapshots, audit, risk_snapshots, bundles, rate_limit)):
        raise SystemExit("enterprise migration did not create required tables")
    print("PostgreSQL enterprise migration validated (idempotent on re-run)")


if __name__ == "__main__":
    main()
