"""Original filing repetitions may resolve only under declared precision consistency."""
from copy import deepcopy
from pathlib import Path

from research.e5.execution.core import read_json
from research.e5.phase2.live_source import resolve_precision


def fixture_rows():
    root = Path(__file__).resolve().parents[1]
    proof = read_json(root/'research/e5/phase2/qualification/original-instance-v1-precision-diagnostics.json')
    return deepcopy(proof['live_bundle']['evidence']['provenance']['current__total_assets']['conflicting_rows'])


def test_real_same_context_rounding_is_order_independent_and_preserves_precise_value():
    rows = fixture_rows()
    for values in (rows, rows[::-1]):
        selected, resolutions = resolve_precision(values)
        assert len(selected) == 1 and selected[0]['value'] == '12118553000'
        assert len(resolutions) == 1
        assert resolutions[0]['all_rows'] == values


def test_inconsistent_rounding_remains_a_conflict():
    rows = fixture_rows()
    rows[1]['value'] = '15000000000'
    selected, resolutions = resolve_precision(rows)
    assert selected == rows and not resolutions


def test_equal_precision_disagreement_and_missing_precision_remain_conflicts():
    for declaration in ('-3', None):
        rows = fixture_rows()
        rows[1]['decimals'] = declaration
        selected, resolutions = resolve_precision(rows)
        assert selected == rows and not resolutions


def test_different_contexts_are_never_collapsed():
    rows = fixture_rows()
    rows[1]['context_id'] += '-other-period-or-entity'
    selected, resolutions = resolve_precision(rows)
    assert selected == rows and not resolutions
