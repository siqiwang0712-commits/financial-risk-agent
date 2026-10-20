"""Runtime boundary regressions; fixtures here are never empirical E5 evidence."""
import pytest
from finrisk.assurance.policy import AssurancePolicy

from research.e5.execution.core import GateError
from research.e5.phase2.study import evidence_only_decision


def test_partial_material_verification_never_authorizes_s3_even_above_point_four():
    verified = {'reason_code': 'FIRST', 'source_evidence': [{'id': 'source-1'}], 'evidence_path_status': 'VERIFIED'}
    unverified = {'reason_code': 'SECOND', 'source_evidence': [], 'evidence_path_status': 'UNVERIFIED'}
    assert evidence_only_decision('PASS', [verified, unverified], AssurancePolicy()) == 'REVIEW'
    assert evidence_only_decision('PASS', [verified], AssurancePolicy()) == 'PASS'
    assert evidence_only_decision('ABSTAIN', [verified, unverified], AssurancePolicy()) == 'ABSTAIN'


def test_outcome_acquisition_cannot_make_a_request_before_real_unlock(tmp_path, monkeypatch):
    from pathlib import Path

    from research.e5.phase2.acquire_outcomes import acquire
    def forbidden(*args, **kwargs):
        raise AssertionError('future data requested before protocol/prediction/unlock')
    monkeypatch.setattr('research.e5.phase2.acquire_outcomes.download', forbidden)
    with pytest.raises(GateError):
        acquire(Path(__file__).resolve().parents[1], tmp_path, ['2026q3'])
    assert not (tmp_path/'outcome-inputs').exists()
