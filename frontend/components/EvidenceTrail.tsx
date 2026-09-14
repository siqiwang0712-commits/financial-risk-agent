import { displayRatio, evidenceLocator } from "../lib/presentation.mjs";
import type { Conclusion, Evidence } from "../lib/types";

interface Props {
  conclusions: Conclusion[];
}

/**
 * A numeric field, formatted, or an explicit "N/A".
 *
 * `item.confidence.toFixed(2)` threw on `undefined`, and `verification_status`
 * is rendered as a status label, so it must survive a missing value too - a
 * citation whose status the backend did not report is exactly the case a reader
 * most needs to see.
 */
function statusLabel(status: string | undefined): string {
  return typeof status === "string" && status ? status.toUpperCase() : "UNKNOWN";
}

function EvidenceCard({ item }: { item: Evidence }) {
  const verified = item.verification_status === "verified";
  return (
    <blockquote className={`evidenceCard ${verified ? "verified" : "unverified"}`}>
      <header>
        <span className={`statusDot ${verified ? "ok" : "bad"}`} aria-hidden="true" />
        <b>{statusLabel(item.verification_status)}</b>
        <span className="locator">{evidenceLocator(item)}</span>
      </header>
      <p>{item.quote || item.source_text || "(no quoted span)"}</p>
      <footer>
        <span>confidence {displayRatio(item.confidence, 2)}</span>
        {item.value !== null && item.value !== undefined ? <span>value {item.value}</span> : null}
        {item.unit ? <span>{item.unit}</span> : null}
      </footer>
    </blockquote>
  );
}

/**
 * "Evidence is the product" rendered literally: conclusion, reason, the tool or
 * rule that produced it, and the quoted span it rests on.
 *
 * A conclusion with no verified evidence is displayed as such rather than
 * dropped, because an unsupported claim that was correctly refused is itself
 * evidence that the gate works.
 */
export function EvidenceTrail({ conclusions }: Props) {
  if (!conclusions?.length) {
    return (
      <div className="emptyState">
        <b>No evidence-supported material risk conclusion was admitted.</b>
        <p>
          The claim verifier admits a conclusion only when every material input carries verified
          provenance. An empty trail here means nothing cleared that bar - not that no risk exists.
        </p>
      </div>
    );
  }

  return (
    <div className="evidenceTrail">
      {conclusions.map((conclusion, index) => (
        <article className="trailItem" key={`${conclusion.claim}-${index}`}>
          <div className="trailClaim">
            <small>Conclusion</small>
            <h3>{conclusion.claim}</h3>
            <p>{conclusion.reason}</p>
          </div>

          <div className="trailMechanism">
            <small>Tool / rationale</small>
            <b>{conclusion.tool}</b>
            <p>{conclusion.rationale}</p>
            <span className="confidenceChip">confidence {conclusion.confidence}</span>
          </div>

          <div className="trailEvidence">
            <small>Verified evidence</small>
            {conclusion.evidence?.length ? (
              conclusion.evidence.map((item, itemIndex) => (
                <EvidenceCard key={`${item.document}-${item.page}-${itemIndex}`} item={item} />
              ))
            ) : (
              <p className="muted">No quoted span reached this conclusion.</p>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export { EvidenceCard };
