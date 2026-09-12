import type { AssessmentPayload } from "../lib/types";

interface Props {
  payload: AssessmentPayload;
}

/**
 * Plain-language account of how the decision was reached, or why the system
 * declined to reach one.
 *
 * This panel exists because the project's claim is not "we score companies" but
 * "every material conclusion traces to verified evidence, and when it cannot,
 * the system says so". That claim is only credible if a reader can see the
 * mechanism, so the mechanism is rendered rather than hidden behind a number.
 */

const REASON_COPY: Record<string, string> = {
  SEVERE_VERIFIED_SIGNAL:
    "At least one verified signal reached a severe band. Fusion is non-compensatory, so ordinary dimensions cannot average it away.",
  INSUFFICIENT_EVIDENCE:
    "Evidence coverage fell below the policy floor. The system abstains rather than guessing.",
  CLAIM_CONTEXT_INCOMPLETE:
    "A claim was tested against fewer evidence constructs than its category requires, so it was not classified as a contradiction.",
  HIGH_MODEL_DISAGREEMENT:
    "Independent components disagreed beyond the policy ceiling, so the result is routed to review instead of being presented as settled.",
  UNVALIDATED_RELIABILITY:
    "Reliability is UNCALIBRATED. The evidence-quality index is not a probability and is not treated as one.",
  CRITICAL_DIMENSION_ESCALATION:
    "A single dimension reached the critical band and escalated the aggregate as a monotonic floor.",
  AGGREGATE_CRITICAL_SCORE:
    "The fused score itself reached the critical band.",
  DUPLICATE_EVIDENCE_SUPPRESSED:
    "A correlated evidence group was capped to its strongest contribution so one disclosure could not be counted repeatedly.",
};

const FAILURE_COPY: Record<string, string> = {
  missing_evidence: "Material inputs exist but none carries verified provenance.",
  conflicting_evidence: "Narrative and numeric evidence conflict on at least one verified claim.",
  llm_unavailable: "The narrative provider failed. The numeric result is preserved and the run degrades to review.",
  parser_failure: "Filing extraction failed, so nothing downstream can be trusted.",
  stale_data: "The filing is outside the accepted recency window.",
  rule_model_contradiction: "A configured rule and a traditional model point in opposite directions.",
};

function verdictSentence(payload: AssessmentPayload): string {
  const agent = payload.agent;
  const decision = payload.final_decision || agent?.decision || "REVIEW";
  const trace = agent?.decision_trace;
  const verified = trace?.verified_path_count ?? 0;
  const material = trace?.material_path_count ?? 0;

  if (decision === "ABSTAIN") {
    return `The system declined to decide. Evidence coverage is ${payload.evidence_coverage.toFixed(3)}, below the policy floor, so no conclusion is asserted.`;
  }
  if (decision === "REVIEW") {
    return `The system routed this to human review. ${material - verified} of ${material} material paths could not be fully verified, so the result is not presented as settled.`;
  }
  if (decision === "FLAG") {
    return `The system flagged risk. ${verified} of ${material} material paths are verified, and at least one verified signal reached a severe band.`;
  }
  return `No adverse signal cleared the review threshold across ${material} material path(s). This is a low-severity reading, not an assurance of safety.`;
}

export function WhyDecision({ payload }: Props) {
  const agent = payload.agent;
  const trace = agent?.decision_trace;
  const failure = payload.failure_state;
  const verifier = agent?.role_review?.verifier;

  const codes = Array.from(
    new Set([
      ...(trace?.decision_reason_codes ?? []),
      ...(agent?.fusion?.reason_codes ?? []),
    ]),
  );

  const failures = [
    ...(failure?.blocking_failures ?? []).map((name) => ({ name, kind: "blocking" as const })),
    ...(failure?.review_failures ?? []).map((name) => ({ name, kind: "review" as const })),
  ];

  const rejected = verifier?.challenges?.filter((item) => item.severity === "blocking").length ?? 0;

  return (
    <section className="panel whyPanel">
      <div className="panelHeading">
        <div>
          <p className="kicker">Decision basis</p>
          <h2>Why this decision</h2>
        </div>
        <p className="panelMeta">
          {failure?.degraded ? "degraded run" : "nominal run"}
        </p>
      </div>

      <p className="verdict">{verdictSentence(payload)}</p>

      <div className="whyGrid">
        <div className="whyBlock">
          <h3>Reason codes</h3>
          {codes.length ? (
            <ul className="reasonList">
              {codes.map((code) => (
                <li key={code}>
                  <code>{code}</code>
                  <p>{REASON_COPY[code] ?? "Machine-readable reason recorded on the decision."}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No reason codes were recorded for this decision.</p>
          )}
        </div>

        <div className="whyBlock">
          <h3>Failure states</h3>
          {failures.length ? (
            <ul className="reasonList">
              {failures.map(({ name, kind }) => (
                <li key={`${kind}-${name}`}>
                  <code className={kind === "blocking" ? "blocking" : "review"}>{name}</code>
                  <p>{FAILURE_COPY[name] ?? "Recorded as a first-class failure state."}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              No blocking or review-level failure was recorded. Missing inputs, low coverage,
              parser failure and provider failure are all first-class states here, so their absence
              is meaningful.
            </p>
          )}

          {verifier ? (
            <div className="verifierOutcome">
              <h4>Analyst · Critic · Verifier</h4>
              <p>
                Verifier verdict <b className={verifier.status === "REJECTED" ? "rejected" : "accepted"}>{verifier.status}</b>
                {typeof verifier.checked_claims === "number"
                  ? ` after checking ${verifier.checked_claims} claim(s)`
                  : ""}
                {rejected ? `, with ${rejected} blocking challenge(s).` : "."}
              </p>
            </div>
          ) : null}
        </div>

        <div className="whyBlock">
          <h3>What is missing</h3>
          {payload.missing_information.length ? (
            <ul className="missingList">
              {payload.missing_information.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              Every metric required by the triggered rules was computable. Absence of a missing-value
              note is not a completeness guarantee.
            </p>
          )}

          <div className="coverageBreakdown">
            <h4>Evidence quality composition</h4>
            <ul>
              {Object.entries(payload.confidence_components).map(([key, value]) => (
                <li key={key}>
                  <span>{key.replace(/_/g, " ")}</span>
                  <i className="miniBar">
                    <b style={{ width: `${Math.round(value * 100)}%` }} />
                  </i>
                  <em>{value.toFixed(2)}</em>
                </li>
              ))}
            </ul>
            <p className="footnote">
              These components combine into the evidence-quality index. None of them is a
              probability that the decision is correct.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
