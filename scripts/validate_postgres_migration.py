import os
from pathlib import Path

from finrisk.enterprise.postgres import PostgresEnterpriseRepository

root = Path(__file__).resolve().parents[1]
repository = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
repository.migrate(root / "migrations" / "001_enterprise_core.sql")
with repository.connection.cursor() as cursor:
    cursor.execute(
        "SELECT to_regclass('public.analysis_snapshots'), to_regclass('public.audit_events')"
    )
    snapshots, audit = cursor.fetchone()
if not snapshots or not audit:
    raise SystemExit("enterprise migration did not create required tables")
print("PostgreSQL enterprise migration validated")
