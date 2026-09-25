# E4 Validation Report

## Design

E4 tested the locked FinRisk v0.3.4 commit `4273b070678240fe7cbdf01a17527afcc71c500e` on 2,000 out-of-time, company-disjoint FY2024 SEC filers. Cohort selection and all predictions were frozen before future SEC archives were mounted. The endpoint remained `deterministic_forward_outcome_rule_v1`; all scores remain `UNCALIBRATED` heuristic indices.

## Sample flow

- Eligible before sampling: 3,659
- Frozen E4-A cohort: 2,000
- VERIFIED outcomes: 674
- Events: 235 (34.9%)
- REQUIRES_HUMAN_REVIEW: 571
- INSUFFICIENT_DATA: 755

Performance estimates apply to the deterministically verifiable subset.

## Primary results

B6 AUROC was 0.708, with PR-AUC 0.584. P1 B6–B0 ΔAUROC was +0.030 (95% CI +0.014 to +0.048; Holm-adjusted p=0.0015), meeting the prespecified positive-improvement gate.

P2 H0–B0 was +0.055 (-0.071 to +0.191) and P3 H0–A2 was +0.145 (-0.286 to +0.527). Both had only 5 paired events and remain exploratory; neither improvement was established.

## Local Agent

The benchmark communicated with a locally hosted Agent through an HTTP API. No external hosted inference API was used. The frozen backend was Ollama 0.12.3 / Qwen2.5 0.5B Instruct Q4_K_M / CPU. There were 5 permanent failures across 150 official Agent records. Successful fixed-seed stability repeats were deterministic; single-case versus batch scores differed by 0.101 on average, with 96.6% decision agreement.

## Robustness and integrity

All SEC inputs passed hashes, CRC and archive-member checks. Feature and outcome mounts were physically separated through prediction freeze. Independent concordance included 17,757 values from 1,648 companies; 90.9% agreed within 5%. Metric/raw-fact missingness, sector, threshold, endpoint attrition, Agent failure, stability and batch-context analyses were executed. Deterministic replay was canonical byte-identical.

## Claim boundary

E4 supports a positive paired ranking improvement for B6 over B0 on the verified E4-A subset. It does not establish an Agent or Hybrid improvement, calibrated default probability, universal bankruptcy prediction, production/regulatory fitness, narrative-document grounding, or full FinRisk Agent external validation.
