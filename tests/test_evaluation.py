import pytest
from finrisk.evaluation import classification_metrics, expected_calibration_error


def test_metric_inputs_are_validated():
    with pytest.raises(ValueError):classification_metrics([1],[1,0])
    with pytest.raises(ValueError):expected_calibration_error([1.2],[True])

def test_ece_boundary_counted_once():
    assert expected_calibration_error([0.5],[True],2)==0.5
