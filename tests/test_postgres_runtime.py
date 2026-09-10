import os
from pathlib import Path

import pytest
from finrisk.enterprise.domain import Entity, Organization, Role, new_id
from finrisk.enterprise.postgres import PostgresEnterpriseRepository
from finrisk.enterprise.security import PostgresCredentialStore, issue_api_key

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
    credentials = PostgresCredentialStore(first.connection)
    raw, credential = issue_api_key(organization.id, "admin", Role.ADMIN)
    credentials.register(credential)
    replacement, _ = credentials.rotate(credential.id)
    with pytest.raises(PermissionError):
        credentials.authenticate(raw)
    first.connection.close()

    second = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    assert second.get_entity(organization.id, entity.id).name == "Persistent issuer"
    assert PostgresCredentialStore(second.connection).authenticate(replacement).role is Role.ADMIN
    second.connection.close()
