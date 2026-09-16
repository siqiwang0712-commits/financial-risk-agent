import os
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
