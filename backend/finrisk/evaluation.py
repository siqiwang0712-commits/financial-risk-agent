from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ClassificationMetrics:
    precision:float; recall:float; f1:float


def _validate_binary(values: list[int], name: str) -> None:
    if any(value not in (0, 1) for value in values):
        raise ValueError(f"{name} must be binary")


def _validate_probabilities(values: list[float]) -> None:
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in values
    ):
        raise ValueError("probabilities must be finite and within [0, 1]")

def classification_metrics(y_true:list[int],y_pred:list[int])->ClassificationMetrics:
    if len(y_true)!=len(y_pred):raise ValueError("inputs must have equal length")
    if any(x not in (0,1) for x in y_true+y_pred):raise ValueError("labels must be binary")
    tp=sum(a==b==1 for a,b in zip(y_true,y_pred));fp=sum(a==0 and b==1 for a,b in zip(y_true,y_pred));fn=sum(a==1 and b==0 for a,b in zip(y_true,y_pred))
    p=tp/(tp+fp) if tp+fp else 0;r=tp/(tp+fn) if tp+fn else 0;f=2*p*r/(p+r) if p+r else 0
    return ClassificationMetrics(p,r,f)

def unsupported_claim_rate(claims:list[dict])->float:
    return sum(not c.get("evidence_verified",False) for c in claims)/len(claims) if claims else 0

def expected_calibration_error(confidences:list[float],correct:list[bool],bins=10)->float:
    if len(confidences)!=len(correct):raise ValueError("inputs must have equal length")
    if bins<1:raise ValueError("invalid confidence or bins")
    _validate_probabilities(confidences)
    if any(not isinstance(item, bool) for item in correct):raise ValueError("correct must contain booleans")
    if not confidences:return 0
    total=0
    for i in range(bins):
        idx=[j for j,c in enumerate(confidences) if i/bins<=c<(i+1)/bins or (i==bins-1 and c==1)]
        if idx:total+=len(idx)/len(confidences)*abs(sum(confidences[j] for j in idx)/len(idx)-sum(correct[j] for j in idx)/len(idx))
    return total

def balanced_accuracy(y_true:list[int],y_pred:list[int])->float:
    if len(y_true)!=len(y_pred):raise ValueError("inputs must have equal length")
    _validate_binary(y_true, "labels")
    _validate_binary(y_pred, "predictions")
    recalls=[]
    for label in (0,1):
        idx=[i for i,value in enumerate(y_true) if value==label]
        if idx:recalls.append(sum(y_pred[i]==label for i in idx)/len(idx))
    return sum(recalls)/len(recalls) if recalls else 0.0

def brier_score(y_true:list[int],probabilities:list[float])->float:
    if len(y_true)!=len(probabilities):raise ValueError("inputs must have equal length")
    _validate_binary(y_true, "labels")
    _validate_probabilities(probabilities)
    return sum((p-y)**2 for y,p in zip(y_true,probabilities))/len(y_true) if y_true else 0.0

def roc_auc(y_true:list[int],probabilities:list[float])->float|None:
    # Every other metric in this module validates its inputs. Without this,
    # `zip` silently truncated to the shorter list and returned a number computed
    # from a subset of the data - a wrong answer presented as a valid one.
    if len(y_true)!=len(probabilities):raise ValueError("inputs must have equal length")
    _validate_binary(y_true, "labels")
    _validate_probabilities(probabilities)
    positives=[p for y,p in zip(y_true,probabilities) if y==1];negatives=[p for y,p in zip(y_true,probabilities) if y==0]
    if not positives or not negatives:return None
    wins=sum(1 if p>n else .5 if p==n else 0 for p in positives for n in negatives)
    return wins/(len(positives)*len(negatives))

def average_precision(y_true:list[int],probabilities:list[float])->float|None:
    if len(y_true)!=len(probabilities):raise ValueError("inputs must have equal length")
    _validate_binary(y_true, "labels")
    _validate_probabilities(probabilities)
    positives=sum(y_true)
    if not positives:return None
    # Tied scores are handled as a single group. The previous implementation used
    # `sorted(zip(probabilities, y_true), reverse=True)`, so a tuple comparison broke
    # ties by *label* descending and pulled the positive verdict to rank 1. A
    # constant-score baseline with zero discriminative power therefore reported
    # AUPRC = 1.0 (a perfect score). Grouping makes the metric order-independent
    # among equal scores.
    groups: dict[float, list[int]] = {}
    for probability, label in zip(probabilities, y_true):
        entry = groups.setdefault(probability, [0, 0])
        entry[0] += 1
        entry[1] += int(label)
    cumulative_tp = 0
    cumulative_total = 0
    total = 0.0
    for probability in sorted(groups, reverse=True):
        size, group_positives = groups[probability]
        cumulative_tp += group_positives
        cumulative_total += size
        precision = cumulative_tp / cumulative_total
        total += (group_positives / positives) * precision
    return total

def confusion_matrix(y_true:list[int],y_pred:list[int])->dict[str,int]:
    # Same truncation hazard as `roc_auc`: a shorter `y_pred` produced a matrix
    # whose cells summed to fewer rows than were passed in, with no indication.
    if len(y_true)!=len(y_pred):raise ValueError("inputs must have equal length")
    if any(x not in (0,1) for x in y_true+y_pred):raise ValueError("labels must be binary")
    return {"tn":sum(a==0 and b==0 for a,b in zip(y_true,y_pred)),"fp":sum(a==0 and b==1 for a,b in zip(y_true,y_pred)),"fn":sum(a==1 and b==0 for a,b in zip(y_true,y_pred)),"tp":sum(a==1 and b==1 for a,b in zip(y_true,y_pred))}
