import pytest
from finrisk.evaluation import (
    average_precision,
    balanced_accuracy,
    brier_score,
    classification_metrics,
    confusion_matrix,
    expected_calibration_error,
    roc_auc,
)


def test_metric_inputs_are_validated():
    with pytest.raises(ValueError):classification_metrics([1],[1,0])
    with pytest.raises(ValueError):expected_calibration_error([1.2],[True])

def test_ece_boundary_counted_once():
    assert expected_calibration_error([0.5],[True],2)==0.5

def test_extended_binary_metrics():
    truth=[0,0,1,1];prediction=[0,1,0,1];probabilities=[.1,.8,.4,.9]
    assert balanced_accuracy(truth,prediction)==.5
    assert brier_score(truth,probabilities)==pytest.approx(.255)
    assert roc_auc(truth,probabilities)==.75
    assert average_precision(truth,probabilities)==pytest.approx(5/6)
    assert confusion_matrix(truth,prediction)=={"tn":1,"fp":1,"fn":1,"tp":1}
