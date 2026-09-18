import { displayReliability, displayScore } from "../lib/presentation.mjs";
import type { AssessmentPayload } from "../lib/types";

interface Props {
  payload: AssessmentPayload;
}

function Cell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`stripCell${tone ? ` ${tone}` : ""}`}>
      <small>{label}</small>
      <b>{value}</b>
    </div>
  );
}

function ratio(value: number | null | undefined): string {
  return value === null || value === undefined ? "N/A" : value.toFixed(3);
}

/**
 * The headline. Note what is *not* here: no probability, no confidence in the
 * colloquial sense, no single number presented as truth. Severity, coverage,
 * evidence quality, disagreement and reliability stay visually separate because
 * the project's central claim is that they are different things.
 */
export function DecisionSummary({ payload }: Props) {
  const agent = payload.agent;
  const epistemics = agent?.epistemics;
  const severity = agent?.risk_severity ?? "unknown";
  const decision = payload.final_decision || agent?.decision || "REVIEW";

  return (
    <section className={`decisionSummary severity-${severity}`}>
      <div className="decisionHero">
        <div className="heroScore">
          <small>Risk index · heuristic, not a probability</small>
          <div className="scoreValue">
            {displayScore(payload.overall_score)}
            {payload.overall_score === null ? null : <span>/100</span>}
          </div>
          <p className="heroLevel">{payload.risk_level}</p>
        </div>

        <div className="heroDecision">
          <small>Decision</small>
          <b className={`decisionTag ${String(decision).toLowerCase()}`}>{decision}</b>
          <p className="heroCompany">
            {payload.company} · FY{payload.reporting_period}
          </p>
          <p className="heroReliability">
            {/* Without a fallback the reliability line renders an empty string for
                a payload that carries no calibration status. */}
            {displayReliability(
              epistemics?.calibration_status ?? payload.reliability_status ?? "UNCALIBRATED",
              epistemics?.reliability ?? null,
            )}
          </p>
        </div>
      </div>

      <div className="decisionStrip">
        <Cell label="Severity" value={severity} />
        <Cell label="Trajectory" value={agent?.risk_trajectory ?? "unknown"} />
        <Cell label="Evidence coverage" value={ratio(payload.evidence_coverage)} />
        <Cell label="Evidence quality" value={ratio(payload.evidence_quality)} />
        <Cell label="Model disagreement" value={ratio(agent?.model_disagreement)} />
        <Cell label="Verified paths" value={`${agent?.decision_trace?.verified_path_count ?? 0}/${agent?.decision_trace?.material_path_count ?? 0}`} />
      </div>

      {payload.legacy_weighted_score !== undefined && payload.legacy_weighted_score !== null ? (
        <p className="legacyNote">
          The risk index above is the fusion score the decision was derived from. The earlier
          expert-weighted aggregate for the same evidence was{" "}
          <b>{payload.legacy_weighted_score}</b>; it is retained as a diagnostic only.
        </p>
      ) : null}
    </section>
  );
}
