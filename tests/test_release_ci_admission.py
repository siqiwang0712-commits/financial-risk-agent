from copy import deepcopy

import pytest

from scripts.verify_release_ci import (
    REPOSITORY,
    REQUIRED_JOBS,
    checked_run,
    verify_completed,
)

COMMIT = 'a' * 40
RUN = {'id': 1, 'head_sha': COMMIT, 'event': 'push', 'path': '.github/workflows/ci.yml',
       'head_repository': {'full_name': REPOSITORY}, 'status': 'completed', 'conclusion': 'success'}
JOBS = [{'name': name, 'status': 'completed', 'conclusion': 'success'} for name in REQUIRED_JOBS]


@pytest.mark.parametrize('field,value', [('head_sha', 'b'*40), ('event', 'pull_request'),
                                        ('path', '.github/workflows/other.yml'),
                                        ('head_repository', {'full_name': 'untrusted/fork'})])
def test_unrelated_ci_cannot_admit_release(field, value):
    with pytest.raises(ValueError, match='exact release source'):
        checked_run([{**RUN, field: value}], COMMIT)


@pytest.mark.parametrize('state', ['failure', 'cancelled', 'skipped', None])
def test_old_success_cannot_hide_new_failed_or_pending_ci(state):
    latest = {**RUN, 'id': 2, 'conclusion': state}
    with pytest.raises(ValueError, match='newest source CI'):
        verify_completed(checked_run([RUN, latest], COMMIT), JOBS)


@pytest.mark.parametrize('state', ['failure', 'cancelled', 'skipped', None])
def test_any_non_successful_required_job_blocks_release(state):
    jobs = deepcopy(JOBS)
    jobs[0]['conclusion'] = state
    with pytest.raises(ValueError, match='required CI jobs'):
        verify_completed(RUN, jobs)


@pytest.mark.parametrize('jobs', [JOBS[:-1], JOBS + [JOBS[0]]])
def test_incomplete_or_duplicate_job_inventory_blocks_release(jobs):
    with pytest.raises(ValueError, match='required CI jobs'):
        verify_completed(RUN, jobs)


def test_exact_successful_source_is_admitted():
    verify_completed(checked_run([RUN], COMMIT), JOBS)


def test_actual_release_workflow_requires_ci_before_builds():
    from pathlib import Path

    import yaml
    workflow = yaml.safe_load((Path(__file__).parents[1] / '.github/workflows/container-release.yml').read_text())
    steps = workflow['jobs']['prepare']['steps']
    assert any('scripts/verify_release_ci.py --commit "$(git rev-parse HEAD)"' in step.get('run', '') for step in steps)
    assert workflow['jobs']['prepare']['permissions'] == {'contents': 'read', 'actions': 'read'}
    assert all(workflow['jobs'][job]['needs'] == 'prepare' for job in ('build-api', 'build-web'))
