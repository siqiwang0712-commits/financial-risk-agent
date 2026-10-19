# Outcome-blind primary inference design — not frozen

Authority: current human protocol and machine config. P1=S4–S1, P2=S4–S3;
benefit is comparator error incidence minus S4 incidence, not AUROC improvement.
Let A be automated issuance, D the binary disposition and Y the VERIFIED endpoint.
E=A*I(D != Y). Primary error denominator is the common paired VERIFIED set;
withheld cases remain in that denominator but are never called correct predictions.
Coverage denominator is all eligible paired feature packets, not only known labels.

For each pair estimate mean(E_comparator-E_S4) and mean(A_S4-A_comparator).
Predeclare a positive meaningful error benefit delta, noninferiority margin m and
positive absolute S4 coverage floor c. These remain BLOCKED(E5-P03); historical
ranking data cannot identify a decision-maker's loss or review capacity.
Nulls: error benefit <= delta OR coverage difference <= -m OR S4 coverage <= c.
All required component tests must reject for a primary success (intersection-union).
Use maximum component p-value, then Holm over the two primary comparisons at .05.
The absolute floor must participate in the intersection-union, not merely be
reported after the fact. No test may be executed until these boundaries resolve.

Planned paired-company bootstrap: 20,000 draws with replacement of company IDs,
seed 20261019; preserve every arm and label for each drawn ID. Estimate BCa 95%
intervals using delete-one-company jackknife acceleration. One-sided null-centered
bootstrap p=(1+number of null-centered replicates at least as extreme as observed)
/(B+1). Use the declared safety/coverage boundary for centering, not zero by default.
Undefined acceleration, all-identical data, no issued cases, too few positive/
negative pairs or failed numerical diagnostics mean NOT_ESTIMABLE, no primary claim.
BCa intervals describe uncertainty; Holm-adjusted p-values control the primary
family. The exact implementation and independent calibration of this combined test
remain qualification work before freeze; no historical AUROC test is substituted.

Existing E4-S `e4s_stats.py` paired/BCa and E4-R `e4r_stats.py` mechanics are the
nominated reusable infrastructure, not imported legacy hypotheses. Future adoption
must test Type-I behavior for these bounded paired incidence/coverage estimands;
AUROC calibration is not sufficient. No confirmatory analysis engine is claimed
complete while effects, coverage feasibility and validation remain blocked.

Missing labels are not negative. Report complete-case attrition and full-population
worst-case incident bounds, with selective error only where issued/evaluable N>0.
No post-hoc sensitivity may upgrade a failed primary. Secondary discrimination,
review-budget and evidence metrics stay separately labeled. This plan does not
assert issuer authenticity, source truth, external validation or financial safety.
