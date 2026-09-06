import os
from pathlib import Path

from finrisk.enterprise.postgres import PostgresEnterpriseRepository

root = Path(__file__).resolve().parents[1]
repository = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
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
