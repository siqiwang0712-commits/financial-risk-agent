"""A valid sibling certificate must not replace the requested ledger record."""
import os
from pathlib import Path

import pytest
from finrisk.enterprise.decision_bundle import build_decision_bundle
from finrisk.enterprise.domain import Entity, Organization, new_id
from finrisk.enterprise.postgres import PostgresEnterpriseRepository
from finrisk.enterprise.repository import InMemoryEnterpriseRepository
from test_assurance_runtime import REFERENCE, calibrated_engine, input_for, path


def certificates(repository):
    org = Organization(new_id('org'), 'Binding test')
    entity = Entity(new_id('ent'), org.id, 'Synthetic issuer')
    repository.save(org)
    repository.save(entity)
    engine = calibrated_engine()
    bundles = []
    for names in (('a', 'b'), ('c', 'd')):
        paths = [path(name) for name in names]
        result = engine.evaluate(input_for(*paths, reference=REFERENCE))
        bundles.append(build_decision_bundle(org.id, entity.id, {}, {}, {}, {}, paths, {}, [], {},
                                             result.final_decision, assurance=result.to_dict(), assurance_policy=engine.policy))
    return bundles


def test_memory_rejects_sibling_certificate_under_another_id():
    repository = InMemoryEnterpriseRepository()
    first, sibling = certificates(repository)
    repository.save_decision_bundle(first)
    repository.decision_bundles[first.bundle_id] = sibling
    with pytest.raises(ValueError, match='verification failed'):
        repository.get_decision_bundle(first.organization_id, first.entity_id, first.bundle_id)


@pytest.mark.skipif(not os.getenv('DATABASE_URL'), reason='real PostgreSQL required')
@pytest.mark.parametrize('corruption', ['sibling_payload', 'column_hash'])
def test_postgres_rejects_corrupted_ledger_binding_after_reconnect(corruption):
    from psycopg.types.json import Jsonb
    repository = PostgresEnterpriseRepository.connect(os.environ['DATABASE_URL'])
    try:
        for migration in sorted((Path(__file__).parents[1] / 'migrations').glob('*.sql')):
            repository.migrate(migration)
        first, sibling = certificates(repository)
        repository.save_decision_bundle(first)
        with repository.connection_context() as connection:
            with connection.cursor() as cursor:
                if corruption == 'sibling_payload':
                    cursor.execute('UPDATE decision_bundles SET payload=%s WHERE id=%s', (Jsonb(sibling.to_dict()), first.bundle_id))
                else:
                    cursor.execute('UPDATE decision_bundles SET bundle_hash=%s WHERE id=%s', ('0'*64, first.bundle_id))
            connection.commit()
    finally:
        repository.close()
    repository = PostgresEnterpriseRepository.connect(os.environ['DATABASE_URL'])
    try:
        with pytest.raises(ValueError, match='verification failed'):
            repository.get_decision_bundle(first.organization_id, first.entity_id, first.bundle_id)
    finally:
        repository.close()
