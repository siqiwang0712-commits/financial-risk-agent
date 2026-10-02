import type { AssuranceResult, DecisionCertificate } from "../lib/types";

interface Props {
  assurance: AssuranceResult;
  certificate: DecisionCertificate;
}

function State({ label, value }: { label: string; value: string }) {
  const tone = /VERIFIED|STABLE|IN_REFERENCE|PASSED/.test(value)
    ? "ok"
    : /FAILED|FRAGILE|OUTSIDE|INSUFFICIENT/.test(value)
      ? "bad"
      : "warn";
  return (
    <div className="assuranceState">
      <span>{label}</span>
      <b className={`statusChip ${tone}`}>{value.replaceAll("_", " ")}</b>
    </div>
  );
}

export function AssurancePanel({ assurance, certificate }: Props) {
  const sufficient = assurance.decision_sufficient_evidence;
  const fragility = assurance.evidence_fragility;
  const distribution = assurance.distribution_validity;

  return (
    <section className="assurancePanel" aria-label="Decision assurance details">
      <header>
        <div>
          <small>DECISION AUTHORIZATION</small>
          <h3>Why this proposal was—or was not—authorized</h3>
        </div>
        <span className={`statusChip ${assurance.automation_allowed ? "ok" : "warn"}`}>
          {assurance.automation_allowed ? "AUTOMATION ALLOWED" : "HUMAN CONTROL REQUIRED"}
        </span>
      </header>

      <div className="assuranceStates">
        <State label="Evidence support" value={assurance.evidence_assurance.state} />
        <State label="Evidence robustness" value={fragility.state} />
        <State label="Distribution validity" value={distribution.state} />
        <State label="Policy maturity" value={assurance.policy_status} />
      </div>

      {assurance.reason_codes.length ? (
        <div className="assuranceReasons">
          <b>Authorization reasons</b>
          <ul>{assurance.reason_codes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
        </div>
      ) : null}

      <details>
        <summary>Evidence fragility</summary>
        <p>
          Largest single-evidence score impact: <b>{fragility.largest_single_evidence_impact ?? "N/A"}</b> · Decision flips: <b>{fragility.decision_flip_count}</b>
        </p>
        <p>This deterministic ablation does not rerun the LLM or acquire new evidence.</p>
      </details>

      <details>
        <summary>Decision-sufficient evidence</summary>
        <p>Method: <b>{sufficient.method}</b>{sufficient.exact ? " · exact" : " · approximate, not mathematically minimal"}</p>
        {sufficient.evidence_ids.length ? (
          <ul>{sufficient.evidence_ids.map((id) => <li key={id}><code>{id}</code></li>)}</ul>
        ) : <p>No decision-sufficient subset could be estimated.</p>}
      </details>

      <details>
        <summary>Distribution validity</summary>
        <p>
          Reference: <b>{distribution.reference_name ?? "No frozen reference"}</b> · Evaluated features: <b>{distribution.evaluated_feature_count}</b>
        </p>
        <p>Reference scope: <b>{distribution.reference_scope ?? "NONE"}</b>. A development reference is not external validation.</p>
        {distribution.diagnostics.map((item) => <p key={item}>{item}</p>)}
        {distribution.state !== "IN_REFERENCE" ? <p>Existing assurance claims are not asserted outside the defined reference scope.</p> : null}
      </details>

      <details>
        <summary>Decision Certificate</summary>
        <dl className="certificateGrid">
          <dt>Certificate</dt><dd>{certificate.certificate_version}</dd>
          <dt>Certificate hash</dt><dd><code>{certificate.certificate_hash}</code></dd>
          <dt>Input digest</dt><dd><code>{certificate.input_hash}</code></dd>
          <dt>Output digest</dt><dd><code>{certificate.output_hash}</code></dd>
          <dt>Policy</dt><dd>{certificate.policy_version}</dd>
        </dl>
      </details>
    </section>
  );
}
