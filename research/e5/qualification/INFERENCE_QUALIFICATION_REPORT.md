# Inference qualification scope

The new execution engine implements the prespecified comparator-minus-S4 error
incidence on VERIFIED companies, coverage on all paired companies, paired
multinomial company resampling, BCa intervals with delete-one-company acceleration,
null-centered greater-than p-values with plus-one correction, three-component
intersection-union tests using the maximum p-value, and two-primary Holm adjustment.
Undefined inference remains NOT_ESTIMABLE. An undefined primary retains its place
in the multiplicity family; its p-value is not reported as a fabricated one.

Tests cross-check BCa intervals against SciPy on the same bootstrap distribution,
exercise Holm fixtures, missingness denominators, degenerate samples, exact seed
reproduction, and identities preserved within every paired resample.

The null study uses 5,000 Monte Carlo trials per configuration and the production
20,000 bootstrap draws per trial. It includes global null, error-benefit,
coverage-NI, absolute-coverage and mixed boundaries, N=100/200/500, and independent
missingness of 0%/25%. Each configuration is content-addressed and resumable.
The exact results and source hashes are in `type1_simulation_report.json` when the
run has completed; an incomplete run never implies a successful gate.

**This is limited engineering qualification, not the complete mandate's statistical
qualification.** In particular, the simulation duplicates the two comparator
configurations, testing perfect dependence rather than a broad P1/P2 dependence
grid. It varies sufficient error/issuance statistics rather than running the
required event-prevalence and informative-observability scenarios. A complete
joint IUT+Holm power study, final N and the complete required operating-characteristic
grid remain unfinished. No E5 protocol/inference freeze or confirmatory p-values
are authorized by this limited study. The source hash identifies the engine that
was actually tested, without claiming that it is a complete qualified analysis.

## Recorded failure and pre-outcome V2 correction

The complete V1 grid returned **FAILED_ANTI_CONSERVATISM**. In the mixed-boundary
configuration, the absolute component rejected in 296/5,000 trials (0.0592), with
one-sided 99% exact-binomial lower bound 0.0516873. V1 is not qualified.

`v2/AMENDMENT.json` preserves that failed identity and introduces a separately
identified boundary-Bernoulli absolute-coverage null. The unchanged paired empirical
bootstrap still supplies BCa intervals and the error/NI components. For absolute
coverage, the boundary distribution is fully specified by c; binomial compression
of the extreme-replicate count preserves the 20,000-draw plus-one Monte Carlo test.

The V2 absolute component passed its stated screen in 21 configurations and
105,000 synthetic trials. See `v2/absolute_coverage_null_report.json`. This does not
qualify the whole V2 IUT+Holm pipeline, its full dependence grid or joint power.
No E5 outcome was accessed; no scientific protocol identity was inherited.
