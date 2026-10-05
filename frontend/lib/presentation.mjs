export function displayScore(score) {
  return score === null || score === undefined ? 'N/A' : String(score);
}

export function displayReliability(status, value) {
  if (status === 'UNCALIBRATED') return 'UNCALIBRATED — not a probability';
  return value === null || value === undefined ? status : `${status} ${value}`;
}

export function normalizeDecision(value) {
  return ['ABSTAIN', 'REVIEW', 'PASS', 'FLAG'].includes(value) ? value : 'REVIEW';
}

export function authorizedDecision(payload) {
  const assurance = payload?.assurance;
  const certificate = payload?.decision_certificate;
  if (!assurance || !certificate
    || !['ABSTAIN', 'REVIEW', 'PASS', 'FLAG'].includes(payload.final_decision)
    || !['ABSTAIN', 'REVIEW', 'PASS', 'FLAG'].includes(payload.proposed_decision)
    || typeof assurance.policy_hash !== 'string' || !assurance.policy_hash
    || typeof certificate.certificate_hash !== 'string' || !certificate.certificate_hash
    || payload.final_decision !== assurance.final_decision
    || payload.proposed_decision !== assurance.proposed_decision
    || certificate.final_decision !== assurance.final_decision
    || certificate.proposed_decision !== assurance.proposed_decision
    || certificate.policy_hash !== assurance.policy_hash
    || (payload.agent != null
      && certificate.certificate_hash !== payload.agent?.decision_certificate?.certificate_hash)) {
    return 'UNAUTHORIZED';
  }
  return payload.final_decision;
}

export function evidenceLocator(evidence) {
  return [evidence.source, evidence.document, evidence.page ? `page ${evidence.page}` : null]
    .filter(Boolean)
    .join(' · ');
}

export async function safeApiJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}
