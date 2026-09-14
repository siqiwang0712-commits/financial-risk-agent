"""Apply the enterprise migrations to `DATABASE_URL` and assert the tables exist.

Run explicitly. Importing this module used to read `os.environ["DATABASE_URL"]`
at import time and raise `KeyError` on any machine that had not exported it,
which made the module impossible to import for inspection.
"""

from __future__ import annotations

import os
from pathlib import Path

from finrisk.enterprise.postgres import PostgresEnterpriseRepository


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    repository = PostgresEnterpriseRepository.connect(database_url)
    for migration in sorted((root / "migrations").glob("*.sql")):
        repository.migrate(migration)
    with repository.connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('public.analysis_snapshots'), "
            "to_regclass('public.audit_events'), "
            "to_regclass('public.risk_snapshots'), "
            "to_regclass('public.decision_bundles')"
        )
        snapshots, audit, risk_snapshots, bundles = cursor.fetchone()
    if not all((snapshots, audit, risk_snapshots, bundles)):
        raise SystemExit("enterprise migration did not create required tables")
    print("PostgreSQL enterprise migration validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
