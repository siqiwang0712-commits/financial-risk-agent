# Examples and sample reports — v0.4.2

- `synthetic_company.json` is an explicitly synthetic engineering fixture.
- `human_study_synthetic.csv` illustrates the study-analysis format; it is not a
  completed participant study.
- `intel_2024_sample_report.txt` and `.pdf` are checked-in demonstration reports
  based on the public pilot inputs. They are not an externally validated Intel
  opinion or independently verifiable authorization certificates. Their bytes are
  retained; this documentation pass does not regenerate them.

A report heading such as `Decision` is a presentation of the supplied assessment,
not a new authorization source. For current integrations, keep `proposed_decision`,
`assurance`, authorized `final_decision` and the complete `decision_certificate` from
its [API response](../docs/API_REFERENCE.md). Hash integrity is not issuer
authentication. Scores and evidence-quality indices remain UNCALIBRATED; E5 remains
BLOCKED / DRAFT_NOT_FROZEN. See the [case-study limits](../docs/case_study_001.md).
