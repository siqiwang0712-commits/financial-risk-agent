# E5-Narrative — Claim-Level Evidence Grounding in Filing Text

Status: **PROSPECTIVE PROTOCOL — NOT FROZEN — NO CORPUS, NO ANNOTATIONS, NO RESULTS**

Supersedes the narrative paragraph in `STUDY_PROTOCOL.md` §12, which remains the summary.

---

## 1. Why this is a separate study

Structured E5 asks whether an Agent's **risk ranking** adds value beyond B6. It does not
test whether the Agent can *read a filing*. Those are different capabilities with different
evidence requirements, and E4 already showed what happens when they are conflated: E4's
Agent packets contained structured facts and engineered metrics, not MD&A or Risk Factors,
so E4 cannot support any claim about document reasoning. Its own audit records this as a
scope boundary, not a gap to be papered over.

E5-Narrative therefore tests the thing the project is actually named for — whether a
Financial Risk Agent can extract, ground and check **claims** against **evidence** in filing
text — with its own corpus, its own ground truth and its own metrics. It must not be merged
into structured E5, and no number from one may be quoted as evidence for the other.

## 2. Research questions

| ID | Question |
|---|---|
| N1 | Can the Agent extract the risk-relevant claims a human annotator would extract, at a usable recall and precision? |
| N2 | Is every extracted claim **grounded** in a specific, correct span of the filing? |
| N3 | Does the Agent detect contradictions between narrative and the structured financials? |
| N4 | Does the Agent detect **temporal** changes between consecutive filings? |
| N5 | Does the Agent abstain when the text does not support a claim, rather than asserting one? |

N2 and N5 are the load-bearing questions. An agent that produces fluent risk prose with
fabricated or unattributable citations is worse than useless in a decision-grade setting,
and N2/N5 are the metrics that expose it.

## 3. Corpus

**Sections.** From each filing: MD&A, Risk Factors, Liquidity, Debt, and the footnotes
relevant to going concern; plus auditor commentary and any going-concern paragraph.

**Selection.** Companies are disjoint from E1–E5 and from every prior validation cohort.
Selection is by the frozen hash rule, not by hand, so the annotators cannot pick easy cases.

**Freeze.** Section text, section boundaries, the extraction method and its version, and the
content hash of every section are frozen before annotation begins. Section boundary choice
matters — a "claim" is only well defined relative to a section — so the boundary rule is part
of the frozen protocol.

**No future text.** Nothing after the filing's own period may appear in any packet. The
outcome used in structured E5 is never visible here.

## 4. Ground truth

**Unit of annotation: the claim.** A claim is a sentence-level assertion about the company's
financial condition that a risk analyst would record. The annotation schema fixes the fields:

```
claim_id, company_id, filing_period, section, claim_span,
claim_text, claim_type (level | trend | driver | forward_looking),
direction (improving | deteriorating | neutral),
evidence_spans[], evidence_sufficiency (sufficient | partial | absent),
contradicts_structured_financials (true | false | unknown),
temporal_change (new | repeated | escalated | resolved | not_comparable)
```

**Two annotators plus adjudication.** Annotator A and Annotator B label every section
independently. Disagreements go to Annotator C, blind to both verdicts. Report raw agreement,
Cohen's κ per field, and the adjudication rate. Field-level κ matters more than a single
aggregate: `evidence_spans` agreement is typically far lower than `direction` agreement, and
collapsing them hides the part that is actually hard.

**Annotation guidelines are frozen and published** before annotation, together with a small
worked example set. Guidelines changed after seeing model output would make the ground truth
a function of the model.

**Annotators must not see** any model output, any score, any prediction, or the other
annotator's verdict before recording their own.

## 5. Metrics

Each metric is defined on the claim unit and reported with its denominator.

| Metric | Definition |
|---|---|
| Claim recall | `|matched reference claims| / |reference claims|`, matching on span overlap + type |
| Claim precision | `|matched model claims| / |model claims|` |
| Evidence grounding rate | share of model claims whose cited spans overlap a reference evidence span for that claim |
| Citation correctness | share of cited spans that actually support the claim, judged against the frozen text (not against the model's own text) |
| Contradiction F1 | F1 against the reference `contradicts_structured_financials` labels |
| Temporal-change F1 | F1 against reference `temporal_change` labels, computed only on companies with a comparable prior filing |
| Unsupported-claim rate | `|model claims with evidence_sufficiency = absent| / |model claims|` — lower is better |
| Abstention quality | among cases where the reference says `evidence_sufficiency = absent`, the share where the model abstained; plus the share where the reference says `sufficient` but the model abstained (over-abstention) |

Both directions of abstention are reported. A model that abstains on everything scores
perfectly on the unsupported-claim rate, so the pair is required.

## 6. Instrument validation (the part that is usually skipped)

A metric for "citation correctness" is only meaningful if it can detect a **known-wrong**
citation. Before the model is run, the annotation pipeline is validated on a set of
**planted defects**:

1. take reference claims with correct citations;
2. inject a controlled defect — a citation pointing at an unrelated span, a claim whose
   direction is flipped, a claim asserted with no evidence, a temporal change mislabelled;
3. run the metric implementation over the injected set.

The metric must recover the injected defects at a rate reported **before** any model result
is seen. If the metric cannot detect a defect that was deliberately planted, it cannot be
trusted to report the same defect in model output. This mirrors the E4-S finding that the
instrument has to be audited, not just used.

Report per-defect-type detection rate and false-positive rate on unmodified claims.

## 7. Systems and controls

| System | Purpose |
|---|---|
| `full` | the complete Agent pipeline as shipped |
| `no_retrieval` | claims generated without evidence retrieval — should degrade grounding sharply |
| `retrieval_only` | evidence spans returned without claim synthesis |
| `evidence_removed` | `full` with the cited spans stripped before judging — tests whether the metric depends on the model's own citations |
| human upper bound | Annotator A's own output scored against the adjudicated reference |

The `evidence_removed` control is the important one: if citation correctness does not change
when the evidence is removed, the metric is measuring the model's self-consistency rather
than grounding.

## 8. Inference

- Comparisons are **paired on the claim unit** but resampled by **company**, because claims
  within a company share text and annotator attention.
- Intervals: company-cluster BCa bootstrap, 20,000 replicates.
- Multiplicity: Holm across the N1–N5 family at family-wise α = 0.05, frozen before
  annotation.
- Effect sizes are reported with the denominator, and any subgroup below 20 claims is
  descriptive only.
- The primary test for a difference in a rate is a paired cluster bootstrap; no
  label-permutation test is used, for the reasons in `INFERENCE_POLICY.md`.

## 9. Failure taxonomy

Every error is classified into exactly one bucket, with counts reported: extraction miss,
spurious claim, wrong span, span too broad, citation unsupported, direction error,
contradiction false positive, contradiction false negative, temporal misclassification,
over-abstention, and abstention on a supported claim. A single aggregate score hides which of
these dominates, and the fix differs per bucket.

## 10. Governance

Follows `GOVERNANCE_WORKFLOW.md` with the same staging discipline:

```
narrative-protocol  ->  section-freeze  ->  guideline-freeze  ->  annotation-A/B
                    ->  adjudication  ->  instrument-validation  ->  model-run
                    ->  evaluation  ->  results
```

The **instrument-validation** stage must be committed and pushed before the model-run stage
exists, so that the metric's detection ability is on the record before any model number is.

## 11. What this will and will not establish

**Will establish**, if the gates pass: whether the Agent's claims are grounded in the filing
text, whether its citations are correct, whether it detects narrative–numeric contradictions
and temporal changes, and how it behaves when the evidence is absent.

**Will not establish:** that grounded claim extraction improves risk ranking (that is
structured E5's question); any calibrated probability; production or regulatory fitness; or
that the annotation is unbiased in general — only that it was produced blind to model output.

## 12. Limitations to state up front

- Claim segmentation is partly subjective; κ on `claim_span` will be imperfect and is
  reported rather than smoothed away.
- The reference set is bounded by annotator time, so recall is measured against a
  human-produced reference, not a complete one.
- Planted defects validate the *metric*, not the annotators; annotator error is measured by
  κ and remains a limitation.
- A single filing period gives temporal-change labels only where a comparable prior filing
  exists, which will be a subset.
