from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClassificationMetrics:
    precision:float; recall:float; f1:float

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
    if bins<1 or any(c<0 or c>1 for c in confidences):raise ValueError("invalid confidence or bins")
    if not confidences:return 0
    total=0
    for i in range(bins):
        idx=[j for j,c in enumerate(confidences) if i/bins<=c<(i+1)/bins or (i==bins-1 and c==1)]
        if idx:total+=len(idx)/len(confidences)*abs(sum(confidences[j] for j in idx)/len(idx)-sum(correct[j] for j in idx)/len(idx))
    return total
