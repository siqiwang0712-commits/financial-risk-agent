# Canonical V3 operating-characteristic qualification

Status: **PASSED**, within the frozen finite simulation grid. This is synthetic method qualification, not empirical E5 evidence. V1 and the additional V2 failures remain preserved.

Analysis identity: `1653696313abcc4c52eb6cebd74cdb215e453ae87c588f30c603a6d75738bef9`. Thirteen prespecified configurations, 5,000 trials each, and 20,000 paired company bootstrap draws per trial. Frozen utility margins are unchanged.

| Configuration | N | Largest true-null component rejection rate | Holm true-null family error | Material anti-conservatism |
|---|---:|---:|---:|---|
| global_null | 100 | 0.0000 | 0.0000 | NO |
| error_boundary_independent | 200 | 0.0402 | 0.0048 | NO |
| NI_boundary_nested | 500 | 0.0352 | 0.0192 | NO |
| NI_boundary_discordant | 200 | 0.0466 | 0.0324 | NO |
| absolute_boundary | 500 | 0.0448 | 0.0242 | NO |
| mixed_boundary | 500 | 0.0486 | 0.0000 | NO |
| P1_null_P2_alternative | 500 | 0.0438 | 0.0234 | NO |
| P2_null_P1_alternative | 500 | 0.0420 | 0.0176 | NO |
| high_informative_missingness | 1000 | 0.0406 | 0.0354 | NO |
| packet_and_proposal_attrition | 1000 | 0.0458 | 0.0076 | NO |
| rare_events_nested_NI | 1500 | 0.0428 | 0.0250 | NO |
| small_paired_error_boundary | 100 | 0.0370 | 0.0042 | NO |
| N100_nested_NI_V2_regression | 100 | 0.0298 | 0.0000 | NO |

The predeclared failure criterion is a one-sided 99% exact-binomial lower bound above 0.05 for a true-null component, primary IUT, or Holm family. No configuration meets that failure criterion. This finite grid does not prove uniform error control for every possible population.

BCa intervals resample all arms and observability together at company level. Error tests condition on the common VERIFIED subset; coverage NI uses the paired constrained trinomial null; absolute coverage retains the V2 boundary Bernoulli correction. Undefined tests remain NOT_ESTIMABLE and cannot produce primary success.

The immutable sequential and single-configuration execution partitions are assembled without choosing favorable results. A scheduler-only IndexError and a stopped sequential continuation are retained separately; neither changes the inference kernel or counted trials.
