# E5 Calibration Plan

Calibration is optional and must be isolated from final validation.

- Reserve company- and time-disjoint development, calibration, and validation
  partitions before labels are opened.
- Fit a single prespecified calibration family on the calibration partition;
  candidate selection cannot inspect final-validation labels.
- Freeze clipping, regularization, binning, missing-score treatment, and
  abstention policy before validation.
- Report calibration-in-the-large, slope, Brier score, ECE with frozen bins,
  reliability diagram, coverage, and uncertainty on untouched validation data.
- Preserve ranking metrics separately from calibration metrics.
- If sample size or event count is inadequate, do not fit calibration and keep
  the score `UNCALIBRATED`.
- Never describe an unvalidated heuristic or Agent score as probability of
  default, bankruptcy, insolvency, or credit loss.
