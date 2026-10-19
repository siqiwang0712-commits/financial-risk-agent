"""Phase-II safeguards; no synthetic fixture is empirical E5 evidence."""
from copy import deepcopy

import pytest

from research.e5.execution.core import GateError, validate_features

H = 'a' * 64


def packet():
    return {'case_id': 'synthetic-case', 'cik': '0000000001', 'accession': '0000009999-25-000001',
            'filing_timestamp': '2025-01-01T00:00:00Z', 'prediction_cutoff': '2025-01-01T00:00:00Z',
            'schema_hash': H, 'extraction_code_hash': H, 'preprocessing_hash': H,
            'reference_distribution_hash': H, 'features': {'current_ratio': 1.},
            'sources': [{'sha256': H, 'available_at': '2025-01-01T00:00:00Z',
                         'filing_timestamp': '2025-01-01T00:00:00Z', 'accession': '0000009999-25-000001',
                         'cik': '0000000001', 'role': 'INDEX_FILING'}]}


@pytest.mark.parametrize(('key', 'value'), [('accession', '0000009999-25-000002'),
                                           ('cik', '0000000002'), ('role', 'LATEST_COMPANYFACTS'),
                                           ('role', 'PRIOR_PERIOD_FILING')])
def test_source_identity_substitution_is_rejected(key, value):
    p = packet()
    p['sources'][0][key] = value
    with pytest.raises(GateError):
        validate_features(p, schema_hash=H, code_hash=H)


def test_filing_agent_accession_prefix_need_not_equal_issuer_cik():
    validate_features(packet(), schema_hash=H, code_hash=H)


def test_cross_case_accession_source_cannot_be_reused():
    a = packet()
    b = deepcopy(a)
    b['accession'] = '0000009999-25-000003'
    with pytest.raises(GateError):
        validate_features(b, schema_hash=H, code_hash=H)
