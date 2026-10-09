from copy import deepcopy

import pytest

from scripts.verify_candidate_image import verify_metadata

IMAGE = {'Config': {'User': 'finrisk', 'Labels': {
    'org.opencontainers.image.version': '0.4.2', 'org.opencontainers.image.revision': 'a'*40}}}


@pytest.mark.parametrize('field,value', [('version', '0.4.1'), ('revision', 'b'*40),
                                        ('version', None), ('revision', None)])
def test_substituted_or_unlabelled_source_is_rejected(field, value):
    image = deepcopy(IMAGE)
    image['Config']['Labels']['org.opencontainers.image.'+field] = value
    with pytest.raises(ValueError, match='identity mismatch'):
        verify_metadata(image, 'v0.4.2', 'a'*40)


@pytest.mark.parametrize('user', [None, '', 'root', '0', '0:0', 'root:finrisk', '0:finrisk', '00'])
def test_privileged_runtime_is_rejected(user):
    image = deepcopy(IMAGE)
    image['Config']['User'] = user
    with pytest.raises(ValueError, match='unprivileged'):
        verify_metadata(image, '0.4.2', 'a'*40)


def test_exact_candidate_metadata_is_accepted():
    verify_metadata(IMAGE, 'v0.4.2', 'a'*40)
