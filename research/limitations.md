# Limitations

The executed public pilot has only three same-sector companies, one positive risk label and a single annotator. Its point estimates and bootstrap intervals cannot support generalization or a claim that the hybrid approach outperforms alternatives. The LLM-only pilot used the deterministic offline provider; the real provider has not been run without an intentionally supplied API key.

SEC Company Facts acquisition returned HTTP 403 in the recorded environment. XBRL normalization, provenance, restatement selection and cross-source reconciliation are implemented and unit tested, but public-pilot extraction accuracy is not yet empirically measured. The frozen observations are reviewed statement values, not a substitute for an independently annotated XBRL gold set.

The consistency engine uses transparent category thresholds and requires two numeric conflicts (except explicit going-concern doubt). It still loses semantic context—for example, a liquidity claim may include marketable securities or committed facilities that a cash/current-ratio test does not represent.

PDF layouts, scanned documents, XBRL differences, restatements, and ambiguous accounting labels can reduce extraction quality. Sector-specific accounting makes generic ratios and Altman/Beneish/Ohlson/Piotroski models inappropriate in some cases, especially financial institutions. Expert weights are transparent but not statistically optimal. Narrative extraction can miss context even when its quote is genuine. Page-level matching proves provenance, not truth. Scores are decision-support signals—not bankruptcy probabilities, fraud findings, credit ratings, or investment advice.
