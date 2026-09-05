# Evaluation Protocol

Create a versioned manifest of public annual reports and licenses, then double-annotate financial values, source pages, narrative claims, and contradictions. Adjudicate disagreements blind to system output. Split by company and time.

Metrics: exact/tolerance extraction accuracy; evidence precision; unsupported claim and hallucination rates; macro-F1/AUROC only when valid outcome labels exist; contradiction precision/recall/F1; Brier score and expected calibration error; coverage; and latency. Report bootstrap confidence intervals and per-sector slices. Compare all five baselines on the identical corpus and prompts. Synthetic fixtures test mechanics only and are labelled `synthetic`; they are not evidence of real-world performance.

