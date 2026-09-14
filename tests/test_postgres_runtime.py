import os
from pathlib import Path

import pytest
from finrisk.enterprise.domain import (
    Entity,
    Organization,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
    Role,
    new_id,
)
from finrisk.enterprise.postgres import PostgresEnterpriseRepository
from finrisk.enterprise.security import PostgresCredentialStore, issue_api_key
from finrisk.enterprise.temporal import RiskSnapshot

ROOT = Path(__file__).resolve().parents[1]

requires_postgres = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="PostgreSQL integration requires DATABASE_URL",
)


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
    repository.connection.close()


@requires_postgres
def test_postgres_case_transition_is_compare_and_set():
    """`save_case_transition` must be atomic against a concurrent writer.

    `transition` reads a case, validates the state machine, mutates and saves.
    With an unconditional `ON CONFLICT ... DO UPDATE`, two reviewers acting on the
    same case both succeeded and the loser silently discarded the winner - and
    with it the state machine, because the loser had validated against a status
    that no longer existed. The `UPDATE ... WHERE status = expected` predicate is
    what closes that window, so it is asserted here against a real PostgreSQL.
    """
    repository = PostgresEnterpriseRepository.connect(os.environ["DATABASE_URL"])
    for migration in sorted((ROOT / "migrations").glob("*.sql")):
        repository.migrate(migration)
    organization = Organization(new_id("org"), "Case CAS test")
    entity = Entity(new_id("ent"), organization.id, "Issuer")
    repository.save(organization)
    repository.save(entity)
    case = RiskCase(
        new_id("case"),
        organization.id,
        entity.id,
        RiskDomain.LIQUIDITY,
        "high",
        "stable",
        0.8,
        0.7,
        status=RiskCaseStatus.OPEN,
    )
    repository.save(case)

    # Two readers of the same version.
    first = repository.get_case(organization.id, case.id)
    second = repository.get_case(organization.id, case.id)

    second.status = RiskCaseStatus.UNDER_REVIEW
    repository.save_case_transition(second, RiskCaseStatus.OPEN)
    assert (
        repository.get_case(organization.id, case.id).status
        is RiskCaseStatus.UNDER_REVIEW
    )

    # The first reader's write is based on a status that no longer exists.
    first.status = RiskCaseStatus.MITIGATING
    with pytest.raises(ValueError, match="changed concurrently"):
        repository.save_case_transition(first, RiskCaseStatus.OPEN)
    # The rejected write must not have landed, and must not have re-inserted the
    # row or left the connection in a broken transaction.
    assert repository.get_case(organization.id, case.id).status is RiskCaseStatus.UNDER_REVIEW
    assert repository.get_case(organization.id, case.id).id == case.id
    repository.connection.close()
