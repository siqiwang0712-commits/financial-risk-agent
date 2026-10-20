# Original filing source and exact clock amendment — before E5 exposure

The common method core remains byte-identical. Raw producer, fitted models,
calibrator, review thresholds, Assurance policy, utility margins and canonical
inference are unchanged. No E5 cohort, prediction or outcome exists.

The SEC submissions API acceptance clock failed comparison with the original
EDGAR index. FSDS acceptance timestamps round to minutes. Both retrospective
index inputs and future endpoint filings now use the original EDGAR index's
second-resolution Eastern timestamp converted to UTC. Original API/FSDS values
are retained as provenance, never silently offset or substituted.

Accession-filtered CompanyFacts failed financial equivalence and is rejected;
its exact implementation and qualification failure are preserved. Prospective
inputs instead use the original accession's extracted XBRL instance, with entity,
annual duration, reporting period, consolidated context, taxonomy and unit checks.
Same-context rounded repetitions resolve only when one unique most precise
value's entire declared rounding interval lies inside all duplicate intervals.
True conflicts stay unavailable. Neither averaging nor outcome-dependent choice
is allowed. Precision diagnostics and adversarial regression tests are retained.

Strict equality of every FSDS and original-instance feature **failed** and is
permanent evidence (`original-instance-v1-*`, `original-instance-v2-*`). AVNET's
45 fields agree after legitimate precision resolution. MSFT additionally has
annual current/prior `Depreciation` values (22.0bn / 15.2bn USD) in its original
instance; the immutable FSDS `num.txt` contains no such concept for that accession.
The complete diagnostic alias query returned zero rows. This is a difference in
source coverage; it is not a contradiction between observed financial values.

V3 therefore qualifies a different, explicit source contract: every historical
FSDS feature must replay exactly; every commonly observed value must agree;
an additional original-instance value needs its exact accession-bound, hashed
US-GAAP source row and cannot override a conflicting archive fact. No observed
archive value may disappear. The earlier all-field-equality test remains failed.
This is a declared pre-E5 source contract amendment, not a claim that it passed.
Retrospective features retain FSDS observability; prospective features retain
valid original-instance observability. These studies are reported separately,
with no pooled R/P primary inference. Differential missingness and calibration
transport remain limitations; these two excluded engineering fixtures do not
establish external predictive validity.

All S0, once-only shared proposal, and evidence-routing/Assurance computations
run inside an immutable Docker image with no network, read-only root, no host
volumes, no credentials and dropped capabilities. Source re-extraction belongs
to the source steward; outcome acquisition is a later, separately gated stage.
Real qualification on the two already-excluded issuers is engineering evidence
only. No independent human review or E5 empirical effect is claimed.
