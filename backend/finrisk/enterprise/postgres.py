from __future__ import annotations

import json
from pathlib import Path


class PostgresEnterpriseRepository:
    """Small psycopg adapter. Deployment validation requires an external PostgreSQL instance."""

    def __init__(self, connection):
        self.connection = connection

    @classmethod
    def connect(cls, dsn: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "install the 'postgres' extra to use PostgreSQL"
            ) from exc
        return cls(psycopg.connect(dsn))

    def migrate(self, path: Path) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(path.read_text(encoding="utf-8"))
        self.connection.commit()

    def append_audit_event(self, event) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO audit_events (id, organization_id, actor_id, action, object_type, object_id, payload, occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                (
                    event.id,
                    event.organization_id,
                    event.actor_id,
                    event.action,
                    event.object_type,
                    event.object_id,
                    json.dumps(event.payload),
                    event.occurred_at,
                ),
            )
        self.connection.commit()
