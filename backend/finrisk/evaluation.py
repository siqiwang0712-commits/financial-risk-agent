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

def balanced_accuracy(y_true:list[int],y_pred:list[int])->float:
    if len(y_true)!=len(y_pred):raise ValueError("inputs must have equal length")
    recalls=[]
    for label in (0,1):
        idx=[i for i,value in enumerate(y_true) if value==label]
        if idx:recalls.append(sum(y_pred[i]==label for i in idx)/len(idx))
    return sum(recalls)/len(recalls) if recalls else 0.0

def brier_score(y_true:list[int],probabilities:list[float])->float:
    if len(y_true)!=len(probabilities):raise ValueError("inputs must have equal length")
    return sum((p-y)**2 for y,p in zip(y_true,probabilities))/len(y_true) if y_true else 0.0

def roc_auc(y_true:list[int],probabilities:list[float])->float|None:
    positives=[p for y,p in zip(y_true,probabilities) if y==1];negatives=[p for y,p in zip(y_true,probabilities) if y==0]
    if not positives or not negatives:return None
    wins=sum(1 if p>n else .5 if p==n else 0 for p in positives for n in negatives)
    return wins/(len(positives)*len(negatives))

def average_precision(y_true:list[int],probabilities:list[float])->float|None:
    if not any(y_true):return None
    ranked=sorted(zip(probabilities,y_true),reverse=True);hits=0;total=0.0
    for rank,(_,label) in enumerate(ranked,1):
        if label:hits+=1;total+=hits/rank
    return total/sum(y_true)

def confusion_matrix(y_true:list[int],y_pred:list[int])->dict[str,int]:
    return {"tn":sum(a==0 and b==0 for a,b in zip(y_true,y_pred)),"fp":sum(a==0 and b==1 for a,b in zip(y_true,y_pred)),"fn":sum(a==1 and b==0 for a,b in zip(y_true,y_pred)),"tp":sum(a==1 and b==1 for a,b in zip(y_true,y_pred))}
