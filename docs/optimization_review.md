# Independent Agent Review and Response

An independent read-only Agent reviewed the project after the first public release. This document records the findings so improvements remain auditable rather than silently changing project claims.

## Implemented in the hardening pass

- Connected a size- and magic-byte-validated multipart PDF endpoint to parsing, normalization, assessment, and page-source output.
- Replaced the frontend's illustrative fixed score with a real API workflow, loading/error states, returned dimensions, and rule evidence.
- Added source references to derived metrics and rule signals plus an assessment-level evidence graph.
- Changed unsupported dimensions from an automatic base score to `N/A` with zero coverage.
- Replaced request-dictionary completeness with a fixed core-field matrix and exposed confidence components. Confidence is labelled an uncalibrated coverage score.
- Corrected ROA, ROE, and working-capital days to use average balances when prior-year data exists; single-year calculations disclose their ending-balance proxy.
- Added finite, positive-domain, and denominator protections to traditional models.
- Fixed evaluation length/range validation and ECE boundary double-counting.
- Replaced the incomplete license, productionized the frontend container, updated publication claims, and added API/model/evaluation tests.

## Deliberately still pending

Complex table reconstruction, automatic multi-year column alignment, restatement reconciliation, XBRL cross-checking, OCR, full eight-dimension contradiction ontology, rule-family correlation caps, empirically calibrated confidence, professional linked PDF rendering, and a real adjudicated benchmark remain future work. The upload endpoint therefore returns `review_required: true`.

This distinction is intentional: the project should demonstrate a reliable research architecture without presenting a conservative prototype extractor as a production filing parser.

