# Second Independent Agent Review

The second read-only Agent focused on residual systemic risk after the first hardening pass.

## Implemented response

- Correlated single-metric threshold rules are de-duplicated by category and metric, retaining the strongest delta; cross-metric interaction rules remain independent.
- Traditional-model risk mappings are now explicit in `config/model_scoring.json` and enter the same auditable signal stream as expert rules.
- Overall score and level become N/A when fewer than two dimensions have evidence.
- Evidence is represented as typed nodes and directed edges from located values through metrics/signals/dimensions to overall assessment. Parser-located values are no longer falsely marked verified.
- Upload extraction retains conflicting candidates as review issues and excludes ambiguous values from scoring.
- A bounded two/three-column parser now recognizes nearby year headings, scale, currency, statement context, and restated headings. It remains a conservative prototype, not a full table engine.
- Negated going-concern language is rejected by the offline provider; only accepted structured claim polarity maps to risk facts.
- Upload work moves PDF parsing off the async event loop, caps size and pages, standardizes damaged-PDF errors, and retains temporary-file cleanup.
- Reports expose confidence components and source document/page/status for rule evidence.

## Still pending by design

Rule-family metadata and learned de-correlation, complete model-to-source edges, bounding-box provenance, full table geometry, XBRL reconciliation, OCR, modality/temporality and all-dimension contradiction matrices, task queues/rate limits/authentication, linked professional PDF layout, locked dependency hashes, and executable five-baseline benchmark orchestration require a later production/research phase.

