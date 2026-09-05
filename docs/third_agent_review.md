# Third Independent Agent Review

The third read-only audit targeted semantic defects that can survive ordinary test suites.

## Implemented response

- Fixed an Ohlson unit error: the model exposes logistic probability separately from its O-score, and configured scoring uses that probability explicitly.
- Replaced evidence-string inference with explicit rule-family metadata for major correlated liquidity, loss, interest-coverage, and cash-deficit signals. Family aggregation is order-independent and retains the strongest signal.
- Preserved model source references and added model, claim, and contradiction nodes and edges to the evidence graph.
- Removed the unsupported 0.5 narrative-evidence prior. Coverage now separates data availability, numeric provenance, verified claims, model applicability, and temporal depth.
- The PDF endpoint reconstructs a prior-year dictionary from multi-column filings and applies deterministic ranking for restated/main-statement candidates; unresolved top-ranked conflicts remain excluded and visible.
- Added an executable, explicitly synthetic manifest runner for five baselines and two ablations. JSONL outputs are ignored and must never be presented as real benchmark evidence.

## Remaining work

Explicit families should ultimately cover every correlated rule and be validated by domain experts. Full table geometry, cross-page header state, XBRL reconciliation, calibrated coverage, eight-dimension claim ontology, worker isolation, professional linked reports, locked dependency hashes, and a licensed adjudicated benchmark remain pending.
